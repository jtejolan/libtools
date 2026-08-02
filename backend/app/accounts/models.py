from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class LibtoolsUser(Base):
    __tablename__ = "libtools_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(500))
    recovery_code_hash: Mapped[str | None] = mapped_column(String(500))
    role: Mapped[str] = mapped_column(String(20), default="user", server_default="user")
    active: Mapped[bool] = mapped_column(Boolean(), default=True, server_default="1")
    must_change_password: Mapped[bool] = mapped_column(
        Boolean(), default=False, server_default="0"
    )
    session_version: Mapped[int] = mapped_column(
        Integer(), default=1, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    tool_access: Mapped[list["ToolAccess"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class ToolAccess(Base):
    __tablename__ = "libtools_tool_access"
    __table_args__ = (
        UniqueConstraint("user_id", "tool_key", name="uq_libtools_user_tool"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("libtools_users.id", ondelete="CASCADE"), index=True
    )
    tool_key: Mapped[str] = mapped_column(String(50), index=True)

    user: Mapped[LibtoolsUser] = relationship(back_populates="tool_access")
