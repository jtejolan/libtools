"""pivot bookclub accounts and roster

Revision ID: 7e4c2a1f9d30
Revises: c445e16b6173
Create Date: 2026-08-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7e4c2a1f9d30"
down_revision: Union[str, None] = "c445e16b6173"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The participant-owned self-serve feature was never production data.
    # Remove it explicitly because SQLite deployments do not enable FK
    # cascades globally. Library-managed clubs and their rosters are kept.
    self_serve = "SELECT id FROM book_clubs WHERE club_type = 'self_serve'"
    op.execute(sa.text(
        "DELETE FROM bookclub_date_poll_votes WHERE poll_id IN "
        f"(SELECT id FROM bookclub_date_polls WHERE club_id IN ({self_serve}))"
    ))
    op.execute(sa.text(
        "DELETE FROM bookclub_date_poll_options WHERE poll_id IN "
        f"(SELECT id FROM bookclub_date_polls WHERE club_id IN ({self_serve}))"
    ))
    op.execute(sa.text(f"DELETE FROM bookclub_date_polls WHERE club_id IN ({self_serve})"))
    op.execute(sa.text(
        "DELETE FROM bookclub_votes WHERE voting_round_id IN "
        f"(SELECT id FROM bookclub_voting_rounds WHERE club_id IN ({self_serve}))"
    ))
    op.execute(sa.text(
        "DELETE FROM bookclub_book_candidates WHERE voting_round_id IN "
        f"(SELECT id FROM bookclub_voting_rounds WHERE club_id IN ({self_serve}))"
    ))
    op.execute(sa.text(f"DELETE FROM bookclub_voting_rounds WHERE club_id IN ({self_serve})"))
    op.execute(sa.text(f"DELETE FROM bookclub_ratings WHERE club_id IN ({self_serve})"))
    op.execute(sa.text(
        "DELETE FROM bookclub_discussion_questions WHERE meeting_id IN "
        f"(SELECT id FROM bookclub_meetings WHERE club_id IN ({self_serve}))"
    ))
    op.execute(sa.text(
        "DELETE FROM bookclub_participation WHERE meeting_id IN "
        f"(SELECT id FROM bookclub_meetings WHERE club_id IN ({self_serve}))"
    ))
    for table in (
        "bookclub_meetings",
        "bookclub_members",
        "bookclub_books",
        "bookclub_templates",
        "book_club_access",
    ):
        op.execute(sa.text(f"DELETE FROM {table} WHERE club_id IN ({self_serve})"))
    op.execute(sa.text(f"DELETE FROM book_clubs WHERE id IN ({self_serve})"))

    # Participant identities are also test data, so rebuilding them as
    # global accounts does not require an ambiguous account merge.
    op.execute(sa.text("DELETE FROM bookclub_ratings"))
    op.execute(sa.text("DELETE FROM bookclub_votes"))
    op.execute(sa.text("DELETE FROM bookclub_date_poll_votes"))
    op.execute(sa.text("UPDATE bookclub_book_candidates SET proposed_by_participant_id = NULL"))
    op.execute(sa.text("DELETE FROM bookclub_participant_account_tokens"))
    op.execute(sa.text("DELETE FROM bookclub_participant_accounts"))

    with op.batch_alter_table("bookclub_participant_accounts") as batch:
        batch.drop_constraint("uq_bookclub_participant_club_email", type_="unique")
        batch.drop_index("ix_bookclub_participant_accounts_club_id")
        batch.drop_column("club_id")
        batch.drop_column("role")
        batch.drop_column("unsubscribed_at")
        batch.create_unique_constraint("uq_bookclub_participant_email", ["email"])

    with op.batch_alter_table("bookclub_members") as batch:
        batch.add_column(sa.Column("participant_account_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("participant_unsubscribed_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_index("ix_bookclub_members_participant_account_id", ["participant_account_id"])
        batch.create_foreign_key(
            "fk_bookclub_members_participant_account_id",
            "bookclub_participant_accounts",
            ["participant_account_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    # Removed test-only self-serve data cannot and should not be restored.
    with op.batch_alter_table("bookclub_members") as batch:
        batch.drop_constraint("fk_bookclub_members_participant_account_id", type_="foreignkey")
        batch.drop_index("ix_bookclub_members_participant_account_id")
        batch.drop_column("participant_unsubscribed_at")
        batch.drop_column("participant_account_id")

    with op.batch_alter_table("bookclub_participant_accounts") as batch:
        batch.drop_constraint("uq_bookclub_participant_email", type_="unique")
        batch.add_column(sa.Column("club_id", sa.Integer(), nullable=False))
        batch.add_column(sa.Column("role", sa.String(length=20), server_default="member", nullable=False))
        batch.add_column(sa.Column("unsubscribed_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_index("ix_bookclub_participant_accounts_club_id", ["club_id"])
        batch.create_unique_constraint("uq_bookclub_participant_club_email", ["club_id", "email"])
