# shared/database.py
"""
MongoDB connection manager.
Replaces the previous SQLAlchemy/SQLite setup with pymongo.
"""

import os

from pymongo import MongoClient, ASCENDING
from pymongo.database import Database
from pymongo.collection import Collection

# ---------------------------------------------------------------------------
# Load .env files so MONGO_URI works even without shell exports
# ---------------------------------------------------------------------------

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv:
    _project_env = os.path.join(os.path.dirname(__file__), "..", ".env")
    _project_env = os.path.abspath(_project_env)
    if os.path.exists(_project_env):
        load_dotenv(_project_env, override=False)

# ---------------------------------------------------------------------------
# MongoDB client and database
# ---------------------------------------------------------------------------

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "urbanresolve")

_client: MongoClient | None = None
_db: Database | None = None


def get_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    return _client


def get_database() -> Database:
    global _db
    if _db is None:
        _db = get_client()[MONGO_DB_NAME]
    return _db


def get_db() -> Database:
    """
    FastAPI dependency — yields the MongoDB database handle.
    Compatible with `Depends(get_db)`.
    """
    yield get_database()


# ---------------------------------------------------------------------------
# Collection accessors (convenience)
# ---------------------------------------------------------------------------

def users_col() -> Collection:
    return get_database()["users"]


def issues_col() -> Collection:
    return get_database()["issues"]


def comments_col() -> Collection:
    return get_database()["comments"]


def resolution_verifications_col() -> Collection:
    return get_database()["resolution_verifications"]


def issue_votes_col() -> Collection:
    return get_database()["issue_votes"]


def email_otps_col() -> Collection:
    return get_database()["email_otps"]


def counters_col() -> Collection:
    return get_database()["counters"]


# ---------------------------------------------------------------------------
# Index creation (replaces SQLAlchemy metadata.create_all)
# ---------------------------------------------------------------------------

def init_database():
    """
    Creates MongoDB indexes for performance and uniqueness constraints.
    Safe to call multiple times (MongoDB ignores duplicate index creation).
    """
    db = get_database()

    # Users — unique email hash
    db["users"].create_index("email_hash", unique=True)

    # Issues — ascending by created_at for feed ordering
    db["issues"].create_index([("created_at", ASCENDING)])
    db["issues"].create_index("issue_id", unique=True)

    # Comments — by issue_id for fast lookups
    db["comments"].create_index("issue_id")

    # Resolution verifications — by issue_id
    db["resolution_verifications"].create_index("issue_id")

    # Issue votes — unique compound index (one vote per user per issue)
    db["issue_votes"].create_index(
        [("issue_id", ASCENDING), ("voter_email_hash", ASCENDING)],
        unique=True,
    )

    # Email OTPs — by email hash for lookups, TTL for auto-expiry
    db["email_otps"].create_index("email_hash")
    db["email_otps"].create_index("expires_at", expireAfterSeconds=0)

    # Counters collection for auto-incrementing IDs
    if db["counters"].find_one({"_id": "issue_id"}) is None:
        db["counters"].insert_one({"_id": "issue_id", "seq": 0})


def next_issue_id() -> int:
    """
    Atomically increment and return the next issue ID.
    """
    result = counters_col().find_one_and_update(
        {"_id": "issue_id"},
        {"$inc": {"seq": 1}},
        return_document=True,
    )
    return result["seq"]
