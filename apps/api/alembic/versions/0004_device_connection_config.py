"""Store transport-specific endpoint settings on devices."""

from alembic import op
import sqlalchemy as sa


revision = "0004_device_connection_config"
down_revision = "0003_system_preferences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("devices")}
    if "config" not in columns:
        op.add_column("devices", sa.Column("config", sa.JSON(), nullable=True))
    devices = sa.table("devices", sa.column("config", sa.JSON()))
    op.execute(devices.update().where(devices.c.config.is_(None)).values(config={}))


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("devices")}
    if "config" in columns:
        op.drop_column("devices", "config")
