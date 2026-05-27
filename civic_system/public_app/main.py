import os
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from shared.analytics import (
    build_issue_severity,
    build_sla_status,
    build_verification_summary,
    build_ward_leaderboard,
    group_duplicate_hotspots,
)
from shared.database import get_db, init_database
from shared.email_utils import send_email
from shared.media_utils import save_upload
from shared.models import Base, Comment, EmailOTP, Issue, IssueVote, ResolutionVerification, User
from shared.security import generate_otp

init_database(Base)

BASE_DIR = Path(__file__).resolve().parent
app = FastAPI(title="CivicConnect - Public Portal")

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/uploads", StaticFiles(directory=str(BASE_DIR.parent / "shared" / "uploads")), name="uploads")


def render_template(name: str, request: Request, context: dict):
    full_context = {
        "request": request,
        "current_user": request.cookies.get("urbanresolve_user"),
    }
    full_context.update(context)
    return templates.TemplateResponse(request=request, name=name, context=full_context)


def ensure_public_user(email: str, db: Session):
    existing_user = db.query(User).filter(User.email == email).first()
    if not existing_user:
        db.add(User(email=email, role="public"))
        db.commit()


def build_issue_context(db: Session, current_user: str | None = None):
    issues = db.query(Issue).filter(Issue.is_public == True).order_by(Issue.created_at.desc()).all()
    comments = db.query(Comment).order_by(Comment.created_at.asc()).all()
    votes = db.query(IssueVote).all()
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
    sla_status = {
        issue.id: build_sla_status(issue, issue_severity[issue.id])
        for issue in issues
    }
    verification_summary = {
        issue.id: build_verification_summary(issue_verifications.get(issue.id, []))
        for issue in issues
    }
    ward_leaderboard = build_ward_leaderboard(issues)

    issue_hotspots = {}
    for hotspot in hotspots:
        for hotspot_issue in hotspot["issues"]:
            issue_hotspots[hotspot_issue.id] = hotspot

    issue_upvotes: dict[int, int] = {}
    user_upvotes: set[int] = set()
    for vote in votes:
        issue_upvotes[vote.issue_id] = issue_upvotes.get(vote.issue_id, 0) + 1
        if current_user and vote.voter_email == current_user:
            user_upvotes.add(vote.issue_id)

    resolved_issues = [issue for issue in issues if issue.status == "Resolved"]
    active_issues = [issue for issue in issues if issue.status != "Resolved"]

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


def render_issue_feed(request: Request, db: Session, **context):
    current_user = request.cookies.get("urbanresolve_user")
    merged_context = build_issue_context(db, current_user=current_user)
    merged_context.update(context)
    return render_template("index.html", request, merged_context)


@app.get("/")
def home(request: Request):
    return render_template("home.html", request, {})


@app.get("/issues")
def issues_page(request: Request, db: Session = Depends(get_db)):
    return render_issue_feed(request, db)


@app.get("/login")
def login_page(request: Request):
    return render_template("login.html", request, {})


@app.post("/login/request-otp")
def request_otp(request: Request, email: str = Form(...), db: Session = Depends(get_db)):
    otp = generate_otp()
    record = EmailOTP(email=email, otp=otp, expires_at=datetime.utcnow() + timedelta(minutes=5))
    db.add(record)
    db.commit()

    send_email(email, "CivicConnect Login OTP", f"Your OTP is: {otp}\n\nValid for 5 minutes.")
    return render_template(
        "login.html",
        request,
        {"email": email, "message": "OTP sent to your email", "otp_requested": True}
    )


@app.post("/login/verify-otp")
def verify_otp(request: Request, email: str = Form(...), otp: str = Form(...), db: Session = Depends(get_db)):
    record = db.query(EmailOTP).filter(EmailOTP.email == email).order_by(EmailOTP.id.desc()).first()
    if not record or not record.is_valid(otp):
        return render_template(
            "login.html",
            request,
            {"email": email, "error": "Invalid or expired OTP", "otp_requested": True}
        )
    response = render_issue_feed(request, db, success="Login successful")
    response.set_cookie(
        key="urbanresolve_user",
        value=email,
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
    db: Session = Depends(get_db)
):
    image_path = save_upload(image, "issue_images")
    reporter_video_path = save_upload(video, "issue_videos")

    issue = Issue(
        title=title,
        category=category,
        description=description,
        address=address,
        ward=ward,
        reporter_email=email,
        image_path=image_path,
        reporter_video_path=reporter_video_path,
        location_label=location_label or address,
        latitude=float(latitude) if latitude else None,
        longitude=float(longitude) if longitude else None,
    )

    db.add(issue)
    db.commit()
    db.refresh(issue)
    ensure_public_user(email, db)

    context = build_issue_context(db)
    hotspot = context["issue_hotspots"].get(issue.id)
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
        {"success": "Issue submitted successfully with media, location details, and hotspot detection."}
    )


@app.post("/issue/{issue_id}/comments")
def add_comment(
    issue_id: int,
    request: Request,
    body: str = Form(...),
    db: Session = Depends(get_db)
):
    current_user = request.cookies.get("urbanresolve_user")
    if not current_user:
        return render_issue_feed(request, db, error="Please log in before commenting.")

    issue = db.query(Issue).filter(Issue.id == issue_id, Issue.is_public == True).first()
    if not issue:
        return render_issue_feed(request, db, error="Issue not found.")

    commenter_name = current_user.split("@")[0].replace('.', ' ').title()
    comment = Comment(issue_id=issue.id, commenter_name=commenter_name, commenter_email=current_user, body=body)
    db.add(comment)
    db.commit()
    ensure_public_user(current_user, db)

    return render_issue_feed(request, db, success=f"Comment added for '{issue.title}'.")


@app.post("/issue/{issue_id}/upvote")
def upvote_issue(
    request: Request,
    issue_id: int,
    db: Session = Depends(get_db)
):
    current_user = request.cookies.get("urbanresolve_user")
    if not current_user:
        return render_issue_feed(request, db, error="Please log in to upvote issues.")

    issue = db.query(Issue).filter(Issue.id == issue_id, Issue.is_public == True).first()
    if not issue:
        return render_issue_feed(request, db, error="Issue not found")

    existing_vote = db.query(IssueVote).filter(IssueVote.issue_id == issue_id, IssueVote.voter_email == current_user).first()
    if not existing_vote:
        db.add(IssueVote(issue_id=issue_id, voter_email=current_user))
        db.commit()

    return render_issue_feed(request, db, success=f"You upvoted '{issue.title}'.")


@app.post("/issue/{issue_id}/verify-resolution")
def verify_resolution(
    issue_id: int,
    request: Request,
    verifier_name: str = Form(...),
    verifier_email: str = Form(...),
    verdict: str = Form(...),
    note: str = Form(""),
    image: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    issue = db.query(Issue).filter(Issue.id == issue_id, Issue.is_public == True).first()
    if not issue:
        return render_issue_feed(request, db, error="Issue not found.")

    if issue.status != "Resolved":
        return render_issue_feed(request, db, error="Citizen verification opens only after admins mark the issue as resolved.")

    verification = ResolutionVerification(
        issue_id=issue.id,
        verifier_name=verifier_name,
        verifier_email=verifier_email,
        verdict=verdict,
        note=note,
        image_path=save_upload(image, "verification_images")
    )
    db.add(verification)
    db.commit()
    ensure_public_user(verifier_email, db)

    return render_issue_feed(request, db, success=f"Verification recorded for '{issue.title}'.")
