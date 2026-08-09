"""add participant progress and preferences

Revision ID: b4d7f1a3c920
Revises: 9b2f4d6a8c10
Create Date: 2026-08-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b4d7f1a3c920"
down_revision: Union[str, None] = "9b2f4d6a8c10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bookclub_reading_progress",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("club_id", sa.Integer(), nullable=False),
        sa.Column("member_id", sa.Integer(), nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["bookclub_books.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["club_id"], ["book_clubs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["member_id"], ["bookclub_members.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("member_id", "book_id", name="uq_bookclub_member_book_progress"),
    )
    op.create_index("ix_bookclub_reading_progress_club_id", "bookclub_reading_progress", ["club_id"])
    op.create_index("ix_bookclub_reading_progress_member_id", "bookclub_reading_progress", ["member_id"])
    op.create_index("ix_bookclub_reading_progress_book_id", "bookclub_reading_progress", ["book_id"])

    op.create_table(
        "bookclub_notification_preferences",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("member_id", sa.Integer(), nullable=False),
        sa.Column("announcements", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("polls", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("meeting_reminders", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("discussion_replies", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["member_id"], ["bookclub_members.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("member_id"),
    )
    op.create_index("ix_bookclub_notification_preferences_member_id", "bookclub_notification_preferences", ["member_id"])


def downgrade() -> None:
    op.drop_index("ix_bookclub_notification_preferences_member_id", table_name="bookclub_notification_preferences")
    op.drop_table("bookclub_notification_preferences")
    op.drop_index("ix_bookclub_reading_progress_book_id", table_name="bookclub_reading_progress")
    op.drop_index("ix_bookclub_reading_progress_member_id", table_name="bookclub_reading_progress")
    op.drop_index("ix_bookclub_reading_progress_club_id", table_name="bookclub_reading_progress")
    op.drop_table("bookclub_reading_progress")
