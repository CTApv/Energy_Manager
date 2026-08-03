from __future__ import annotations

import json
import subprocess
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass
class NodeInfo:
    id: str
    hostname: str
    ip: str
    tags: list[str]
    online: bool
    last_seen: str


class TailscaleProvider(ABC):
    @abstractmethod
    async def create_auth_key(self, tags: list[str], reusable: bool = False) -> str: ...
    @abstractmethod
    async def list_nodes(self) -> list[NodeInfo]: ...
    @abstractmethod
    async def update_tags(self, node_id: str, tags: list[str]) -> NodeInfo: ...
    @abstractmethod
    async def revoke_node(self, node_id: str) -> None: ...


class FakeTailscaleProvider(TailscaleProvider):
    def __init__(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.nodes = {"fake-node-em-demo": NodeInfo("fake-node-em-demo", "em-demo-001", "100.64.0.10", ["tag:em-edge", "tag:em-customer-cta-demo", "tag:em-site-stabilimento-demo"], True, now)}

    async def create_auth_key(self, tags: list[str], reusable: bool = False) -> str:
        return "tskey-auth-fake-redacted"

    async def list_nodes(self) -> list[NodeInfo]:
        return list(self.nodes.values())

    async def update_tags(self, node_id: str, tags: list[str]) -> NodeInfo:
        node = self.nodes[node_id]
        node.tags = tags
        return node

    async def revoke_node(self, node_id: str) -> None:
        self.nodes.pop(node_id, None)


class ApiTailscaleProvider(TailscaleProvider):
    """Real-provider boundary. Network calls are deliberately disabled until credentials are authorized."""
    def __init__(self, client_id: str, client_secret: str, tailnet: str) -> None:
        self.client_id, self._client_secret, self.tailnet = client_id, client_secret, tailnet

    async def create_auth_key(self, tags: list[str], reusable: bool = False) -> str:
        raise RuntimeError("real Tailscale mutations require explicit deployment authorization")

    async def list_nodes(self) -> list[NodeInfo]:
        raise RuntimeError("real Tailscale API is not enabled in the MVP development profile")

    async def update_tags(self, node_id: str, tags: list[str]) -> NodeInfo:
        raise RuntimeError("real Tailscale mutations require explicit deployment authorization")

    async def revoke_node(self, node_id: str) -> None:
        raise RuntimeError("real Tailscale mutations require explicit deployment authorization")


class NetworkAgent:
    def __init__(self, dry_run: bool = True) -> None:
        self.dry_run = dry_run

    def _run(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        if self.dry_run:
            return subprocess.CompletedProcess(args, 0, stdout='{"BackendState":"Running","TailscaleIPs":["100.64.0.10"],"Self":{"Tags":["tag:em-edge"]}}', stderr="")
        return subprocess.run(args, check=False, capture_output=True, text=True, timeout=10, shell=False)

    def diagnostics(self) -> dict[str, Any]:
        try:
            result = self._run(["tailscale", "status", "--json"])
            payload = json.loads(result.stdout) if result.returncode == 0 else {}
            return {"installed": True, "connected": payload.get("BackendState") == "Running", "ip": (payload.get("TailscaleIPs") or [None])[0], "tags": payload.get("Self", {}).get("Tags", []), "dry_run": self.dry_run, "error": result.stderr or None}
        except (FileNotFoundError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
            return {"installed": False, "connected": False, "ip": None, "tags": [], "dry_run": self.dry_run, "error": str(exc)}


def node_dict(node: NodeInfo) -> dict:
    return asdict(node)

