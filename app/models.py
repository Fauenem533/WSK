from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, DateTime, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from app.database import Base


class Runner(Base):
    __tablename__ = "runners"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    name_normalized = Column(String, nullable=False, index=True)
    gender = Column(String(1), nullable=False, default="M")
    club = Column(String, default="")
    city = Column(String, default="")

    results = relationship("Result", back_populates="runner", lazy="selectin")

    __table_args__ = (
        Index("ix_runners_name_norm", "name_normalized"),
    )


class Result(Base):
    __tablename__ = "results"

    id = Column(Integer, primary_key=True, index=True)
    runner_id = Column(Integer, ForeignKey("runners.id"), nullable=False)
    race_id = Column(String, nullable=False)  # pol, set, cw, bonk, mar
    place = Column(Integer)
    category = Column(String, default="")
    time_str = Column(String, default="DNF")
    time_seconds = Column(Float, nullable=True)

    runner = relationship("Runner", back_populates="results")

    __table_args__ = (
        UniqueConstraint("runner_id", "race_id", name="uq_runner_race"),
        Index("ix_results_race", "race_id"),
    )


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    username = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    notify_new_results = Column(Boolean, default=True)

    favorites = relationship("Favorite", back_populates="user", lazy="selectin")


class Favorite(Base):
    __tablename__ = "favorites"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    runner_id = Column(Integer, ForeignKey("runners.id"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="favorites")
    runner = relationship("Runner")

    __table_args__ = (
        UniqueConstraint("user_id", "runner_id", name="uq_user_runner"),
    )


class ScrapeLog(Base):
    __tablename__ = "scrape_logs"

    id = Column(Integer, primary_key=True, index=True)
    race_id = Column(String, nullable=False)
    status = Column(String, nullable=False)  # success, error
    runners_count = Column(Integer, default=0)
    message = Column(String, default="")
    scraped_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
