"""Add persistent Digital Twin Lab experiment records."""

from alembic import op
import sqlalchemy as sa


revision = "0006_digital_twin_lab"
down_revision = "0005_platform_foundations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "digital_twin_runs" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "digital_twin_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("scenario", sa.String(80), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    for column in ("kind", "status", "started_at"):
        op.create_index(f"ix_digital_twin_runs_{column}", "digital_twin_runs", [column])


def downgrade() -> None:
    if "digital_twin_runs" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("digital_twin_runs")
