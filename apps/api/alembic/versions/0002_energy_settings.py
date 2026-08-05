"""Add site energy monitoring settings."""

from alembic import op
import sqlalchemy as sa


revision = "0002_energy_settings"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0001 builds the then-current metadata; keep fresh installs and upgrades compatible.
    if "energy_settings" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "energy_settings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="EUR"),
        sa.Column("import_price_per_kwh", sa.Float(), nullable=False, server_default="0"),
        sa.Column("export_price_per_kwh", sa.Float(), nullable=False, server_default="0"),
        sa.Column("co2_kg_per_kwh", sa.Float(), nullable=False, server_default="0"),
        sa.Column("contracted_power_kw", sa.Float(), nullable=True),
        sa.Column("monthly_energy_budget_kwh", sa.Float(), nullable=True),
        sa.Column("monthly_cost_budget", sa.Float(), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="Europe/Rome"),
        sa.Column("workday_start", sa.String(length=5), nullable=False, server_default="08:00"),
        sa.Column("workday_end", sa.String(length=5), nullable=False, server_default="18:00"),
        sa.Column("working_days", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("energy_settings")
