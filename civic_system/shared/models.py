# shared/models.py
"""
MongoDB document helpers.
Replaces SQLAlchemy ORM models with plain dict constructors
and Pydantic-like helper functions for document creation.

Each function returns a dict ready for pymongo insert_one().
"""

from datetime import datetime


def make_user(
    email_hash: str, 
    encrypted_email: str, 
    username: str, 
    username_lower: str, 
    password_hash: str, 
    role: str = "public"
) -> dict:
    """Create a User document."""
    return {
        "email_hash": email_hash,
        "encrypted_email": encrypted_email,
        "username": username,
        "username_lower": username_lower,
        "password_hash": password_hash,
        "role": role,
        "created_at": datetime.utcnow(),
    }


def make_issue(
    issue_id: int,
    title: str,
    category: str,
    reporter_email_enc: str,
    description: str = "",
    address: str = "",
    ward: str = "",
    location_label: str = "",
    latitude: float | None = None,
    longitude: float | None = None,
    image_path: str | None = None,
    reporter_video_path: str | None = None,
    is_public: bool = True,
    status: str = "Pending",
    created_at: datetime | None = None,
) -> dict:
    """Create an Issue document."""
    now = datetime.utcnow()
    return {
        "issue_id": issue_id,
        "title": title,
        "category": category,
        "description": description,
        "address": address,
        "ward": ward,
        "latitude": latitude,
        "longitude": longitude,
        "location_label": location_label,
        "priority": 3,
        "status": status,
        "is_public": is_public,
        "reporter_email_enc": reporter_email_enc,
        "image_path": image_path,
        "reporter_video_path": reporter_video_path,
        "admin_resolution_video_path": None,
        "admin_resolution_notes": None,
        "admin_resolution_latitude": None,
        "admin_resolution_longitude": None,
        "last_update_message": None,
        "resolved_at": None,
        "escalation_notified_at": None,
        "created_at": created_at or now,
        "updated_at": now,
    }


def make_comment(
    issue_id: int,
    commenter_name: str,
    commenter_email_enc: str,
    body: str,
) -> dict:
    """Create a Comment document."""
    return {
        "issue_id": issue_id,
        "commenter_name": commenter_name,
        "commenter_email_enc": commenter_email_enc,
        "body": body,
        "created_at": datetime.utcnow(),
    }


def make_resolution_verification(
    issue_id: int,
    verifier_name: str,
    verifier_email_enc: str,
    verdict: str,
    note: str = "",
    image_path: str | None = None,
) -> dict:
    """Create a ResolutionVerification document."""
    return {
        "issue_id": issue_id,
        "verifier_name": verifier_name,
        "verifier_email_enc": verifier_email_enc,
        "verdict": verdict,
        "note": note,
        "image_path": image_path,
        "created_at": datetime.utcnow(),
    }


def make_issue_vote(issue_id: int, voter_email_hash: str) -> dict:
    """Create an IssueVote document."""
    return {
        "issue_id": issue_id,
        "voter_email_hash": voter_email_hash,
        "created_at": datetime.utcnow(),
    }


def make_email_otp(email_hash: str, otp_hash: str, expires_at: datetime) -> dict:
    """Create an EmailOTP document with hashed email and hashed OTP."""
    return {
        "email_hash": email_hash,
        "otp_hash": otp_hash,
        "expires_at": expires_at,
    }
