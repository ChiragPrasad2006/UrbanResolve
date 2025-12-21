# admin_app/main.py
from fastapi import FastAPI, Request, Depends, Form
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from fastapi.staticfiles import StaticFiles

from shared.database import engine, get_db
from shared.models import Base, Issue, EmailOTP, User
from shared.security import generate_otp
from shared.email_utils import send_email

Base.metadata.create_all(bind=engine)

app = FastAPI(title="UrbanResolve Login - Admin Portal")

app.mount("/static", StaticFiles(directory="admin_app/static"), name="static")
templates = Jinja2Templates(directory="admin_app/templates")

# ---------------- ADMIN LOGIN ----------------
@app.get("/login")
def admin_login_page(request: Request):
    return templates.TemplateResponse(
        "login.html",
        {"request": request}
    )

app.mount(
    "/uploads",
    StaticFiles(directory="shared/uploads"),
    name="uploads"
)

@app.post("/login/request-otp")
def admin_request_otp(
    request: Request,
    email: str = Form(...),
    db: Session = Depends(get_db)
):
    admin = db.query(User).filter(
        User.email == email,
        User.role == "admin"
    ).first()

    if not admin:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "Unauthorized admin email"
            }
        )

    otp = generate_otp()
    record = EmailOTP(
        email=email,
        otp=otp,
        expires_at=datetime.utcnow() + timedelta(minutes=5)
    )
    db.add(record)
    db.commit()

    send_email(
        email,
        "Admin Login OTP",
        f"Your admin OTP is: {otp}\nValid for 5 minutes."
    )

    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "email": email,
            "message": "OTP sent to admin email"
        }
    )

@app.post("/login/verify-otp")
def admin_verify_otp(
    request: Request,
    email: str = Form(...),
    otp: str = Form(...),
    db: Session = Depends(get_db)
):
    admin = db.query(User).filter(
        User.email == email,
        User.role == "admin"
    ).first()

    if not admin:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "Unauthorized admin"
            }
        )

    record = (
        db.query(EmailOTP)
        .filter(EmailOTP.email == email)
        .order_by(EmailOTP.id.desc())
        .first()
    )

    if not record or not record.is_valid(otp):
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "email": email,
                "error": "Invalid or expired OTP"
            }
        )

    issues = db.query(Issue).order_by(Issue.created_at.desc()).all()
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "issues": issues,
            "success": "Admin login successful"
        }
    )

# ---------------- ADMIN DASHBOARD ----------------
@app.get("/dashboard")
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    issues = db.query(Issue).order_by(Issue.created_at.desc()).all()
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "issues": issues}
    )

# ---------------- UPDATE ISSUE STATUS ----------------
@app.post("/issue/update")
def update_issue_status(
    request: Request,
    issue_id: int = Form(...),
    status: str = Form(...),
    db: Session = Depends(get_db)
):
    issue = db.query(Issue).filter(Issue.id == issue_id).first()

    if not issue:
        issues = db.query(Issue).order_by(Issue.created_at.desc()).all()
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "issues": issues,
                "error": "Issue not found"
            }
        )

    # Update status
    issue.status = status
    db.commit()

    # Notify public user
    send_email(
        issue.reporter_email,
        "Issue Status Updated",
        f"Your issue '{issue.title}' is now marked as '{status}'."
    )

    # Reload dashboard
    issues = db.query(Issue).order_by(Issue.created_at.desc()).all()
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "issues": issues,
            "success": "Status updated successfully"
        }
    )
    

