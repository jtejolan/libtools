"""add participant book suggestions

Revision ID: c9f2a4d7e610
Revises: b8e4f6a1c230
Create Date: 2026-08-11
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c9f2a4d7e610"
down_revision: Union[str, None] = "b8e4f6a1c230"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bookclub_book_suggestions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("club_id", sa.Integer(), nullable=False),
        sa.Column("participant_id", sa.Integer(), nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=True),
        sa.Column("google_books_id", sa.String(length=100), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("author", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("cover_image_url", sa.String(length=1000), nullable=True),
        sa.Column("publication_date", sa.Date(), nullable=True),
        sa.Column("isbn", sa.String(length=20), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("comments", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["bookclub_books.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["club_id"], ["book_clubs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["participant_id"], ["bookclub_participant_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bookclub_book_suggestions_club_id", "bookclub_book_suggestions", ["club_id"])
    op.create_index("ix_bookclub_book_suggestions_participant_id", "bookclub_book_suggestions", ["participant_id"])
    op.create_index("ix_bookclub_book_suggestions_book_id", "bookclub_book_suggestions", ["book_id"])


def downgrade() -> None:
    op.drop_table("bookclub_book_suggestions")
