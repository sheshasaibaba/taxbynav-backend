"""Add guest booking support: nullable user_id, guest_email, guest_full_name.

Revision ID: 003_guest_booking
Revises: 002_contact_mode
Create Date: 2026-03-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "003_guest_booking"
down_revision: Union[str, None] = "002_contact_mode"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop FK so we can alter user_id (SQLite/Postgres may require it)
    op.drop_constraint(
        "appointments_user_id_fkey",
        "appointments",
        type_="foreignkey",
    )
    op.alter_column(
        "appointments",
        "user_id",
        existing_type=sa.Integer(),
        nullable=True,
    )
    op.create_foreign_key(
        "appointments_user_id_fkey",
        "appointments",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.add_column(
        "appointments",
        sa.Column("guest_email", sa.String(), nullable=True),
    )
    op.add_column(
        "appointments",
        sa.Column("guest_full_name", sa.String(), nullable=True),
    )
    op.create_index(
        op.f("ix_appointments_guest_email"),
        "appointments",
        ["guest_email"],
        unique=False,
    )
    op.create_check_constraint(
        "appointments_user_or_guest",
        "appointments",
        "(user_id IS NOT NULL) OR (guest_email IS NOT NULL)",
    )


def downgrade() -> None:
    # Remove guest-only rows so user_id can be NOT NULL again
    op.execute("DELETE FROM appointments WHERE user_id IS NULL")
    op.drop_constraint("appointments_user_or_guest", "appointments", type_="check")
    op.drop_index(op.f("ix_appointments_guest_email"), table_name="appointments")
    op.drop_column("appointments", "guest_full_name")
    op.drop_column("appointments", "guest_email")
    op.drop_constraint("appointments_user_id_fkey", "appointments", type_="foreignkey")
    op.alter_column(
        "appointments",
        "user_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.create_foreign_key(
        "appointments_user_id_fkey",
        "appointments",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
