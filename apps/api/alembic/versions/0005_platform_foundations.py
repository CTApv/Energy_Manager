"""Add secure sync, fleet inventory, rollups, tariffs and baselines."""

from alembic import op
import sqlalchemy as sa


revision = "0005_platform_foundations"
down_revision = "0004_device_connection_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    edge_columns = {column["name"] for column in inspector.get_columns("edges")}
    additions = {
        "last_sync_at": sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        "configuration_version": sa.Column("configuration_version", sa.String(80), nullable=False, server_default=""),
        "backlog_count": sa.Column("backlog_count", sa.Integer(), nullable=False, server_default="0"),
        "disk_free_percent": sa.Column("disk_free_percent", sa.Float(), nullable=True),
        "inventory": sa.Column("inventory", sa.JSON(), nullable=False, server_default="{}"),
    }
    for name, column in additions.items():
        if name not in edge_columns:
            op.add_column("edges", column)
    telemetry_columns = {column["name"] for column in inspector.get_columns("telemetry_samples")}
    if "edge_id" not in telemetry_columns:
        op.add_column("telemetry_samples", sa.Column("edge_id", sa.String(36), nullable=True))
        op.create_index("ix_telemetry_samples_edge_id", "telemetry_samples", ["edge_id"])
    batch_columns = {column["name"] for column in inspector.get_columns("ingested_batches")}
    if "event_count" not in batch_columns:
        op.add_column("ingested_batches", sa.Column("event_count", sa.Integer(), nullable=False, server_default="0"))

    tables = set(inspector.get_table_names())
    if "ingested_events" not in tables:
        op.create_table("ingested_events",
            sa.Column("id", sa.String(36), primary_key=True), sa.Column("edge_id", sa.String(36), nullable=False),
            sa.Column("batch_id", sa.String(100), nullable=False), sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_ingested_events_edge_id", "ingested_events", ["edge_id"])
        op.create_index("ix_ingested_events_batch_id", "ingested_events", ["batch_id"])
        op.create_index("ix_ingested_events_received_at", "ingested_events", ["received_at"])
    if "remote_devices" not in tables:
        op.create_table("remote_devices",
            sa.Column("id", sa.String(36), primary_key=True), sa.Column("edge_id", sa.String(36), nullable=False),
            sa.Column("local_device_id", sa.String(36), nullable=False), sa.Column("name", sa.String(160), nullable=False),
            sa.Column("category", sa.String(60), nullable=False), sa.Column("manufacturer", sa.String(100), nullable=False),
            sa.Column("model", sa.String(100), nullable=False), sa.Column("profile_id", sa.String(100), nullable=False),
            sa.Column("profile_version", sa.String(30), nullable=False), sa.Column("status", sa.String(30), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("edge_id", "local_device_id"),
        )
        op.create_index("ix_remote_devices_edge_id", "remote_devices", ["edge_id"])
    if "telemetry_rollups" not in tables:
        op.create_table("telemetry_rollups",
            sa.Column("id", sa.String(36), primary_key=True), sa.Column("edge_id", sa.String(36), nullable=False),
            sa.Column("device_id", sa.String(36), nullable=False), sa.Column("measurement_key", sa.String(160), nullable=False),
            sa.Column("resolution", sa.String(20), nullable=False), sa.Column("bucket_start", sa.DateTime(timezone=True), nullable=False),
            sa.Column("sample_count", sa.Integer(), nullable=False), sa.Column("good_count", sa.Integer(), nullable=False),
            sa.Column("minimum", sa.Float(), nullable=True), sa.Column("maximum", sa.Float(), nullable=True),
            sa.Column("average", sa.Float(), nullable=True), sa.Column("last_value", sa.Float(), nullable=True), sa.Column("unit", sa.String(30), nullable=False),
            sa.UniqueConstraint("edge_id", "device_id", "measurement_key", "resolution", "bucket_start"),
        )
        for column in ("edge_id", "device_id", "measurement_key", "bucket_start"):
            op.create_index(f"ix_telemetry_rollups_{column}", "telemetry_rollups", [column])
    if "energy_tariffs" not in tables:
        op.create_table("energy_tariffs",
            sa.Column("id", sa.String(36), primary_key=True), sa.Column("name", sa.String(160), nullable=False),
            sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False), sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
            sa.Column("weekdays", sa.JSON(), nullable=False), sa.Column("start_minute", sa.Integer(), nullable=False),
            sa.Column("end_minute", sa.Integer(), nullable=False), sa.Column("import_price_per_kwh", sa.Float(), nullable=False),
            sa.Column("export_price_per_kwh", sa.Float(), nullable=False), sa.Column("priority", sa.Integer(), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
    if "energy_baselines" not in tables:
        op.create_table("energy_baselines",
            sa.Column("id", sa.String(36), primary_key=True), sa.Column("name", sa.String(160), nullable=False),
            sa.Column("measurement_key", sa.String(160), nullable=False), sa.Column("device_id", sa.String(36), nullable=True),
            sa.Column("period_start", sa.DateTime(timezone=True), nullable=False), sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
            sa.Column("baseline_value", sa.Float(), nullable=False), sa.Column("unit", sa.String(30), nullable=False),
            sa.Column("normalization", sa.JSON(), nullable=False), sa.Column("active", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_energy_baselines_device_id", "energy_baselines", ["device_id"])


def downgrade() -> None:
    for table in ("energy_baselines", "energy_tariffs", "telemetry_rollups", "remote_devices", "ingested_events"):
        if table in sa.inspect(op.get_bind()).get_table_names():
            op.drop_table(table)
    inspector = sa.inspect(op.get_bind())
    batch_columns = {column["name"] for column in inspector.get_columns("ingested_batches")}
    if "event_count" in batch_columns:
        op.drop_column("ingested_batches", "event_count")
    telemetry_columns = {column["name"] for column in inspector.get_columns("telemetry_samples")}
    if "edge_id" in telemetry_columns:
        op.drop_index("ix_telemetry_samples_edge_id", table_name="telemetry_samples")
        op.drop_column("telemetry_samples", "edge_id")
    edge_columns = {column["name"] for column in inspector.get_columns("edges")}
    for column in ("inventory", "disk_free_percent", "backlog_count", "configuration_version", "last_sync_at"):
        if column in edge_columns:
            op.drop_column("edges", column)
