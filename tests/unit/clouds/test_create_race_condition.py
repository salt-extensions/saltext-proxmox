"""
Demonstrates the async task / cluster-resources-cache race in create().

create() fires the guest-creation POST, which Proxmox handles
asynchronously (it returns a task UPID immediately and continues the
real work in the background). cluster/resources -- the index every
lookup by name goes through -- is a separately, periodically refreshed
cache (pvestatd) that can still be unaware of the guest even after the
creation task has finished. Starting the guest immediately therefore
raised SaltCloudNotFound intermittently, even though creation had
always succeeded.

These tests drive create() through its public behaviour only, so they
fail against the unpatched module rather than erroring on missing
helpers. Keep it that way: referring to _wait_for_task or
_retry_until_found by name here would stop this file demonstrating the
bug and turn it into a description of the fix.
"""
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from salt.exceptions import SaltCloudNotFound
from saltext.proxmox.clouds import proxmox

NODE = "mypvenode"
VM_NAME = "k3s-worker-01"
VMID = 21101
UPID = f"UPID:{NODE}:00000001:00000001:vzcreate:{VMID}:root@pam:"


@pytest.fixture
def configure_loader_modules():
    return {
        proxmox: {
            "__opts__": {"sock_dir": "/tmp", "transport": "zeromq"},
            "__utils__": {
                "cloud.fire_event": MagicMock(),
                "cloud.filter_event": MagicMock(),
                "cloud.bootstrap": MagicMock(return_value={}),
            },
        }
    }


@pytest.fixture
def vm_():
    return {
        "name": VM_NAME,
        "create": {"node": NODE},
        "technology": "lxc",
    }


def _query_stub(catches_up_on=None):
    """
    Return a `(stub, calls)` pair standing in for `_query()`.

    catches_up_on
        Which cluster/resources call is the first to list the new guest.
        `None` means the cache never catches up at all.

    `calls` counts the cluster/resources lookups the stub has served.
    """
    calls = {"resources": 0}

    def fake_query(method, path, data=None):
        # POST nodes/{node}/lxc -- the asynchronous guest-creation call,
        # which returns a task UPID rather than the finished guest.
        if method == "POST" and path.endswith("/lxc"):
            return UPID
        # GET nodes/{node}/tasks/{upid}/status -- whether the background
        # creation task itself has finished.
        if "/tasks/" in path and path.endswith("/status"):
            return {"status": "stopped"}
        # GET nodes/{node}/lxc/{vmid}/status/current -- the guest's own run
        # state. A different endpoint from the task status above.
        if path.endswith("/status/current"):
            return {"status": "running"}
        # GET cluster/resources -- the periodically refreshed, lagging index.
        if path == "cluster/resources":
            calls["resources"] += 1
            if catches_up_on is None or calls["resources"] < catches_up_on:
                return [{"type": "lxc", "name": "some-other-vm", "vmid": 1, "node": NODE}]
            return [{"type": "lxc", "name": VM_NAME, "vmid": VMID, "node": NODE}]
        # Per-guest config lookups made while building the return value.
        return {}

    return fake_query, calls


def test_create_gives_up_when_resource_list_never_catches_up(monkeypatch, vm_):
    """
    Test that `create()` stops retrying and raises SaltCloudNotFound when
    cluster/resources never lists the new guest
    """
    monkeypatch.setattr(proxmox.time, "sleep", lambda _: None)
    fake_query, calls = _query_stub()

    with patch.object(proxmox, "_query", autospec=True, side_effect=fake_query):
        with pytest.raises(SaltCloudNotFound):
            proxmox.create(vm_)

    # It gave up rather than retrying forever, and it genuinely retried
    # rather than failing on the first miss.
    assert calls["resources"] > 1


def test_create_succeeds_once_resource_list_catches_up(monkeypatch, vm_):
    """
    Test that `create()` tolerates a cluster/resources lookup that initially
    misses the newly created guest, retrying until the cache catches up
    """
    monkeypatch.setattr(proxmox.time, "sleep", lambda _: None)
    fake_query, calls = _query_stub(catches_up_on=3)

    with patch.object(proxmox, "_query", autospec=True, side_effect=fake_query):
        ret = proxmox.create(vm_)

    # The first two lookups missed, so the test really did exercise a retry.
    assert calls["resources"] >= 3
    # And create() returned details for the guest it was asked to create.
    assert ret["name"] == VM_NAME
    assert ret["vmid"] == VMID
