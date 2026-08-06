"""add book history and transit tracking

Revision ID: d7e3b91c4a20
Revises: a4af3deaaa80
Create Date: 2026-08-05 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d7e3b91c4a20"
down_revision: Union[str, None] = "a4af3deaaa80"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "bookclub_members",
        sa.Column("transit_label_printed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "bookclub_books",
        sa.Column(
            "is_past_selection",
            sa.Boolean(),
            server_default="0",
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("bookclub_books", "is_past_selection")
    op.drop_column("bookclub_members", "transit_label_printed_at")
