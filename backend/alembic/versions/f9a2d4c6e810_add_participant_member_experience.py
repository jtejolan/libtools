"""add participant member experience

Revision ID: f9a2d4c6e810
Revises: e8a1c4d72f60
Create Date: 2026-08-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f9a2d4c6e810"
down_revision: Union[str, None] = "e8a1c4d72f60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bookclub_members", sa.Column("bio", sa.Text(), nullable=True))
    op.add_column("bookclub_members", sa.Column("avatar_url", sa.String(length=500), nullable=True))
    op.add_column(
        "bookclub_members",
        sa.Column("directory_visible", sa.Boolean(), server_default="0", nullable=False),
    )
    op.add_column(
        "bookclub_notification_preferences",
        sa.Column(
            "delivery_frequency",
            sa.String(length=20),
            server_default="immediate",
            nullable=False,
        ),
    )
    op.create_table(
        "bookclub_announcement_reads",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("announcement_id", sa.Integer(), nullable=False),
        sa.Column("member_id", sa.Integer(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["announcement_id"], ["bookclub_announcements.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["member_id"], ["bookclub_members.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("announcement_id", "member_id", name="uq_bookclub_announcement_member_read"),
    )
    op.create_index("ix_bookclub_announcement_reads_announcement_id", "bookclub_announcement_reads", ["announcement_id"])
    op.create_index("ix_bookclub_announcement_reads_member_id", "bookclub_announcement_reads", ["member_id"])
    op.create_table(
        "bookclub_discussion_posts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("club_id", sa.Integer(), nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("member_id", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["bookclub_books.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["club_id"], ["book_clubs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["member_id"], ["bookclub_members.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_id"], ["bookclub_discussion_posts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bookclub_discussion_posts_book_id", "bookclub_discussion_posts", ["book_id"])
    op.create_index("ix_bookclub_discussion_posts_club_id", "bookclub_discussion_posts", ["club_id"])
    op.create_index("ix_bookclub_discussion_posts_member_id", "bookclub_discussion_posts", ["member_id"])
    op.create_index("ix_bookclub_discussion_posts_parent_id", "bookclub_discussion_posts", ["parent_id"])


def downgrade() -> None:
    op.drop_index("ix_bookclub_discussion_posts_parent_id", table_name="bookclub_discussion_posts")
    op.drop_index("ix_bookclub_discussion_posts_member_id", table_name="bookclub_discussion_posts")
    op.drop_index("ix_bookclub_discussion_posts_club_id", table_name="bookclub_discussion_posts")
    op.drop_index("ix_bookclub_discussion_posts_book_id", table_name="bookclub_discussion_posts")
    op.drop_table("bookclub_discussion_posts")
    op.drop_index("ix_bookclub_announcement_reads_member_id", table_name="bookclub_announcement_reads")
    op.drop_index("ix_bookclub_announcement_reads_announcement_id", table_name="bookclub_announcement_reads")
    op.drop_table("bookclub_announcement_reads")
    op.drop_column("bookclub_notification_preferences", "delivery_frequency")
    op.drop_column("bookclub_members", "directory_visible")
    op.drop_column("bookclub_members", "avatar_url")
    op.drop_column("bookclub_members", "bio")
