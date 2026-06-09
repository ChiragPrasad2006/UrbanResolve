import os
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pymongo.database import Database
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from shared.analytics import (
    build_heatmap_data,
    build_issue_severity,
    build_sla_status,
    build_verification_summary,
    group_duplicate_hotspots,
)
from shared.database import (
    get_db,
    init_database,
    issues_col,
    comments_col,
    resolution_verifications_col,
    users_col,
    email_otps_col,
)
from shared.email_utils import send_email
from shared.media_utils import distance_in_meters, save_upload, upload_path_to_disk
from shared.middleware import SecurityHeadersMiddleware, limiter
from shared.models import make_email_otp, make_user
from shared.security import (
    decrypt_email,
    encrypt_email,
    generate_csrf_token,
    generate_otp,
    hash_email,
    hash_otp,
    sanitize_input,
    sign_session,
    unsign_session,
    validate_csrf_token,
    verify_otp,
    verify_password,
)

init_database()

BASE_DIR = Path(__file__).resolve().parent
app = FastAPI(title="UrbanResolve Login - Admin Portal")

# Security middleware
app.add_middleware(SecurityHeadersMiddleware)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/uploads", StaticFiles(directory=str(BASE_DIR.parent / "shared" / "uploads")), name="uploads")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_current_admin(request: Request) -> str | None:
    """Extract admin email from signed session cookie."""
    token = request.cookies.get("urbanresolve_admin")
    if not token:
        return None
    return unsign_session(token)


def render_template(name: str, request: Request, context: dict):
    current_admin = get_current_admin(request)
    full_context = {
        "request": request,
        "current_admin": current_admin,
        "csrf_token": generate_csrf_token(),
    }
    full_context.update(context)
    return templates.TemplateResponse(request=request, name=name, context=full_context)


def send_escalation_if_needed(issue: dict, severity_score: float, sla_status: dict, verification_summary: dict):
    escalation_email = os.getenv("ESCALATION_EMAIL")
    if not escalation_email or not sla_status["overdue"] or issue.get("escalation_notified_at") is not None:
        return

    body_lines = [
        f"Issue '{issue['title']}' requires escalation.",
        f"Category: {issue['category']}",
        f"Ward: {issue.get('ward') or 'Unassigned'}",
        f"Severity score: {severity_score}",
        f"SLA allowed hours: {sla_status['allowed_hours']}",
        f"Elapsed hours: {sla_status['elapsed_hours']}",
        f"Community not solved confirmations: {verification_summary.get('not_solved', 0)}",
    ]
    send_email(escalation_email, f"Escalation Required: {issue['title']}", "\n".join(body_lines))
    issues_col().update_one(
        {"issue_id": issue["issue_id"]},
        {"$set": {"escalation_notified_at": datetime.utcnow()}},
    )


