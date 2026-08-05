from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Edge, RemoteDevice, Site, TelemetryRollup, Tenant


def allowed_edge_ids(db: Session, role: str, tenant_id: str | None) -> list[str]:
    query = select(Edge.id).join(Site, Edge.site_id == Site.id)
    if role not in {"platform_admin", "technician"}:
        if not tenant_id:
            return []
        query = query.where(Site.tenant_id == tenant_id)
    return list(db.scalars(query))


def portfolio(db: Session, role: str, tenant_id: str | None) -> dict:
    edge_ids = allowed_edge_ids(db, role, tenant_id)
    if not edge_ids:
        return {"tenants": 0, "sites": 0, "edges": 0, "online_edges": 0, "degraded_edges": 0, "devices": 0, "samples_1m": 0, "last_update": None}
    tenant_query = select(func.count(func.distinct(Tenant.id))).join(Site, Site.tenant_id == Tenant.id).join(Edge, Edge.site_id == Site.id).where(Edge.id.in_(edge_ids))
    site_query = select(func.count(func.distinct(Site.id))).join(Edge, Edge.site_id == Site.id).where(Edge.id.in_(edge_ids))
    last_update = db.scalar(select(func.max(Edge.last_seen_at)).where(Edge.id.in_(edge_ids)))
    return {
        "tenants": db.scalar(tenant_query) or 0,
        "sites": db.scalar(site_query) or 0,
        "edges": len(edge_ids),
        "online_edges": db.scalar(select(func.count()).select_from(Edge).where(Edge.id.in_(edge_ids), Edge.status == "online")) or 0,
        "degraded_edges": db.scalar(select(func.count()).select_from(Edge).where(Edge.id.in_(edge_ids), Edge.status == "degraded")) or 0,
        "devices": db.scalar(select(func.count()).select_from(RemoteDevice).where(RemoteDevice.edge_id.in_(edge_ids))) or 0,
        "samples_1m": db.scalar(select(func.sum(TelemetryRollup.sample_count)).where(TelemetryRollup.edge_id.in_(edge_ids))) or 0,
        "last_update": last_update,
        "generated_at": datetime.now(timezone.utc),
    }
