"""Add site_settings, contact_inquiries, and appointment enhancements.

Revision ID: 004_settings_and_enhancements
Revises: 003_guest_booking
Create Date: 2026-10-14
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "004_settings_and_enhancements"
down_revision: str | None = "003_guest_booking"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create site_settings table
    op.create_table(
        "site_settings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("business_start_hour", sa.Integer(), nullable=False, server_default="9"),
        sa.Column("business_end_hour", sa.Integer(), nullable=False, server_default="18"),
        sa.Column("slot_duration_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("working_days", sa.String(), nullable=False, server_default="0,1,2,3,4,5"),
        sa.Column("blackout_dates", sa.String(), nullable=False, server_default=""),
        sa.Column("timezone", sa.String(), nullable=False, server_default="America/Regina"),
        sa.Column("contact_address", sa.String(), nullable=False, server_default="Saskatoon, Saskatchewan"),
        sa.Column("contact_phone", sa.String(), nullable=False, server_default="306-381-4864"),
        sa.Column("contact_email", sa.String(), nullable=False, server_default="jattanaservices@outlook.com"),
        sa.Column("map_url", sa.String(), nullable=False, server_default="https://maps.app.goo.gl/U6UWUMCzqQNeqXTs6?g_st=ic"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Insert default settings row id=1
    op.execute(
        """
        INSERT INTO site_settings (id, business_start_hour, business_end_hour, slot_duration_minutes, working_days, blackout_dates, timezone, contact_address, contact_phone, contact_email, map_url)
        VALUES (1, 9, 18, 30, '0,1,2,3,4,5', '', 'America/Regina', 'Saskatoon, Saskatchewan', '306-381-4864', 'jattanaservices@outlook.com', 'https://maps.app.goo.gl/U6UWUMCzqQNeqXTs6?g_st=ic')
        ON CONFLICT (id) DO NOTHING
        """
    )

    # 2. Create contact_inquiries table
    op.create_table(
        "contact_inquiries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="new"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(op.f("ix_contact_inquiries_email"), "contact_inquiries", ["email"], unique=False)

    # 3. Add columns to appointments table
    op.add_column("appointments", sa.Column("service_type", sa.String(length=100), nullable=True))
    op.add_column("appointments", sa.Column("phone_number", sa.String(length=50), nullable=True))
    op.add_column("appointments", sa.Column("status", sa.String(length=50), nullable=False, server_default="scheduled"))


def downgrade() -> None:
    op.drop_column("appointments", "status")
    op.drop_column("appointments", "phone_number")
    op.drop_column("appointments", "service_type")
    op.drop_index(op.f("ix_contact_inquiries_email"), table_name="contact_inquiries")
    op.drop_table("contact_inquiries")
    op.drop_table("site_settings")
