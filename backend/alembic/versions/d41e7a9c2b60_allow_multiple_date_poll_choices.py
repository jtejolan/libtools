"""allow multiple date poll choices

Revision ID: d41e7a9c2b60
Revises: c9f2a4d7e610
Create Date: 2026-08-12
"""

from typing import Sequence, Union

from alembic import op


revision: str = "d41e7a9c2b60"
down_revision: Union[str, None] = "c9f2a4d7e610"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("bookclub_date_poll_votes") as batch:
        batch.drop_constraint("uq_bookclub_date_poll_vote", type_="unique")
        batch.create_unique_constraint(
            "uq_bookclub_date_poll_vote", ["poll_id", "participant_id", "option_id"]
        )


def downgrade() -> None:
    # If a participant selected several dates, keep their earliest vote before
    # restoring the original one-choice constraint.
    op.execute(
        "DELETE FROM bookclub_date_poll_votes WHERE id NOT IN "
        "(SELECT MIN(id) FROM bookclub_date_poll_votes GROUP BY poll_id, participant_id)"
    )
    with op.batch_alter_table("bookclub_date_poll_votes") as batch:
        batch.drop_constraint("uq_bookclub_date_poll_vote", type_="unique")
        batch.create_unique_constraint(
            "uq_bookclub_date_poll_vote", ["poll_id", "participant_id"]
        )
