import os
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from shared.analytics import (
    build_heatmap_data,
    build_issue_severity,
    build_sla_status,
    build_verification_summary,
    group_duplicate_hotspots,
)
from shared.database import get_db, init_database
from shared.email_utils import send_email
from shared.media_utils import distance_in_meters, save_upload, upload_path_to_disk
from shared.models import Base, Comment, EmailOTP, Issue, ResolutionVerification, User
from shared.security import generate_otp

init_database(Base)

BASE_DIR = Path(__file__).resolve().parent
app = FastAPI(title="UrbanResolve Login - Admin Portal")

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/uploads", StaticFiles(directory=str(BASE_DIR.parent / "shared" / "uploads")), name="uploads")


def render_template(name: str, request: Request, context: dict):
    full_context = {
        "request": request,
        "current_admin": request.cookies.get("urbanresolve_admin"),
    }
    full_context.update(context)
    return templates.TemplateResponse(request=request, name=name, context=full_context)


def send_escalation_if_needed(issue: Issue, severity_score: float, sla_status: dict, verification_summary: dict, db: Session):
    escalation_email = os.getenv("ESCALATION_EMAIL")
    if not escalation_email or not sla_status["overdue"] or issue.escalation_notified_at is not None:
        return

    body_lines = [
        f"Issue '{issue.title}' requires escalation.",
        f"Category: {issue.category}",
        f"Ward: {issue.ward or 'Unassigned'}",
        f"Severity score: {severity_score}",
        f"SLA allowed hours: {sla_status['allowed_hours']}",
        f"Elapsed hours: {sla_status['elapsed_hours']}",
        f"Community not solved confirmations: {verification_summary.get('not_solved', 0)}",
    ]
    send_email(escalation_email, f"Escalation Required: {issue.title}", "\n".join(body_lines))
    issue.escalation_notified_at = datetime.utcnow()
    db.commit()


def load_dashboard_context(request: Request, db: Session, **context):
    issues = db.query(Issue).order_by(Issue.created_at.desc()).all()
    comments = db.query(Comment).order_by(Comment.created_at.asc()).all()
    verifications = db.query(ResolutionVerification).order_by(ResolutionVerification.created_at.desc()).all()

    issue_comments: dict[int, list[Comment]] = {}
    for comment in comments:
        issue_comments.setdefault(comment.issue_id, []).append(comment)
    comment_counts = {issue.id: len(issue_comments.get(issue.id, [])) for issue in issues}

    issue_verifications: dict[int, list[ResolutionVerification]] = {}
    for verification in verifications:
        issue_verifications.setdefault(verification.issue_id, []).append(verification)

    hotspots = group_duplicate_hotspots(issues, comment_counts)
    issue_severity = {
        issue.id: build_issue_severity(issue, comment_counts.get(issue.id, 0), hotspots)
        for issue in issues
    }
    issues.sort(key=lambda issue: (issue.status == "Resolved", -issue_severity[issue.id], issue.created_at), reverse=False)
    sla_status = {issue.id: build_sla_status(issue, issue_severity[issue.id]) for issue in issues}
    verification_summary = {
        issue.id: build_verification_summary(issue_verifications.get(issue.id, []))
        for issue in issues
    }

    for issue in issues:
        send_escalation_if_needed(
            issue,
            issue_severity[issue.id],
            sla_status[issue.id],
            verification_summary[issue.id],
            db
        )

    heatmap_points = build_heatmap_data(issues, comment_counts)
    issue_hotspots = {}
    for hotspot in hotspots:
        for hotspot_issue in hotspot["issues"]:
            issue_hotspots[hotspot_issue.id] = hotspot

    active_issues = [issue for issue in issues if issue.status != "Resolved"]
    resolved_issues = [issue for issue in issues if issue.status == "Resolved"]

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


@app.get("/")
def admin_root():
    return RedirectResponse(url="/login", status_code=307)


@app.get("/login")
def admin_login_page(request: Request):
    return render_template("login.html", request, {})


