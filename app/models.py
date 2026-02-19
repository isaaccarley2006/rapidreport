import os
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

import config


class Base(DeclarativeBase):
    pass


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True)
    week_start = Column(String, nullable=False)
    week_end = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    tasks_json = Column(Text, nullable=False, default="[]")
    emails_json = Column(Text, nullable=False, default="[]")
    summary_text = Column(Text, nullable=False, default="")
    upcoming_tasks_json = Column(Text, nullable=False, default="[]")
    suggestions_text = Column(Text, nullable=False, default="")


engine = create_engine(config.DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


def init_db():
    db_url = config.DATABASE_URL
    if db_url.startswith("sqlite:///"):
        db_path = db_url.replace("sqlite:///", "")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
    Base.metadata.create_all(engine)


def get_session() -> Session:
    return SessionLocal()
