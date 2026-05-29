# shared/database.py
import pathlib as _pathlib
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base

_DB_PATH = _pathlib.Path(__file__).resolve().parent.parent / "civic.db"
DATABASE_URL = f"sqlite:///{_DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}  # required for SQLite
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_database(base):
    base.metadata.create_all(bind=engine)

    inspector = inspect(engine)
    if "issues" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("issues")}
    issue_column_migrations = {
        "ward": "ALTER TABLE issues ADD COLUMN ward VARCHAR",
        "latitude": "ALTER TABLE issues ADD COLUMN latitude FLOAT",
        "longitude": "ALTER TABLE issues ADD COLUMN longitude FLOAT",
        "location_label": "ALTER TABLE issues ADD COLUMN location_label VARCHAR",
        "reporter_video_path": "ALTER TABLE issues ADD COLUMN reporter_video_path VARCHAR",
        "admin_resolution_video_path": "ALTER TABLE issues ADD COLUMN admin_resolution_video_path VARCHAR",
        "admin_resolution_notes": "ALTER TABLE issues ADD COLUMN admin_resolution_notes TEXT",
        "admin_resolution_latitude": "ALTER TABLE issues ADD COLUMN admin_resolution_latitude FLOAT",
        "admin_resolution_longitude": "ALTER TABLE issues ADD COLUMN admin_resolution_longitude FLOAT",
        "last_update_message": "ALTER TABLE issues ADD COLUMN last_update_message TEXT",
        "resolved_at": "ALTER TABLE issues ADD COLUMN resolved_at DATETIME",
        "escalation_notified_at": "ALTER TABLE issues ADD COLUMN escalation_notified_at DATETIME",
        "updated_at": "ALTER TABLE issues ADD COLUMN updated_at DATETIME",
    }

    with engine.begin() as connection:
        for column_name, statement in issue_column_migrations.items():
            if column_name not in existing_columns:
                connection.execute(text(statement))
