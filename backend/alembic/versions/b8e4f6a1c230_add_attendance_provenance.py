"""add participant attendance provenance

Revision ID: b8e4f6a1c230
Revises: a7d3e5f9b120
Create Date: 2026-08-11
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b8e4f6a1c230"
down_revision: Union[str, None] = "a7d3e5f9b120"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bookclub_participation", sa.Column("participant_attended", sa.Boolean(), nullable=True))
    op.add_column("bookclub_participation", sa.Column("participant_attendance_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("bookclub_participation", sa.Column("attendance_source", sa.String(length=20), nullable=True))
    op.add_column("bookclub_participation", sa.Column("attendance_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        "UPDATE bookclub_participation "
        "SET attendance_source = 'facilitator', attendance_updated_at = CURRENT_TIMESTAMP "
        "WHERE attended = 1"
    )


def downgrade() -> None:
    op.drop_column("bookclub_participation", "attendance_updated_at")
    op.drop_column("bookclub_participation", "attendance_source")
    op.drop_column("bookclub_participation", "participant_attendance_updated_at")
    op.drop_column("bookclub_participation", "participant_attended")
