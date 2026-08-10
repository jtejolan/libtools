"""add social reading experience

Revision ID: a7d3e5f9b120
Revises: f9a2d4c6e810
Create Date: 2026-08-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7d3e5f9b120"
down_revision: Union[str, None] = "f9a2d4c6e810"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bookclub_reading_progress", sa.Column("current_page", sa.Integer(), nullable=True))
    op.add_column("bookclub_reading_progress", sa.Column("shared_with_club", sa.Boolean(), server_default="0", nullable=False))
    op.add_column("bookclub_discussion_posts", sa.Column("spoiler", sa.Boolean(), server_default="0", nullable=False))
    with op.batch_alter_table("bookclub_ratings") as batch:
        batch.alter_column("rating", existing_type=sa.Integer(), type_=sa.Float(), existing_nullable=False)

    op.create_table(
        "bookclub_discussion_reactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column("member_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), server_default="like", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["post_id"], ["bookclub_discussion_posts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["member_id"], ["bookclub_members.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("post_id", "member_id", name="uq_bookclub_post_member_reaction"),
    )
    op.create_index("ix_bookclub_discussion_reactions_post_id", "bookclub_discussion_reactions", ["post_id"])
    op.create_index("ix_bookclub_discussion_reactions_member_id", "bookclub_discussion_reactions", ["member_id"])
    op.create_table(
        "bookclub_activity",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("club_id", sa.Integer(), nullable=False),
        sa.Column("member_id", sa.Integer(), nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("detail", sa.String(length=500), nullable=True),
        sa.Column("reference_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["club_id"], ["book_clubs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["member_id"], ["bookclub_members.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["book_id"], ["bookclub_books.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("club_id", "member_id", "book_id", "kind", "created_at"):
        op.create_index(f"ix_bookclub_activity_{column}", "bookclub_activity", [column])


def downgrade() -> None:
    op.drop_table("bookclub_activity")
    op.drop_table("bookclub_discussion_reactions")
    with op.batch_alter_table("bookclub_ratings") as batch:
        batch.alter_column("rating", existing_type=sa.Float(), type_=sa.Integer(), existing_nullable=False)
    op.drop_column("bookclub_discussion_posts", "spoiler")
    op.drop_column("bookclub_reading_progress", "shared_with_club")
    op.drop_column("bookclub_reading_progress", "current_page")
