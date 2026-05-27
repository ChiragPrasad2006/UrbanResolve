# shared/models.py
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, Float, ForeignKey, UniqueConstraint
from datetime import datetime
from .database import Base


class User(Base):
    """
    Stores users for BOTH public and admin systems.
    role = 'public' or 'admin'
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True, nullable=False)
    role = Column(String, default="public")  # public | admin
    created_at = Column(DateTime, default=datetime.utcnow)


class Issue(Base):
    """
    Civic issues reported by users.
    Shared between public and admin portals.
    """
    __tablename__ = "issues"

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    category = Column(String, nullable=False)
    description = Column(Text)
    address = Column(String)
    ward = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    location_label = Column(String, nullable=True)
    priority = Column(Integer, default=3)
    status = Column(String, default="Pending")  # Pending / In Progress / Resolved
    is_public = Column(Boolean, default=True)
    reporter_email = Column(String, nullable=False)
    image_path = Column(String, nullable=True)
    reporter_video_path = Column(String, nullable=True)
    admin_resolution_video_path = Column(String, nullable=True)
    admin_resolution_notes = Column(Text, nullable=True)
    admin_resolution_latitude = Column(Float, nullable=True)
    admin_resolution_longitude = Column(Float, nullable=True)
    last_update_message = Column(Text, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    escalation_notified_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Comment(Base):
    """
    Community comments on an issue.
    """
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True)
    issue_id = Column(Integer, ForeignKey("issues.id"), nullable=False, index=True)
    commenter_name = Column(String, nullable=False)
    commenter_email = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class ResolutionVerification(Base):
    """
    Citizen confirmation about whether a reported fix is genuine.
    """
    __tablename__ = "resolution_verifications"

    id = Column(Integer, primary_key=True)
    issue_id = Column(Integer, ForeignKey("issues.id"), nullable=False, index=True)
    verifier_name = Column(String, nullable=False)
    verifier_email = Column(String, nullable=False)
    verdict = Column(String, nullable=False)  # solved | not_solved
    note = Column(Text, nullable=True)
    image_path = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class IssueVote(Base):
    """
    Track one upvote per logged-in user for a public issue.
    """
    __tablename__ = "issue_votes"
    __table_args__ = (
        UniqueConstraint("issue_id", "voter_email", name="unique_issue_vote"),
    )

    id = Column(Integer, primary_key=True)
    issue_id = Column(Integer, ForeignKey("issues.id"), nullable=False, index=True)
    voter_email = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class EmailOTP(Base):
    """
    Stores email OTPs for 2FA login (both public & admin).
    """
    __tablename__ = "email_otps"

    id = Column(Integer, primary_key=True)
    email = Column(String, index=True, nullable=False)
    otp = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False)

    def is_valid(self, input_otp: str) -> bool:
        return self.otp == input_otp and datetime.utcnow() < self.expires_at
