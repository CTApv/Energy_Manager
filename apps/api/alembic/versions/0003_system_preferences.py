"""Add persistent Edge system preferences and network profiles."""

from alembic import op
import sqlalchemy as sa


revision = "0003_system_preferences"
down_revision = "0002_energy_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "system_preferences" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "system_preferences",
        sa.Column("key", sa.String(length=120), primary_key=True),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("system_preferences")