@app.post("/login/request-otp")
def admin_request_otp(request: Request, email: str = Form(...), db: Session = Depends(get_db)):
    admin = db.query(User).filter(User.email == email, User.role == "admin").first()
    if not admin:
        return render_template("login.html", request, {"email": email, "error": "Unauthorized admin email"})

    otp = generate_otp()
    record = EmailOTP(email=email, otp=otp, expires_at=datetime.utcnow() + timedelta(minutes=5))
    db.add(record)
    db.commit()

    send_email(email, "Admin Login OTP", f"Your admin OTP is: {otp}\nValid for 5 minutes.")
    return render_template(
        "login.html",
        request,
        {"email": email, "message": "OTP sent to admin email", "otp_requested": True}
    )


@app.post("/login/verify-otp")
def admin_verify_otp(request: Request, email: str = Form(...), otp: str = Form(...), db: Session = Depends(get_db)):
    admin = db.query(User).filter(User.email == email, User.role == "admin").first()
    if not admin:
        return render_template("login.html", request, {"error": "Unauthorized admin"})

    record = db.query(EmailOTP).filter(EmailOTP.email == email).order_by(EmailOTP.id.desc()).first()
    if not record or not record.is_valid(otp):
        return render_template(
            "login.html",
            request,
            {"email": email, "error": "Invalid or expired OTP", "otp_requested": True}
        )

    response = load_dashboard_context(request, db, success="Admin login successful")
    response.set_cookie(
        key="urbanresolve_admin",
        value=email,
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
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    return load_dashboard_context(request, db)


@app.post("/issue/update")
def update_issue_status(
    request: Request,
    issue_id: int = Form(...),
    status: str = Form(...),
    update_message: str = Form(""),
    resolution_notes: str = Form(""),
    resolution_latitude: str = Form(""),
    resolution_longitude: str = Form(""),
    resolution_video: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    issue = db.query(Issue).filter(Issue.id == issue_id).first()
    if not issue:
        return load_dashboard_context(request, db, error="Issue not found")

    parsed_resolution_latitude = float(resolution_latitude) if resolution_latitude else None
    parsed_resolution_longitude = float(resolution_longitude) if resolution_longitude else None

    if resolution_video and issue.latitude is not None and issue.longitude is not None:
        if parsed_resolution_latitude is None or parsed_resolution_longitude is None:
            return load_dashboard_context(
                request,
                db,
                error="Select the on-site resolution location on the map before uploading the fix video."
            )

        distance = distance_in_meters(
            issue.latitude,
            issue.longitude,
            parsed_resolution_latitude,
            parsed_resolution_longitude
        )
        if distance > 300:
            return load_dashboard_context(
                request,
                db,
                error="Resolution evidence must be uploaded within 300 meters of the original issue location."
            )

    resolution_video_path = save_upload(resolution_video, "resolution_videos")
    if resolution_video_path:
        issue.admin_resolution_video_path = resolution_video_path

    previous_status = issue.status
    issue.status = status
    issue.last_update_message = update_message
    issue.admin_resolution_notes = resolution_notes
    issue.admin_resolution_latitude = parsed_resolution_latitude
    issue.admin_resolution_longitude = parsed_resolution_longitude
    if status == "Resolved" and previous_status != "Resolved":
        issue.resolved_at = datetime.utcnow()
    elif status != "Resolved":
        issue.resolved_at = None
    db.commit()

    public_base_url = os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000")
    recipients = {issue.reporter_email}
    recipients.update(comment.commenter_email for comment in db.query(Comment).filter(Comment.issue_id == issue.id).all())

    resolution_video_disk_path = upload_path_to_disk(issue.admin_resolution_video_path)
    resolution_video_link = f"{public_base_url}{issue.admin_resolution_video_path}" if issue.admin_resolution_video_path else None

    body_lines = [f"Update for issue: {issue.title}", f"Status: {issue.status}"]
    if update_message:
        body_lines.append(f"Admin update: {update_message}")
    if resolution_notes:
        body_lines.append(f"Resolution notes: {resolution_notes}")
    if resolution_video_link:
        body_lines.append(f"Resolution video: {resolution_video_link}")
    body_lines.append("Residents can now verify whether the issue was truly solved from the public portal.")

    attachments = [resolution_video_disk_path] if resolution_video_disk_path else []
    for recipient in recipients:
        send_email(recipient, f"Issue Update: {issue.title}", "\n".join(body_lines), attachments=attachments)

    return load_dashboard_context(request, db, success="Status updated and community notifications sent.")
