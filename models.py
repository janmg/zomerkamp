"""SQLAlchemy models for the merged Zomerkamp roster application."""

from __future__ import annotations

from datetime import time as dt_time

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, Text, Time, UniqueConstraint, create_engine, func
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker

from config import DATABASE_URL, PREFERENCES, TIME_BLOCKS

MESSAGING_APPS = ["whatsapp", "signal", "telegram", "sms", "none"]
GROUPS = ["1", "2", "3a", "3b", "4", "5", "6+7", "8"]


class Base(DeclarativeBase):
    pass


class Participant(Base):
    __tablename__ = "participants"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(150), nullable=False)
    email = Column(String(254), nullable=False, unique=True, index=True)
    phone = Column(String(50), nullable=True)
    remarks = Column(Text, nullable=True)

    day1_morning = Column(Boolean, default=False)
    day1_afternoon = Column(Boolean, default=False)
    day1_evening = Column(Boolean, default=False)
    day2_morning = Column(Boolean, default=False)
    day2_afternoon = Column(Boolean, default=False)
    day2_evening = Column(Boolean, default=False)
    day3_morning = Column(Boolean, default=False)
    day3_afternoon = Column(Boolean, default=False)
    day3_evening = Column(Boolean, default=False)
    day4_morning = Column(Boolean, default=False)
    day4_afternoon = Column(Boolean, default=False)
    day4_evening = Column(Boolean, default=False)

    preference = Column(
        Enum(*PREFERENCES, name="preference_enum"),
        nullable=False,
        default="do not care",
    )
    messaging = Column(
        Enum(*MESSAGING_APPS, name="messaging_enum"),
        nullable=False,
        default="whatsapp",
        server_default="whatsapp",
    )
    group = Column(
        String(100),
        nullable=True,
        default=None,
    )
    excluded_all_days = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())

    assignments = relationship("Assignment", back_populates="participant", cascade="all, delete-orphan")
    unavailabilities = relationship("Unavailability", back_populates="participant", cascade="all, delete-orphan")
    availability_entries = relationship("Availability", back_populates="participant", cascade="all, delete-orphan")

    def get_block_availability(self, day: int, time_block: str) -> bool:
        entry = next(
            (
                availability
                for availability in self.availability_entries
                if availability.day == day and availability.time_block == time_block
            ),
            None,
        )
        if entry is not None:
            return bool(entry.available)
        return bool(getattr(self, f"day{day}_{time_block}", False))

    def set_block_availability(self, day: int, time_block: str, available: bool) -> None:
        setattr(self, f"day{day}_{time_block}", available)
        entry = next(
            (
                availability
                for availability in self.availability_entries
                if availability.day == day and availability.time_block == time_block
            ),
            None,
        )
        if entry is None:
            entry = Availability(day=day, time_block=time_block, available=available)
            self.availability_entries.append(entry)
        else:
            entry.available = available


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        UniqueConstraint("day", "begin_time", "name", name="uq_task_day_begin_name"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    day = Column(Integer, nullable=False)
    begin_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    points = Column(Integer, nullable=False, default=1)
    people_required = Column(Integer, nullable=False, default=1)
    time_block = Column(Enum(*TIME_BLOCKS, name="time_block_enum"), nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    assignments = relationship("Assignment", back_populates="task", cascade="all, delete-orphan")
    unavailabilities = relationship("Unavailability", back_populates="task", cascade="all, delete-orphan")

    @property
    def task_name(self) -> str:
        return self.name

    @task_name.setter
    def task_name(self, value: str) -> None:
        self.name = value


class Assignment(Base):
    __tablename__ = "assignments"
    __table_args__ = (
        UniqueConstraint("task_id", "participant_id", name="uq_task_participant"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    participant_id = Column(Integer, ForeignKey("participants.id", ondelete="CASCADE"), nullable=False)
    role = Column(Enum("lead", "helper", "backup", name="role_enum"), nullable=False, default="helper")
    points_awarded = Column(Integer, nullable=False, default=0)
    confirmed = Column(Boolean, default=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    task = relationship("Task", back_populates="assignments")
    participant = relationship("Participant", back_populates="assignments")

    @property
    def is_lead(self) -> bool:
        return self.role == "lead"

    @property
    def is_backup(self) -> bool:
        return self.role == "backup"

    @property
    def points_earned(self) -> int:
        return self.points_awarded


class Availability(Base):
    __tablename__ = "availability"
    __table_args__ = (
        UniqueConstraint("participant_id", "day", "time_block", name="uq_participant_day_block"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    participant_id = Column(Integer, ForeignKey("participants.id", ondelete="CASCADE"), nullable=False)
    day = Column(Integer, nullable=False)
    time_block = Column(Enum(*TIME_BLOCKS, name="availability_block_enum"), nullable=False)
    available = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, server_default=func.now())

    participant = relationship("Participant", back_populates="availability_entries")


class Unavailability(Base):
    __tablename__ = "unavailabilities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    participant_id = Column(Integer, ForeignKey("participants.id", ondelete="CASCADE"), nullable=False)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True)
    day = Column(Integer, nullable=True)
    all_days = Column(Boolean, default=False)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    participant = relationship("Participant", back_populates="unavailabilities")
    task = relationship("Task", back_populates="unavailabilities", foreign_keys=[task_id])


def get_engine():
    return create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)


SessionLocal = sessionmaker(bind=get_engine())


def get_session():
    return SessionLocal()


def init_db():
    Base.metadata.create_all(get_engine())
    # Safe migration: add messaging column if it doesn't exist yet
    from sqlalchemy import text
    engine = get_engine()
    with engine.connect() as conn:
        try:
            conn.execute(text(
                "ALTER TABLE participants ADD COLUMN messaging "
                "ENUM('whatsapp','signal','telegram','none') NOT NULL DEFAULT 'none'"
            ))
            conn.commit()
        except Exception:
            pass  # Column already exists
        try:
            conn.execute(text(
                "ALTER TABLE participants ADD COLUMN `group` "
                "ENUM('1','2','3a','3b','4','5','6+7','8') NULL DEFAULT NULL"
            ))
            conn.commit()
        except Exception:
            pass  # Column already exists
    print("Database tables created (or already exist).")