def load_dashboard_context(request: Request, **context):
    issues = list(issues_col().find().sort("created_at", -1))
    all_comments = list(comments_col().find().sort("created_at", 1))
    all_verifications = list(resolution_verifications_col().find().sort("created_at", -1))

    issue_comments: dict[int, list[dict]] = {}
    for comment in all_comments:
        issue_comments.setdefault(comment["issue_id"], []).append(comment)
    comment_counts = {issue["issue_id"]: len(issue_comments.get(issue["issue_id"], [])) for issue in issues}

    issue_verifications: dict[int, list[dict]] = {}
    for verification in all_verifications:
        issue_verifications.setdefault(verification["issue_id"], []).append(verification)

    hotspots = group_duplicate_hotspots(issues, comment_counts)
    issue_severity = {
        issue["issue_id"]: build_issue_severity(issue, comment_counts.get(issue["issue_id"], 0), hotspots)
        for issue in issues
    }
    issues.sort(
        key=lambda issue: (issue["status"] == "Resolved", -issue_severity[issue["issue_id"]], issue["created_at"]),
        reverse=False,
    )
    sla_status = {issue["issue_id"]: build_sla_status(issue, issue_severity[issue["issue_id"]]) for issue in issues}
    verification_summary = {
        issue["issue_id"]: build_verification_summary(issue_verifications.get(issue["issue_id"], []))
        for issue in issues
    }

    for issue in issues:
        send_escalation_if_needed(
            issue,
            issue_severity[issue["issue_id"]],
            sla_status[issue["issue_id"]],
            verification_summary[issue["issue_id"]],
        )

    heatmap_points = build_heatmap_data(issues, comment_counts)
    issue_hotspots = {}
    for hotspot in hotspots:
        for hotspot_issue in hotspot["issues"]:
            issue_hotspots[hotspot_issue["issue_id"]] = hotspot

    active_issues = [issue for issue in issues if issue["status"] != "Resolved"]
    resolved_issues = [issue for issue in issues if issue["status"] == "Resolved"]

    # Decrypt reporter emails for admin display
    for issue in active_issues + resolved_issues:
        try:
            issue["reporter_email"] = decrypt_email(issue["reporter_email_enc"])
        except Exception:
            issue["reporter_email"] = "[encrypted]"

    # Decrypt commenter emails for admin display
    for comments_list in issue_comments.values():
        for comment in comments_list:
            try:
                comment["commenter_email"] = decrypt_email(comment["commenter_email_enc"])
            except Exception:
                comment["commenter_email"] = "[encrypted]"

    # Decrypt verifier emails for admin display
    for verifications_list in issue_verifications.values():
        for verification in verifications_list:
            try:
                verification["verifier_email"] = decrypt_email(verification["verifier_email_enc"])
            except Exception:
                verification["verifier_email"] = "[encrypted]"

    merged_context = {
        "issues": active_issues,
        "resolved_issues": resolved_issues,
        "issue_comments": issue_comments,
        "issue_verifications": issue_verifications,
        "verification_summary": verification_summary,
        "issue_severity": issue_severity,
        "sla_status": sla_status,
        "hotspots": hotspots[:8],
        "issue_hotspots": issue_hotspots,
        "heatmap_points": heatmap_points,
    }
    merged_context.update(context)
    return render_template("dashboard.html", request, merged_context)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/")
def admin_root():
    return RedirectResponse(url="/login", status_code=307)


@app.get("/login")
def admin_login_page(request: Request):
    return render_template("login.html", request, {})


@app.post("/login")
@limiter.limit("5/minute")
def admin_login_route(
    request: Request,
    identifier: str = Form(...),
    password: str = Form(""),
    csrf_token: str = Form(""),
    db: Database = Depends(get_db)
):
    if not validate_csrf_token(csrf_token):
        return render_template("login.html", request, {"identifier": identifier, "error": "Invalid CSRF token. Please try again."})
        
    identifier = sanitize_input(identifier, max_length=254)
    identifier_lower = identifier.lower()

    email_h = hash_email(identifier)
    admin = users_col().find_one({
        "$or": [
            {"email_hash": email_h},
            {"username_lower": identifier_lower}
        ],
        "role": "admin"
    })

    if not admin:
        return render_template("login.html", request, {"identifier": identifier, "error": "Invalid credentials or unauthorized."})

    if not admin.get("password_hash") or not verify_password(password, admin["password_hash"]):
        return render_template("login.html", request, {"identifier": identifier, "error": "Invalid credentials."})

    try:
        admin_email = decrypt_email(admin["encrypted_email"])
    except Exception:
        admin_email = identifier if "@" in identifier else ""

    response = load_dashboard_context(request, success="Admin login successful")
    response.set_cookie(
        key="urbanresolve_admin",
        value=sign_session(admin_email),
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 8,
    )
    return response


