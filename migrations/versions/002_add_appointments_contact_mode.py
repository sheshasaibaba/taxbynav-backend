"""Add contact_mode to appointments.

Revision ID: 002_contact_mode
Revises: 001_initial
Create Date: 2026-03-07

"""
from typing import Sequence, Union

from alembic import op


revision: str = "002_contact_mode"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE appointments ADD COLUMN IF NOT EXISTS contact_mode VARCHAR(50) NULL"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE appointments DROP COLUMN IF EXISTS contact_mode")
