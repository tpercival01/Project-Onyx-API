from datetime import datetime
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class User(Base):
    __tablename__ = "users"

    xuid: Mapped[str] = mapped_column(String, primary_key=True)
    gamertag: Mapped[str] = mapped_column(String, nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String, nullable=True)
    last_updated: Mapped[datetime | None] = mapped_column(
        DateTime, server_default=func.now(), nullable=True
    )


class Game(Base):
    __tablename__ = "games"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_xuid: Mapped[str] = mapped_column(
        ForeignKey("users.xuid"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    earned_achievements: Mapped[int] = mapped_column(Integer, nullable=False)
    total_achievements: Mapped[int] = mapped_column(Integer, nullable=False)
    current_gamerscore: Mapped[int] = mapped_column(Integer, default=0)
    total_gamerscore: Mapped[int] = mapped_column(Integer, default=0)
    last_time_played: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    display_image: Mapped[str | None] = mapped_column(String, nullable=True)


class Achievement(Base):
    __tablename__ = "achievements"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_xuid: Mapped[str] = mapped_column(String, nullable=False)
    title_id: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    gamerscore: Mapped[int] = mapped_column(Integer, nullable=False)
    is_unlocked: Mapped[bool] = mapped_column(Boolean, nullable=False)
    icon_url: Mapped[str | None] = mapped_column(String, nullable=True)