"""add community announcements and rsvp

Revision ID: 9b2f4d6a8c10
Revises: 7e4c2a1f9d30
Create Date: 2026-08-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9b2f4d6a8c10"
down_revision: Union[str, None] = "7e4c2a1f9d30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("bookclub_participation") as batch:
        batch.add_column(sa.Column("rsvp_status", sa.String(length=20), nullable=True))

    op.create_table(
        "bookclub_announcements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("club_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("pinned", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["club_id"], ["book_clubs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bookclub_announcements_club_id", "bookclub_announcements", ["club_id"])


def downgrade() -> None:
    op.drop_index("ix_bookclub_announcements_club_id", table_name="bookclub_announcements")
    op.drop_table("bookclub_announcements")
    with op.batch_alter_table("bookclub_participation") as batch:
        batch.drop_column("rsvp_status")
