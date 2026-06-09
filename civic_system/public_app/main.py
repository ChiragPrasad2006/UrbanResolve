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
    build_issue_severity,
    build_sla_status,
    build_verification_summary,
    build_ward_leaderboard,
    group_duplicate_hotspots,
)
from shared.database import (
    get_db,
    init_database,
    issues_col,
    comments_col,
    issue_votes_col,
    resolution_verifications_col,
    users_col,
    email_otps_col,
    next_issue_id,
)
from shared.email_utils import send_email
from shared.media_utils import save_upload
from shared.middleware import SecurityHeadersMiddleware, limiter
from shared.models import (
    make_comment,
    make_email_otp,
    make_issue,
    make_issue_vote,
    make_resolution_verification,
    make_user,
)
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
    hash_password,
    verify_password,
)

init_database()

BASE_DIR = Path(__file__).resolve().parent
app = FastAPI(title="CivicConnect - Public Portal")

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

def get_current_user(request: Request) -> str | None:
    """Extract user email from signed session cookie."""
    token = request.cookies.get("urbanresolve_user")
    if not token:
        return None
    return unsign_session(token)


def render_template(name: str, request: Request, context: dict):
    current_user = get_current_user(request)
    full_context = {
        "request": request,
        "current_user": current_user,
        "csrf_token": generate_csrf_token(),
    }
    full_context.update(context)
    return templates.TemplateResponse(request=request, name=name, context=full_context)


def ensure_public_user(email: str):
    email_h = hash_email(email)
    if not users_col().find_one({"email_hash": email_h}):
        username = email.split("@")[0]
        users_col().insert_one(make_user(
            email_hash=email_h,
            encrypted_email=encrypt_email(email),
            username=username,
            username_lower=username.lower(),
            password_hash="",
            role="public"
        ))


def build_issue_context(current_user: str | None = None):
    issues = list(issues_col().find({"is_public": True}).sort("created_at", -1))
    all_comments = list(comments_col().find().sort("created_at", 1))
    all_votes = list(issue_votes_col().find())
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
    sla_status = {
        issue["issue_id"]: build_sla_status(issue, issue_severity[issue["issue_id"]])
        for issue in issues
    }
    verification_summary = {
        issue["issue_id"]: build_verification_summary(issue_verifications.get(issue["issue_id"], []))
        for issue in issues
    }
    ward_leaderboard = build_ward_leaderboard(issues)

    issue_hotspots = {}
    for hotspot in hotspots:
        for hotspot_issue in hotspot["issues"]:
            issue_hotspots[hotspot_issue["issue_id"]] = hotspot

    issue_upvotes: dict[int, int] = {}
    user_upvotes: set[int] = set()
    current_user_hash = hash_email(current_user) if current_user else None
    for vote in all_votes:
        issue_upvotes[vote["issue_id"]] = issue_upvotes.get(vote["issue_id"], 0) + 1
        if current_user_hash and vote["voter_email_hash"] == current_user_hash:
            user_upvotes.add(vote["issue_id"])

    resolved_issues = [issue for issue in issues if issue["status"] == "Resolved"]
    active_issues = [issue for issue in issues if issue["status"] != "Resolved"]

    return {
        "issues": active_issues,
        "resolved_issues": resolved_issues,
        "issue_comments": issue_comments,
        "comment_counts": comment_counts,
        "issue_verifications": issue_verifications,
        "verification_summary": verification_summary,
        "ward_leaderboard": ward_leaderboard[:5],
        "issue_severity": issue_severity,
        "sla_status": sla_status,
        "issue_hotspots": issue_hotspots,
        "top_hotspots": hotspots[:5],
        "issue_upvotes": issue_upvotes,
        "user_upvotes": user_upvotes,
    }


def render_issue_feed(request: Request, **context):
    current_user = get_current_user(request)
    merged_context = build_issue_context(current_user=current_user)
    merged_context.update(context)
    return render_template("index.html", request, merged_context)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/")
