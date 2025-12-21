# shared/models.py
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
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
    priority = Column(Integer, default=3)
    status = Column(String, default="Pending")  # Pending / In Progress / Resolved
    is_public = Column(Boolean, default=True)
    reporter_email = Column(String, nullable=False)
    image_path = Column(String, nullable=True)
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
