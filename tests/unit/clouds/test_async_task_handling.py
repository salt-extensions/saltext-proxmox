"""
Unit tests for create()'s handling of Proxmox's asynchronous task
completion and cluster/resources cache consistency.

Regression tests for: create() fired the guest-creation API call and
immediately proceeded to start() with no verification that creation
had actually finished. Proxmox's create endpoint is asynchronous
(returns a task UPID immediately; real work continues in the
background), and cluster/resources is a separately, periodically
refreshed cache that can lag behind task completion by several
seconds. Either gap caused intermittent SaltCloudNotFound on
freshly-created guests.
"""
from unittest.mock import patch

import pytest

from salt.exceptions import SaltCloudNotFound
from saltext.proxmox.clouds import proxmox


@pytest.fixture
def configure_loader_modules():
    return {proxmox: {"__opts__": {}}}


def test_wait_for_task_polls_until_stopped(monkeypatch):
    """
    _wait_for_task should poll the task status endpoint until it
    reports 'stopped', without sleeping in real time during the test.
    """
    responses = [
        {"status": "running"},
        {"status": "running"},
        {"status": "stopped"},
    ]

    monkeypatch.setattr(proxmox.time, "sleep", lambda _: None)

    with patch.object(proxmox, "_query", autospec=True, side_effect=responses) as mock_query:
        proxmox._wait_for_task("mypvenode", "UPID:mypvenode:...")

    assert mock_query.call_count == 3


def test_wait_for_task_no_upid_returns_immediately():
    """
    A falsy upid (e.g. create() returned nothing) should be a no-op,
    not attempt to query task status at all.
    """
    with patch.object(proxmox, "_query", autospec=True) as mock_query:
        proxmox._wait_for_task("mypvenode", None)

    mock_query.assert_not_called()


def test_wait_for_task_gives_up_after_timeout(monkeypatch):
    """
    _wait_for_task should stop polling once timeout is exceeded,
    rather than looping forever on a stuck task.
    """
    monkeypatch.setattr(proxmox.time, "sleep", lambda _: None)

    with patch.object(proxmox, "_query", autospec=True, return_value={"status": "running"}):
        proxmox._wait_for_task("mypvenode", "UPID:...", timeout=3, interval=1)
    # no exception and no hang is the pass condition here


def test_retry_until_found_succeeds_after_transient_misses(monkeypatch):
    """
    _retry_until_found should retry a lookup that raises
    SaltCloudNotFound a few times before succeeding, mirroring
    cluster/resources catching up to a just-created guest.
    """
    monkeypatch.setattr(proxmox.time, "sleep", lambda _: None)
    calls = {"n": 0}

    def flaky_lookup(name):
        calls["n"] += 1
        if calls["n"] < 3:
            raise SaltCloudNotFound(f"not found: {name}")
        return {"name": name}

    result = proxmox._retry_until_found(flaky_lookup, name="k3s-worker-01")

    assert result == {"name": "k3s-worker-01"}
    assert calls["n"] == 3


def test_retry_until_found_raises_after_exhausting_attempts(monkeypatch):
    """
    _retry_until_found should re-raise SaltCloudNotFound once attempts
    are exhausted, rather than retrying forever or swallowing a
    genuine "does not exist" case.
    """
    monkeypatch.setattr(proxmox.time, "sleep", lambda _: None)

    def always_missing(name):
        raise SaltCloudNotFound(f"not found: {name}")

    with pytest.raises(SaltCloudNotFound):
        proxmox._retry_until_found(
            always_missing, name="k3s-worker-01", attempts=3, interval=1
        )