def home(request: Request):
    return render_template("home.html", request, {})


@app.get("/issues")
def issues_page(request: Request, db: Database = Depends(get_db)):
    return render_issue_feed(request)


@app.get("/signup")
def signup_page(request: Request):
    return render_template("signup.html", request, {})


@app.post("/signup")
@limiter.limit("5/minute")
def signup_route(
    request: Request,
    email: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(""),
    db: Database = Depends(get_db)
):
    if not validate_csrf_token(csrf_token):
        return render_template("signup.html", request, {"error": "Invalid CSRF token. Please try again."})
        
    email = sanitize_input(email, max_length=254)
    username = sanitize_input(username, max_length=50)
    
    email_h = hash_email(email)
    username_lower = username.lower()
    
    existing_user = users_col().find_one({
        "$or": [
            {"email_hash": email_h},
            {"username_lower": username_lower}
        ]
    })
    
    if existing_user:
        return render_template(
            "signup.html", 
            request, 
            {"email": email, "username": username, "error": "Email or Username already exists."}
        )
        
    encrypted_email = encrypt_email(email)
    password_h = hash_password(password)
    
    users_col().insert_one(make_user(
        email_hash=email_h,
        encrypted_email=encrypted_email,
        username=username,
        username_lower=username_lower,
        password_hash=password_h,
        role="public"
    ))
    
    response = render_issue_feed(request, success="Account created successfully! You are now logged in.")
    response.set_cookie(
        key="urbanresolve_user",
        value=sign_session(email),
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
    )
    return response


@app.get("/login")
def login_page(request: Request):
    return render_template("login.html", request, {})


