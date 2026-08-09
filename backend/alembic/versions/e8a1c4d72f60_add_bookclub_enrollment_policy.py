"""add book club enrollment policy

Revision ID: e8a1c4d72f60
Revises: b4d7f1a3c920
Create Date: 2026-08-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e8a1c4d72f60"
down_revision: Union[str, None] = "b4d7f1a3c920"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "book_clubs",
        sa.Column(
            "enrollment_policy",
            sa.String(length=20),
            server_default="open",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("book_clubs", "enrollment_policy")
