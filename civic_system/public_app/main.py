# public_app/main.py
from fastapi import FastAPI, Request, Depends, Form
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from fastapi import UploadFile, File
import shutil
import os
from fastapi.staticfiles import StaticFiles

from shared.database import engine, get_db
from shared.models import Base, Issue, EmailOTP
from shared.security import generate_otp
from shared.email_utils import send_email

# Create tables (shared DB)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="CivicConnect - Public Portal")

# Static & templates
app.mount("/static", StaticFiles(directory="public_app/static"), name="static")
templates = Jinja2Templates(directory="public_app/templates")

app.mount(
    "/uploads",
    StaticFiles(directory="shared/uploads"),
    name="uploads"
)
# ---------------- HOME / FEED ----------------
@app.get("/")
def home(request: Request, db: Session = Depends(get_db)):
    issues = db.query(Issue).filter(Issue.is_public == True).order_by(Issue.created_at.desc()).all()
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "issues": issues}
    )

# ---------------- LOGIN (EMAIL OTP) ----------------
@app.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse(
        "login.html",
        {"request": request}
    )

@app.post("/login/request-otp")
def request_otp(
    request: Request,
    email: str = Form(...),
    db: Session = Depends(get_db)
):
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
        "CivicConnect Login OTP",
        f"Your OTP is: {otp}\n\nValid for 5 minutes."
    )

    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "email": email,
            "message": "OTP sent to your email"
        }
    )

@app.post("/login/verify-otp")
def verify_otp(
    request: Request,
    email: str = Form(...),
    otp: str = Form(...),
    db: Session = Depends(get_db)
):
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

    # Successful login → redirect to home
    issues = db.query(Issue).filter(Issue.is_public == True).all()
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "issues": issues, "success": "Login successful"}
    )

# ---------------- REPORT ISSUE ----------------
@app.get("/report/new")
def report_page(request: Request):
    return templates.TemplateResponse(
        "report_new.html",
        {"request": request}
    )

@app.post("/report/new")
def submit_report(
    request: Request,
    title: str = Form(...),
    category: str = Form(...),
    description: str = Form(""),
    address: str = Form(""),
    email: str = Form(...),
    image: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    image_path = None

    if image:
        upload_dir = "shared/uploads"
        os.makedirs(upload_dir, exist_ok=True)

        file_path = os.path.join(upload_dir, image.filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)

        image_path = f"/uploads/{image.filename}"   

    issue = Issue(
        title=title,
        category=category,
        description=description,
        address=address,
        reporter_email=email,
        image_path=image_path
    )

    db.add(issue)
    db.commit()

    send_email(
        email,
        "Issue Submitted Successfully",
        f"Your issue '{title}' has been submitted."
    )

    return templates.TemplateResponse(
        "report_new.html",
        {
            "request": request,
            "success": "Issue submitted successfully!"
        }
    )