@app.post("/login")
@limiter.limit("5/minute")
def login_route(
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
    user = users_col().find_one({
        "$or": [
            {"email_hash": email_h},
            {"username_lower": identifier_lower}
        ]
    })
    
    if not user:
        return render_template("login.html", request, {"identifier": identifier, "error": "Invalid credentials."})
        
    if not user.get("password_hash") or not verify_password(password, user["password_hash"]):
        return render_template("login.html", request, {"identifier": identifier, "error": "Invalid credentials."})
        
    try:
        user_email = decrypt_email(user["encrypted_email"])
    except Exception:
        user_email = identifier if "@" in identifier else ""
        
    response = render_issue_feed(request, success="Login successful")
    response.set_cookie(
        key="urbanresolve_user",
        value=sign_session(user_email),
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
    )
    return response


@app.post("/login/request-otp")
@limiter.limit("5/minute")
def request_otp_route(request: Request, identifier: str = Form(...), csrf_token: str = Form(""), db: Database = Depends(get_db)):
    if not validate_csrf_token(csrf_token):
        return render_template("login.html", request, {"identifier": identifier, "error": "Invalid CSRF token."})
        
    identifier = sanitize_input(identifier, max_length=254)

    email_h = hash_email(identifier)
    user = users_col().find_one({
        "$or": [
            {"email_hash": email_h},
            {"username_lower": identifier.lower()}
        ]
    })
    
    if not user:
        return render_template("login.html", request, {"identifier": identifier, "error": "User not found."})

    try:
        email = decrypt_email(user["encrypted_email"])
    except Exception:
        email = identifier if "@" in identifier else ""
        if not email:
            return render_template("login.html", request, {"identifier": identifier, "error": "Email address missing for this user."})

    otp = generate_otp()
    otp_h = hash_otp(otp)
    email_h = hash_email(email)
    record = make_email_otp(
        email_hash=email_h,
        otp_hash=otp_h,
        expires_at=datetime.utcnow() + timedelta(minutes=5),
    )
    email_otps_col().insert_one(record)

    email_sent, email_message = send_email(email, "CivicConnect Login OTP", f"Your OTP is: {otp}\n\nValid for 5 minutes.")
    if not email_sent:
        return render_template(
            "login.html",
            request,
            {"identifier": identifier, "error": f"Could not send OTP email: {email_message}"},
        )
    return render_template(
        "login.html",
        request,
        {"identifier": identifier, "message": "OTP sent to your email", "otp_requested": True},
    )


@app.post("/login/verify-otp")
@limiter.limit("5/minute")
def verify_otp_route(
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
    user = users_col().find_one({
        "$or": [
            {"email_hash": email_h},
            {"username_lower": identifier.lower()}
        ]
    })
    
    if not user:
        return render_template("login.html", request, {"identifier": identifier, "error": "User not found.", "otp_requested": True})
        
    try:
        email = decrypt_email(user["encrypted_email"])
    except Exception:
        email = identifier if "@" in identifier else ""
        
    email_h = hash_email(email)

    record = email_otps_col().find_one(
        {"email_hash": email_h},
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

    ensure_public_user(email)

    response = render_issue_feed(request, success="Login successful")
    response.set_cookie(
        key="urbanresolve_user",
        value=sign_session(email),
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 8,
    )
    return response


@app.get("/logout")
def logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("urbanresolve_user")
    return response


@app.get("/report/new")
def report_page(request: Request):
    return render_template("report_new.html", request, {})


@app.post("/report/new")
@limiter.limit("5/minute")
def submit_report(
    request: Request,
    title: str = Form(...),
    category: str = Form(...),
    description: str = Form(""),
    address: str = Form(""),
    ward: str = Form(""),
    location_label: str = Form(""),
    latitude: str = Form(""),
    longitude: str = Form(""),
    email: str = Form(...),
    image: UploadFile = File(None),
    video: UploadFile = File(None),
    csrf_token: str = Form(""),
    db: Database = Depends(get_db),
):
    if not validate_csrf_token(csrf_token):
        return render_template("report_new.html", request, {"error": "Invalid CSRF token. Please try again."})
        
    # Sanitize inputs
    title = sanitize_input(title, max_length=200)
    category = sanitize_input(category, max_length=50)
    description = sanitize_input(description, max_length=5000)
    address = sanitize_input(address, max_length=500)
    ward = sanitize_input(ward, max_length=100)
    location_label = sanitize_input(location_label, max_length=200)
    email = sanitize_input(email, max_length=254)

    image_path = save_upload(image, "issue_images")
    reporter_video_path = save_upload(video, "issue_videos")

    issue_id = next_issue_id()
    issue_doc = make_issue(
        issue_id=issue_id,
        title=title,
        category=category,
        description=description,
        address=address,
        ward=ward,
        reporter_email_enc=encrypt_email(email),
        image_path=image_path,
        reporter_video_path=reporter_video_path,
        location_label=location_label or address,
        latitude=float(latitude) if latitude else None,
        longitude=float(longitude) if longitude else None,
    )
    issues_col().insert_one(issue_doc)
    ensure_public_user(email)

    context = build_issue_context()
    hotspot = context["issue_hotspots"].get(issue_id)
    duplicate_note = ""
    if hotspot and hotspot["count"] > 1:
        duplicate_note = f"\nThis report is part of a hotspot with {hotspot['count']} nearby similar complaints."

    public_base_url = os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000")
    body = (
        f"Your issue '{title}' has been submitted successfully.\n\n"
        f"Track it on the community feed: {public_base_url}/issues\n"
        f"Ward: {ward or 'Not specified'}\n"
        f"Location: {location_label or address or 'Not specified'}"
        f"{duplicate_note}"
    )
    send_email(email, "Issue Submitted Successfully", body)

    return render_template(
        "report_new.html",
        request,
        {"success": "Issue submitted successfully with media, location details, and hotspot detection."},
    )


@app.post("/issue/{issue_id}/comments")
@limiter.limit("10/minute")
def add_comment(
    issue_id: int,
    request: Request,
    body: str = Form(...),
    csrf_token: str = Form(""),
    db: Database = Depends(get_db),
):
    if not validate_csrf_token(csrf_token):
        return render_issue_feed(request, error="Invalid CSRF token.")
        
    current_user = get_current_user(request)
    if not current_user:
        return render_issue_feed(request, error="Please log in before commenting.")

    issue = issues_col().find_one({"issue_id": issue_id, "is_public": True})
    if not issue:
        return render_issue_feed(request, error="Issue not found.")

    body = sanitize_input(body, max_length=2000)
    commenter_name = current_user.split("@")[0].replace(".", " ").title()
    comment_doc = make_comment(
        issue_id=issue_id,
        commenter_name=commenter_name,
        commenter_email_enc=encrypt_email(current_user),
        body=body,
    )
    comments_col().insert_one(comment_doc)
    ensure_public_user(current_user)

    return render_issue_feed(request, success=f"Comment added for '{issue['title']}'.")


@app.post("/issue/{issue_id}/upvote")
@limiter.limit("20/minute")
def upvote_issue(
    request: Request,
    issue_id: int,
    csrf_token: str = Form(""),
    db: Database = Depends(get_db),
):
    if not validate_csrf_token(csrf_token):
        return render_issue_feed(request, error="Invalid CSRF token.")
        
    current_user = get_current_user(request)
    if not current_user:
        return render_issue_feed(request, error="Please log in to upvote issues.")

    issue = issues_col().find_one({"issue_id": issue_id, "is_public": True})
    if not issue:
        return render_issue_feed(request, error="Issue not found")

    voter_hash = hash_email(current_user)
    existing_vote = issue_votes_col().find_one({"issue_id": issue_id, "voter_email_hash": voter_hash})
    if not existing_vote:
        vote_doc = make_issue_vote(issue_id=issue_id, voter_email_hash=voter_hash)
        issue_votes_col().insert_one(vote_doc)

    return render_issue_feed(request, success=f"You upvoted '{issue['title']}'.")


@app.post("/issue/{issue_id}/verify-resolution")
@limiter.limit("5/minute")
def verify_resolution(
    issue_id: int,
    request: Request,
    verdict: str = Form(...),
    note: str = Form(""),
    image: UploadFile = File(None),
    csrf_token: str = Form(""),
    db: Database = Depends(get_db),
):
    if not validate_csrf_token(csrf_token):
        return render_issue_feed(request, error="Invalid CSRF token.")
        
    current_user = get_current_user(request)
    if not current_user:
        return render_issue_feed(request, error="Please log in to verify this resolution.")
        
    issue = issues_col().find_one({"issue_id": issue_id, "is_public": True})
    if not issue:
        return render_issue_feed(request, error="Issue not found.")

    if issue["status"] != "Resolved":
        return render_issue_feed(request, error="Citizen verification opens only after admins mark the issue as resolved.")

    try:
        user_doc = users_col().find_one({"email_hash": hash_email(current_user)})
        verifier_name = user_doc.get("username", "Citizen") if user_doc else "Citizen"
        verifier_email_enc = user_doc.get("encrypted_email", encrypt_email(current_user)) if user_doc else encrypt_email(current_user)
    except:
        verifier_name = "Citizen"
        verifier_email_enc = encrypt_email(current_user)

    verdict = sanitize_input(verdict, max_length=20)
    note = sanitize_input(note, max_length=2000)

    verification_doc = make_resolution_verification(
        issue_id=issue_id,
        verifier_name=verifier_name,
        verifier_email_enc=verifier_email_enc,
        verdict=verdict,
        note=note,
        image_path=save_upload(image, "verification_images"),
    )
    resolution_verifications_col().insert_one(verification_doc)

    return render_issue_feed(request, success="Resolution verification submitted.")

    return render_issue_feed(request, success=f"Verification recorded for '{issue['title']}'.")
