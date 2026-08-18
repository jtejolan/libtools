"""make bookclub member email optional

Revision ID: b3c8f1a4d276
Revises: d41e7a9c2b60
Create Date: 2026-08-14
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b3c8f1a4d276"
down_revision: Union[str, None] = "d41e7a9c2b60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("bookclub_members") as batch:
        batch.alter_column("email", existing_type=sa.String(length=320), nullable=True)


def downgrade() -> None:
    op.execute(sa.text(
        "UPDATE bookclub_members SET email = '' WHERE email IS NULL"
    ))
    with op.batch_alter_table("bookclub_members") as batch:
        batch.alter_column("email", existing_type=sa.String(length=320), nullable=False)
