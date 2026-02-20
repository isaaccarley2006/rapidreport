import os
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Text, create_engine
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


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True)
    session_id = Column(String, nullable=False, index=True)
    role = Column(String, nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class LinkedInStat(Base):
    __tablename__ = "linkedin_stats"

    id = Column(Integer, primary_key=True)
    stat_text = Column(Text, nullable=False)
    source_name = Column(String, nullable=False)
    source_url = Column(String, nullable=True)
    date_verified = Column(String, nullable=False)
    category = Column(String, nullable=False)
    is_expired = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class LinkedInPost(Base):
    __tablename__ = "linkedin_posts"

    id = Column(Integer, primary_key=True)
    pillar = Column(String, nullable=False)
    audience = Column(String, nullable=False)
    template_type = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    status = Column(String, default="draft")
    scheduled_date = Column(String, nullable=True)
    scheduled_time = Column(String, default="07:45")
    performance_notes = Column(Text, nullable=True)
    is_recyclable = Column(Boolean, default=False)
    recycle_count = Column(Integer, default=0)
    parent_post_id = Column(Integer, ForeignKey("linkedin_posts.id"), nullable=True)
    report_id = Column(Integer, ForeignKey("reports.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class LinkedInWeek(Base):
    __tablename__ = "linkedin_weeks"

    id = Column(Integer, primary_key=True)
    week_start = Column(String, unique=True, nullable=False)
    monday_post_id = Column(Integer, ForeignKey("linkedin_posts.id"), nullable=True)
    tuesday_post_id = Column(Integer, ForeignKey("linkedin_posts.id"), nullable=True)
    wednesday_post_id = Column(Integer, ForeignKey("linkedin_posts.id"), nullable=True)
    thursday_post_id = Column(Integer, ForeignKey("linkedin_posts.id"), nullable=True)
    friday_post_id = Column(Integer, ForeignKey("linkedin_posts.id"), nullable=True)
    saturday_post_id = Column(Integer, ForeignKey("linkedin_posts.id"), nullable=True)
    sunday_post_id = Column(Integer, ForeignKey("linkedin_posts.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class NewsDigest(Base):
    __tablename__ = "news_digests"

    id = Column(Integer, primary_key=True)
    date = Column(Date, unique=True, nullable=False)
    raw_articles_json = Column(Text)
    summary = Column(Text)
    key_stats_json = Column(Text)
    post_angles_json = Column(Text)
    article_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


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


def seed_stats():
    """Populate LinkedInStat table with verified UK rental market stats if empty."""
    db = SessionLocal()
    if db.query(LinkedInStat).count() > 0:
        db.close()
        return

    stats = [
        # void_periods
        {"stat_text": "The average void period for UK rental properties is 21 days", "source_name": "ARLA Propertymark", "source_url": "https://www.propertymark.co.uk", "date_verified": "2024-09", "category": "void_periods"},
        {"stat_text": "A 21-day void period costs landlords an average of £1,077 in lost rent", "source_name": "ARLA Propertymark", "source_url": "https://www.propertymark.co.uk", "date_verified": "2024-09", "category": "void_periods"},
        {"stat_text": "London void periods average 15 days, the shortest in the UK", "source_name": "Goodlord Rental Index", "source_url": "https://www.goodlord.co", "date_verified": "2024-10", "category": "void_periods"},
        {"stat_text": "West Midlands void periods average 25 days, among the longest in England", "source_name": "Goodlord Rental Index", "source_url": "https://www.goodlord.co", "date_verified": "2024-10", "category": "void_periods"},

        # referencing
        {"stat_text": "Traditional tenant referencing takes 2-5 working days on average", "source_name": "NRLA", "source_url": "https://www.nrla.org.uk", "date_verified": "2024-08", "category": "referencing"},
        {"stat_text": "Complex referencing cases can extend to 3-10 working days", "source_name": "HomeLet", "source_url": "https://www.homelet.co.uk", "date_verified": "2024-08", "category": "referencing"},
        {"stat_text": "Referencing delays are the number one cause of tenancy start date slippage", "source_name": "Propertymark", "source_url": "https://www.propertymark.co.uk", "date_verified": "2024-07", "category": "referencing"},
        {"stat_text": "Goodlord reports 30% of references completed within 1 hour using digital processes", "source_name": "Goodlord", "source_url": "https://www.goodlord.co", "date_verified": "2024-06", "category": "referencing"},

        # market_scale
        {"stat_text": "4.7 million households rent privately in England, representing 19% of all households", "source_name": "English Housing Survey 2022-23", "source_url": "https://www.gov.uk/government/statistics/english-housing-survey-2022-to-2023-headline-report", "date_verified": "2024-07", "category": "market_scale"},
        {"stat_text": "There are approximately 2.3 million landlords in the UK", "source_name": "English Private Landlord Survey", "source_url": "https://www.gov.uk", "date_verified": "2024-03", "category": "market_scale"},
        {"stat_text": "45% of UK landlords own just one rental property", "source_name": "English Private Landlord Survey", "source_url": "https://www.gov.uk", "date_verified": "2024-03", "category": "market_scale"},
        {"stat_text": "HomeLet processes over 1 million tenant references per year in the UK", "source_name": "HomeLet", "source_url": "https://www.homelet.co.uk", "date_verified": "2024-05", "category": "market_scale"},
        {"stat_text": "The average UK rent reached £1,320 per month in Q3 2024", "source_name": "ONS Private Rental Index", "source_url": "https://www.ons.gov.uk", "date_verified": "2024-10", "category": "market_scale"},

        # renters_rights_act
        {"stat_text": "The Renters' Rights Bill received Royal Assent in October 2025", "source_name": "UK Parliament", "source_url": "https://bills.parliament.uk/bills/3764", "date_verified": "2025-10", "category": "renters_rights_act"},
        {"stat_text": "Section 21 'no-fault' evictions will be abolished from May 2026", "source_name": "UK Government", "source_url": "https://www.gov.uk", "date_verified": "2025-10", "category": "renters_rights_act"},
        {"stat_text": "All existing assured shorthold tenancies will convert to periodic tenancies under the new Act", "source_name": "UK Parliament", "source_url": "https://bills.parliament.uk/bills/3764", "date_verified": "2025-10", "category": "renters_rights_act"},
        {"stat_text": "The Renters' Rights Act is the biggest reform to private renting since the Housing Act 1988", "source_name": "Shelter", "source_url": "https://www.shelter.org.uk", "date_verified": "2025-10", "category": "renters_rights_act"},
        {"stat_text": "32,287 Section 21 eviction notices were issued in England in 2024", "source_name": "Ministry of Justice", "source_url": "https://www.gov.uk", "date_verified": "2025-01", "category": "renters_rights_act"},

        # tenant_behaviour
        {"stat_text": "The average tenancy length in England is 924 days (approximately 2.5 years)", "source_name": "Goodlord Rental Index", "source_url": "https://www.goodlord.co", "date_verified": "2024-10", "category": "tenant_behaviour"},
        {"stat_text": "The top reason tenants move is to find a larger property (19.1% of moves)", "source_name": "English Housing Survey 2022-23", "source_url": "https://www.gov.uk", "date_verified": "2024-07", "category": "tenant_behaviour"},
    ]

    for s in stats:
        db.add(LinkedInStat(**s))
    db.commit()
    db.close()
    print("  [seed] Populated stats bank with", len(stats), "verified UK rental market stats")
