import asyncio
import hashlib
import hmac

from energy_manager.main import tenant_scope_allowed, webhook_signature_valid
from energy_manager.tailscale import FakeTailscaleProvider, NetworkAgent


def test_wrong_webhook_signature_rejected():
    assert not webhook_signature_valid(b'{"type":"nodeCreated"}', "wrong", "secret")


def test_correct_webhook_signature_accepted():
    body = b'{"type":"nodeCreated"}'
    signature = hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    assert webhook_signature_valid(body, signature, "secret")


def test_fake_tailscale_without_credentials():
    provider = FakeTailscaleProvider()
    nodes = asyncio.run(provider.list_nodes())
    assert nodes[0].online and "tag:em-edge" in nodes[0].tags


def test_tailscale_missing_is_reported(monkeypatch):
    def missing(*args, **kwargs): raise FileNotFoundError("tailscale")
    monkeypatch.setattr("subprocess.run", missing)
    result = NetworkAgent(dry_run=False).diagnostics()
    assert result["installed"] is False and result["connected"] is False


def test_tenant_isolation():
    assert tenant_scope_allowed("customer_admin", "tenant-a", "tenant-a")
    assert not tenant_scope_allowed("customer_admin", "tenant-a", "tenant-b")
    assert tenant_scope_allowed("platform_admin", None, "tenant-b")