@app.post("/login/request-otp")
@limiter.limit("5/minute")
def admin_request_otp(request: Request, identifier: str = Form(...), csrf_token: str = Form(""), db: Database = Depends(get_db)):
    if not validate_csrf_token(csrf_token):
        return render_template("login.html", request, {"identifier": identifier, "error": "Invalid CSRF token."})
        
    identifier = sanitize_input(identifier, max_length=254)
    email_h = hash_email(identifier)

    admin = users_col().find_one({
        "$or": [
            {"email_hash": email_h},
            {"username_lower": identifier.lower()}
        ],
        "role": "admin"
    })
    
    if not admin:
        return render_template("login.html", request, {"identifier": identifier, "error": "Unauthorized admin"})

    try:
        email = decrypt_email(admin["encrypted_email"])
    except Exception:
        email = identifier if "@" in identifier else ""
        if not email:
            return render_template("login.html", request, {"identifier": identifier, "error": "Email address missing for this user."})

    otp = generate_otp()
    otp_h = hash_otp(otp)
    email_h_real = hash_email(email)
    record = make_email_otp(
        email_hash=email_h_real,
        otp_hash=otp_h,
        expires_at=datetime.utcnow() + timedelta(minutes=5),
    )
    email_otps_col().insert_one(record)

    email_sent, email_message = send_email(email, "Admin Login OTP", f"Your admin OTP is: {otp}\nValid for 5 minutes.")
    if not email_sent:
        return render_template(
            "login.html",
            request,
            {"identifier": identifier, "error": f"Could not send OTP email: {email_message}"},
        )
    return render_template(
        "login.html",
        request,
        {"identifier": identifier, "message": "OTP sent to admin email", "otp_requested": True},
    )


@app.post("/login/verify-otp")
@limiter.limit("5/minute")
def admin_verify_otp(
    request: Request,
    identifier: str = Form(...),
    otp: str = Form(...),
    csrf_token: str = Form(""),
    db: Database = Depends(get_db),
):
    if not validate_csrf_token(csrf_token):
        return render_template("login.html", request, {"identifier": identifier, "error": "Invalid CSRF token.", "otp_requested": True})
        
    identifier = sanitize_input(identifier, max_length=254)
    otp = sanitize_input(otp, max_length=6)
    email_h = hash_email(identifier)

    admin = users_col().find_one({
        "$or": [
            {"email_hash": email_h},
            {"username_lower": identifier.lower()}
        ],
        "role": "admin"
    })
    if not admin:
        return render_template("login.html", request, {"identifier": identifier, "error": "Unauthorized admin"})

    try:
        email = decrypt_email(admin["encrypted_email"])
    except Exception:
        email = identifier if "@" in identifier else ""

    email_h_real = hash_email(email)

    record = email_otps_col().find_one(
        {"email_hash": email_h_real},
        sort=[("_id", -1)],
    )
    if not record:
        return render_template(
            "login.html",
            request,
            {"identifier": identifier, "error": "Invalid or expired OTP", "otp_requested": True},
        )

    otp_valid = verify_otp(otp, record["otp_hash"]) and datetime.utcnow() < record["expires_at"]
    if not otp_valid:
        return render_template(
            "login.html",
            request,
            {"identifier": identifier, "error": "Invalid or expired OTP", "otp_requested": True},
        )

    response = load_dashboard_context(request, success="Admin login successful")
    response.set_cookie(
        key="urbanresolve_admin",
        value=sign_session(email),
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 8,
    )
    return response


@app.get("/logout")
def admin_logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("urbanresolve_admin")
    return response


@app.get("/dashboard")
def admin_dashboard(request: Request, db: Database = Depends(get_db)):
    current_admin = get_current_admin(request)
    if not current_admin:
        return RedirectResponse(url="/login", status_code=303)
    return load_dashboard_context(request)


