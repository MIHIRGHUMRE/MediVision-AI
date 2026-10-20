"""Create persistent cases and audit events.

Revision ID: 0001_initial_schema
Revises:
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cases",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("body_region", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("images", sa.JSON(), nullable=False),
        sa.Column("report_status", sa.String(length=24), nullable=True),
        sa.Column("indication", sa.Text(), nullable=True),
        sa.Column("findings", sa.Text(), nullable=True),
        sa.Column("impression", sa.Text(), nullable=True),
        sa.Column("reviewer", sa.String(length=200), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cases_created_at_id", "cases", ["created_at", "id"])
    op.create_index(
        "ix_cases_report_status_created_at",
        "cases",
        ["report_status", "created_at"],
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("actor", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_case_id_id", "audit_events", ["case_id", "id"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_case_id_id", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_cases_report_status_created_at", table_name="cases")
    op.drop_index("ix_cases_created_at_id", table_name="cases")
    op.drop_table("cases")