@app.post("/issue/update")
@limiter.limit("20/minute")
def update_issue_status(
    request: Request,
    issue_id: int = Form(...),
    status: str = Form(...),
    update_message: str = Form(""),
    resolution_notes: str = Form(""),
    resolution_latitude: str = Form(""),
    resolution_longitude: str = Form(""),
    resolution_video: UploadFile = File(None),
    csrf_token: str = Form(""),
    db: Database = Depends(get_db),
):
    if not validate_csrf_token(csrf_token):
        return load_dashboard_context(request, error="Invalid CSRF token.")
        
    current_admin = get_current_admin(request)
    if not current_admin:
        return RedirectResponse(url="/login", status_code=303)

    # Sanitize inputs
    status = sanitize_input(status, max_length=20)
    update_message = sanitize_input(update_message, max_length=2000)
    resolution_notes = sanitize_input(resolution_notes, max_length=5000)

    issue = issues_col().find_one({"issue_id": issue_id})
    if not issue:
        return load_dashboard_context(request, error="Issue not found")

    parsed_resolution_latitude = float(resolution_latitude) if resolution_latitude else None
    parsed_resolution_longitude = float(resolution_longitude) if resolution_longitude else None

    if resolution_video and issue.get("latitude") is not None and issue.get("longitude") is not None:
        if parsed_resolution_latitude is None or parsed_resolution_longitude is None:
            return load_dashboard_context(
                request,
                error="Select the on-site resolution location on the map before uploading the fix video.",
            )

        distance = distance_in_meters(
            issue["latitude"],
            issue["longitude"],
            parsed_resolution_latitude,
            parsed_resolution_longitude,
        )
        if distance > 300:
            return load_dashboard_context(
                request,
                error="Resolution evidence must be uploaded within 300 meters of the original issue location.",
            )

    resolution_video_path = save_upload(resolution_video, "resolution_videos")

    update_fields = {
        "status": status,
        "last_update_message": update_message,
        "admin_resolution_notes": resolution_notes,
        "admin_resolution_latitude": parsed_resolution_latitude,
        "admin_resolution_longitude": parsed_resolution_longitude,
        "updated_at": datetime.utcnow(),
    }

    if resolution_video_path:
        update_fields["admin_resolution_video_path"] = resolution_video_path

    previous_status = issue["status"]
    if status == "Resolved" and previous_status != "Resolved":
        update_fields["resolved_at"] = datetime.utcnow()
    elif status != "Resolved":
        update_fields["resolved_at"] = None

    issues_col().update_one({"issue_id": issue_id}, {"$set": update_fields})

    # Send notification emails
    public_base_url = os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000")

    # Collect recipient emails (decrypt from stored encrypted values)
    recipients = set()
    try:
        recipients.add(decrypt_email(issue["reporter_email_enc"]))
    except Exception:
        pass

    issue_comments_list = list(comments_col().find({"issue_id": issue_id}))
    for comment in issue_comments_list:
        try:
            recipients.add(decrypt_email(comment["commenter_email_enc"]))
        except Exception:
            pass

    # Reload issue to get updated video path
    updated_issue = issues_col().find_one({"issue_id": issue_id})
    resolution_video_disk_path = upload_path_to_disk(updated_issue.get("admin_resolution_video_path"))
    resolution_video_link = (
        f"{public_base_url}{updated_issue['admin_resolution_video_path']}"
        if updated_issue.get("admin_resolution_video_path")
        else None
    )

    body_lines = [f"Update for issue: {issue['title']}", f"Status: {status}"]
    if update_message:
        body_lines.append(f"Admin update: {update_message}")
    if resolution_notes:
        body_lines.append(f"Resolution notes: {resolution_notes}")
    if resolution_video_link:
        body_lines.append(f"Resolution video: {resolution_video_link}")
    body_lines.append("Residents can now verify whether the issue was truly solved from the public portal.")

    attachments = [resolution_video_disk_path] if resolution_video_disk_path else []
    for recipient in recipients:
        send_email(recipient, f"Issue Update: {issue['title']}", "\n".join(body_lines), attachments=attachments)

    return load_dashboard_context(request, success="Status updated and community notifications sent.")
