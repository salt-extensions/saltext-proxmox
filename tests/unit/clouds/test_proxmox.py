"""
    :codeauthor: Bernhard Gally <github.com/I3urny>
"""

import io
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import requests
from salt.exceptions import SaltCloudNotFound
from salt.exceptions import SaltCloudSystemExit

from saltext.proxmox.clouds import proxmox


def _fqn(function):
    """
    Return the fully qualified name of a function.
    """
    return ".".join([function.__module__, function.__qualname__])


@pytest.fixture
def configure_loader_modules():
    return {
        proxmox: {
            "__opts__": {
                "sock_dir": True,
                "transport": True,
            },
            "__active_provider_name__": "",
        }
    }


@patch(_fqn(proxmox.show_instance))
@patch(_fqn(proxmox.start))
@patch(_fqn(proxmox._query))
def test_create(mock__query: MagicMock, mock_start: MagicMock, mock_show_instance: MagicMock):
    """
    Test that `create()` is calling the correct endpoint with the correct arguments
    """
    create_config = {
        "name": "my-vm",
        "technology": "qemu",
        "create": {
            "vmid": 123,
            "node": "proxmox-node1",
        },
    }

    with (
        patch("salt.utils.cloud.bootstrap", MagicMock()),
        patch("salt.utils.cloud.filter_event", MagicMock()),
        patch("salt.utils.cloud.fire_event", MagicMock()),
    ):
        proxmox.create(create_config)
    mock__query.assert_called_with("POST", "nodes/proxmox-node1/qemu", create_config["create"])


@patch(_fqn(proxmox.show_instance))
@patch(_fqn(proxmox.start))
@patch(_fqn(proxmox.clone))
def test_create_with_clone(
    mock_clone: MagicMock, mock_start: MagicMock, mock_show_instance: MagicMock
):
    """
    Test that `create()` is using the `clone()` function when the config specifies cloning
    """
    clone_config = {
        "name": "my-vm",
        "technology": "qemu",
        "clone": {
            "vmid": 123,
            "newid": 456,
            "node": "proxmox-node1",
        },
    }

    with (
        patch("salt.utils.cloud.bootstrap", MagicMock()),
        patch("salt.utils.cloud.filter_event", MagicMock()),
        patch("salt.utils.cloud.fire_event", MagicMock()),
    ):
        proxmox.create(clone_config)
    mock_clone.assert_called()


@patch(_fqn(proxmox._get_vm_by_id))
@patch(_fqn(proxmox._query))
def test_clone(mock__query: MagicMock, mock__get_vm_by_id: MagicMock):
    """
    Test that `clone()` is calling the correct endpoint with the correct arguments
    """
    clone_config = {
        "vmid": 123,
        "newid": 456,
    }

    mock__get_vm_by_id.return_value = {
        "vmid": 123,
        "node": "proxmox-node1",
        "type": "lxc",
    }

    proxmox.clone(call="function", kwargs=clone_config)
    mock__query.assert_called_with("POST", "nodes/proxmox-node1/lxc/123/clone", clone_config)


def test_clone_when_called_as_action():
    """
    Test that `clone()` raises an error when called as action
    """
    with pytest.raises(SaltCloudSystemExit):
        proxmox.clone(call="action")


@patch(_fqn(proxmox._get_vm_by_name))
@patch(_fqn(proxmox._query))
def test_reconfigure(mock__query: MagicMock, mock__get_vm_by_name: MagicMock):
    """
    Test that `reconfigure()` is calling the correct endpoint with the correct arguments
    """
    reconfigure_config = {"description": "custom description to be updated"}

    mock__get_vm_by_name.return_value = {
        "vmid": 123,
        "name": "my-proxmox-vm",
        "node": "proxmox-node1",
        "type": "lxc",
    }

    proxmox.reconfigure(call="action", name="my-proxmox-vm", kwargs=reconfigure_config)
    mock__query.assert_called_with("PUT", "nodes/proxmox-node1/lxc/123/config", reconfigure_config)


def test_reconfigure_when_called_as_function():
    """
    Test that `reconfigure()` raises an error when called as function
    """
    with pytest.raises(SaltCloudSystemExit):
        proxmox.reconfigure(call="function")


@patch(_fqn(proxmox._get_vm_by_name))
@patch(_fqn(proxmox._query))
def test_destroy(mock__query: MagicMock, mock__get_vm_by_name: MagicMock):
    """
    Test that `clone()` is calling the correct endpoint with the correct arguments
    """
    destroy_config = {"force": True}

    mock__get_vm_by_name.return_value = {
        "vmid": 123,
        "name": "my-proxmox-vm",
        "node": "proxmox-node1",
        "type": "lxc",
    }

    with (
        patch("salt.utils.cloud.bootstrap", MagicMock()),
        patch("salt.utils.cloud.filter_event", MagicMock()),
        patch("salt.utils.cloud.fire_event", MagicMock()),
    ):
        proxmox.destroy(call="action", name="my-proxmox-vm", kwargs=destroy_config)
    mock__query.assert_called_with("DELETE", "nodes/proxmox-node1/lxc/123", destroy_config)


def test_destroy_when_called_as_function():
    """
    Test that `clone()` raises an error when called as function
    """
    with pytest.raises(SaltCloudSystemExit):
        proxmox.destroy(call="function")


@patch(_fqn(proxmox._query))
def test_avail_locations(mock__query: MagicMock):
    """
    Test that only nodes with the status online are listed
    """
    mock__query.return_value = [
        {"node": "node1", "status": "online"},
        {"node": "node2", "status": "offline"},
    ]

    result = proxmox.avail_locations(call="function")
    assert result == {
        "node1": {
            "node": "node1",
            "status": "online",
        },
    }


def test_avail_locations_when_called_as_action():
    """
    Test that `avail_locations()` raises an error when called as action
    """
    with pytest.raises(SaltCloudSystemExit):
        proxmox.avail_locations(call="action")


@patch(_fqn(proxmox.avail_locations))
@patch(_fqn(proxmox._query))
def test_avail_images(mock__query: MagicMock, mock_avail_locations: MagicMock):
    """
    Test that avail_images returns images in the correct data structure
    """
    mock_avail_locations.return_value = {"node1": {}}
    mock__query.return_value = [
        {
            "volid": "other_storage:vztmpl/ubuntu-20.04-standard_20.04-1_amd64.tar.zst",
            "content": "vztmpl",
            "size": 129824858,
        },
        {
            "volid": "other_storage:vztmpl/ubuntu-22.04-standard_22.04-1_amd64.tar.zst",
            "content": "vztmpl",
            "size": 129824858,
        },
    ]

    result = proxmox.avail_images(call="function")
    assert result == {
        "node1": {
            "other_storage:vztmpl/ubuntu-20.04-standard_20.04-1_amd64.tar.zst": {
                "volid": "other_storage:vztmpl/ubuntu-20.04-standard_20.04-1_amd64.tar.zst",
                "content": "vztmpl",
                "size": 129824858,
            },
            "other_storage:vztmpl/ubuntu-22.04-standard_22.04-1_amd64.tar.zst": {
                "volid": "other_storage:vztmpl/ubuntu-22.04-standard_22.04-1_amd64.tar.zst",
                "content": "vztmpl",
                "size": 129824858,
            },
        }
    }


@patch(_fqn(proxmox.avail_locations))
@patch(_fqn(proxmox._query))
def test_avail_images_when_storage_given(mock__query: MagicMock, mock_avail_locations: MagicMock):
    """
    Test that avail_images queries given storage
    """
    mock_avail_locations.return_value = {"node1": {}}

    kwargs = {"storage": "other_storage"}
    proxmox.avail_images(call="function", kwargs=kwargs)
    mock__query.assert_called_with("GET", "nodes/node1/storage/other_storage/content")


@patch(_fqn(proxmox.avail_locations))
@patch(_fqn(proxmox._query))
def test_avail_images_when_no_storage_given(
    mock__query: MagicMock, mock_avail_locations: MagicMock
):
    """
    Test that avail_images queries storage "local" when not specifying a storage
    """
    mock_avail_locations.return_value = {"node1": {}}

    proxmox.avail_images(call="function")
    mock__query.assert_called_with("GET", "nodes/node1/storage/local/content")


def test_avail_images_when_called_as_action():
    """
    Test that `avail_images()` raises an error when called as action
    """
    with pytest.raises(SaltCloudSystemExit):
        proxmox.avail_images(call="action")


@patch(_fqn(proxmox._parse_ips))
@patch(_fqn(proxmox._query))
def test_list_nodes(mock__query: MagicMock, mock__parse_ips: MagicMock):
    """
    Test that `list_nodes()` returns a list of managed VMs with the following fields:
        * id
        * size
        * image
        * state
        * private_ips
        * public_ips
    """

    mock__query.return_value = [
        {
            "vmid": 100,
            "status": "stopped",
            "name": "my-proxmox-vm",
            "node": "proxmox",
            "type": "lxc",
        },
    ]

    mock__parse_ips.return_value = ([], [])

    result = proxmox.list_nodes()
    assert result == {
        "my-proxmox-vm": {
            "id": "100",
            "size": "",
            "image": "",
            "state": "stopped",
            "private_ips": [],
            "public_ips": [],
        }
    }


def test_list_nodes_when_called_as_action():
    """
    Test that `list_nodes()` raises an error when called as action
    """
    with pytest.raises(SaltCloudSystemExit):
        proxmox.list_nodes(call="action")


@patch(_fqn(proxmox._query))
def test_list_nodes_full(mock__query: MagicMock):
    """
    Test that `list_nodes_full()` returns a list of managed VMs with their respective config
    """
    # TODO

    _query_responses = [
        # first response (vm resources)
        [
            {
                "vmid": 100,
                "status": "stopped",
                "name": "my-proxmox-vm",
                "node": "proxmox",
                "type": "lxc",
            }
        ],
        # second response (vm config)
        {
            "ostype": "ubuntu",
            "hostname": "my-proxmox-vm",
            "net0": "name=eth0,bridge=vmbr0,hwaddr=BA:F9:3B:F7:9E:A7,ip=192.168.1.2/24,type=veth",
        },
    ]

    mock__query.side_effect = _query_responses

    result = proxmox.list_nodes_full()
    assert result == {
        "my-proxmox-vm": {
            "vmid": 100,
            "status": "stopped",
            "name": "my-proxmox-vm",
            "node": "proxmox",
            "type": "lxc",
            "config": {
                "ostype": "ubuntu",
                "hostname": "my-proxmox-vm",
                "net0": "name=eth0,bridge=vmbr0,hwaddr=BA:F9:3B:F7:9E:A7,ip=192.168.1.2/24,type=veth",
            },
        }
    }


def test_list_nodes_full_when_called_as_action():
    """
    Test that `list_nodes_full()` raises an error when called as action
    """
    with pytest.raises(SaltCloudSystemExit):
        proxmox.list_nodes_full(call="action")


@patch(_fqn(proxmox.list_nodes_full))
def test_show_instance(mock_list_nodes_full: MagicMock):
    mock_list_nodes_full.return_value = {
        "my-proxmox-vm": {
            "vmid": 100,
            "status": "stopped",
            "name": "my-proxmox-vm",
            "node": "proxmox",
            "type": "lxc",
            "config": {
                "ostype": "ubuntu",
                "hostname": "my-proxmox-vm",
                "net0": "name=eth0,bridge=vmbr0,hwaddr=BA:F9:3B:F7:9E:A7,ip=192.168.101.2/24,type=veth",
            },
        }
    }

    result = proxmox.show_instance(call="action", name="my-proxmox-vm")
    assert result == mock_list_nodes_full.return_value["my-proxmox-vm"]


@patch(_fqn(proxmox.list_nodes_full))
def test_show_instance_when_vm_not_found(mock_list_nodes_full):
    """
    Test that `show_instance()` raises an error when no VM with given name exists
    """
    mock_list_nodes_full.return_value = {}

    with pytest.raises(SaltCloudNotFound):
        proxmox.show_instance(call="action", name="my-proxmox-vm")


def test_show_instance_when_called_as_function():
    """
    Test that `show_instance()` raises an error when called as function
    """
    with pytest.raises(SaltCloudSystemExit):
        proxmox.show_instance(call="function")


@patch(_fqn(proxmox._wait_for_vm_status))
@patch(_fqn(proxmox._set_vm_status))
def test_start(mock__set_vm_status: MagicMock, mock__wait_for_vm_status: MagicMock):
    """
    Test that `start()` uses `_set_vm_status()` and `_wait_for_vm_status()` correctly
    """
    name = "my-proxmox-vm"
    kwargs = {"some-optional-argument": True}
    proxmox.start(call="action", name=name, kwargs=kwargs)
    mock__set_vm_status.assert_called_with(name, "start", kwargs)
    mock__wait_for_vm_status.assert_called_with(name, "running")


def test_start_when_called_as_function():
    """
    Test that `start()` raises an error when called as function
    """
    with pytest.raises(SaltCloudSystemExit):
        proxmox.start(call="function")


@patch(_fqn(proxmox._wait_for_vm_status))
@patch(_fqn(proxmox._set_vm_status))
def test_stop(mock__set_vm_status: MagicMock, mock__wait_for_vm_status: MagicMock):
    """
    Test that `stop()` uses `_set_vm_status()` and `_wait_for_vm_status()` correctly
    """
    name = "my-proxmox-vm"
    kwargs = {"some-optional-argument": True}
    proxmox.stop(call="action", name=name, kwargs=kwargs)
    mock__set_vm_status.assert_called_with(name, "stop", kwargs)
    mock__wait_for_vm_status.assert_called_with(name, "stopped")


def test_stop_when_called_as_function():
    """
    Test that `stop()` raises an error when called as function
    """
    with pytest.raises(SaltCloudSystemExit):
        proxmox.stop(call="function")


@patch(_fqn(proxmox._wait_for_vm_status))
@patch(_fqn(proxmox._set_vm_status))
def test_shutdown(mock__set_vm_status: MagicMock, mock__wait_for_vm_status: MagicMock):
    """
    Test that `shutdown()` uses `_set_vm_status()` and `_wait_for_vm_status()` correctly
    """
    name = "my-proxmox-vm"
    kwargs = {"some-optional-argument": True}
    proxmox.shutdown(call="action", name=name, kwargs=kwargs)
    mock__set_vm_status.assert_called_with(name, "shutdown", kwargs)
    mock__wait_for_vm_status.assert_called_with(name, "stopped")


def test_shutdown_when_called_as_function():
    """
    Test that `shutdown()` raises an error when called as function
    """
    with pytest.raises(SaltCloudSystemExit):
        proxmox.shutdown(call="function")


@patch(_fqn(proxmox._get_url))
@patch(_fqn(proxmox._get_api_token))
@patch("requests.get")
def test_detailed_logging_on_http_errors(
    mock_request: MagicMock, mock_get_api_token: MagicMock, mock_get_url: MagicMock, caplog
):
    """
    Test detailed logging on HTTP errors.
    """
    response = requests.Response()
    response.status_code = 400
    response.reason = "Parameter verification failed."
    response.raw = io.BytesIO(
        b"""
        {
            "data": null,
            "errors": {
                "type": "value 'invalid_value' does not have a value in the enumeration 'vm, storage, node, sdn'"
            }
        }
        """
    )

    mock_request.return_value = response
    mock_get_api_token.return_value = "api_token_value"
    mock_get_url.return_value = "proxmox_url_value"

    with pytest.raises(SaltCloudSystemExit) as err:
        proxmox._query("GET", "json/cluster/resources", {"type": "invalid_value"})

    assert response.reason in str(err.value)
    assert response.text in caplog.text


@patch(_fqn(proxmox._query))
def test__get_vm_by_name(mock__query: MagicMock):
    """
    Test that `_get_vm_by_name()` returns the first matching VM
    """
    mock__query.return_value = [
        {"vmid": 100, "name": "duplicate name vm"},
        {"vmid": 200, "name": "duplicate name vm"},
    ]

    result = proxmox._get_vm_by_name("duplicate name vm")
    assert result["vmid"] == 100


@patch(_fqn(proxmox._query))
def test__get_vm_by_name_when_vm_not_found(mock__query: MagicMock):
    """
    Test that `_get_vm_by_name()` raises an error when no VM with given name exists
    """
    mock__query.return_value = []

    with pytest.raises(SaltCloudNotFound):
        proxmox._get_vm_by_name("my-proxmox-vm")


@patch(_fqn(proxmox._query))
def test__get_vm_by_id(mock__query: MagicMock):
    """
    Test that `_get_vm_by_id()` returns the matching VM
    """
    mock__query.return_value = [
        {"vmid": 100, "name": "my-proxmox-vm"},
    ]

    result = proxmox._get_vm_by_id(100)
    assert result["vmid"] == 100


@patch(_fqn(proxmox._query))
def test__get_vm_by_id_when_vm_not_found(mock__query: MagicMock):
    """
    Test that `_get_vm_by_id()` raises an error when no VM with given vmid
    """
    mock__query.return_value = []

    with pytest.raises(SaltCloudNotFound):
        proxmox._get_vm_by_id("my-proxmox-vm")


def test__parse_ips_when_qemu_config():
    """
    Test that `_parse_ips()` handles QEMU configs correctly
    """
    qemu_config = {
        "ipconfig0": "ip=192.168.1.10/24,gw=192.168.1.1",
        "ipconfig1": "ip=200.200.200.200/24,gw=200.200.200.1",
    }

    private_ips, public_ips = proxmox._parse_ips(qemu_config, "qemu")
    assert private_ips == ["192.168.1.10"]
    assert public_ips == ["200.200.200.200"]


def test__parse_ips_when_lxc_config():
    """
    Test that `_parse_ips()` handles LXC configs correctly
    """
    lxc_config = {
        "net0": "name=eth0,bridge=vmbr0,hwaddr=BA:F9:3B:F7:9E:A7,ip=192.168.1.10/24,type=veth",
        "net1": "name=eth1,bridge=vmbr0,hwaddr=B2:4B:C6:39:1D:10,ip=200.200.200.200/24,type=veth",
    }

    private_ips, public_ips = proxmox._parse_ips(lxc_config, "lxc")
    assert private_ips == ["192.168.1.10"]
    assert public_ips == ["200.200.200.200"]


def test__parse_ips_when_missing_config():
    """
    Test that `_parse_ips()` handles missing IPs correctly
    """
    private_ips, public_ips = proxmox._parse_ips({}, "lxc")
    assert not private_ips
    assert not public_ips


def test__parse_ips_when_invalid_config():
    """
    Test that `_parse_ips()` handles invalid IPs correctly
    """
    invalid_ip_config = {
        "net0": "name=eth0,bridge=vmbr0,hwaddr=BA:F9:3B:F7:9E:A7,ip=192.168.500.2/24,type=veth",
    }

    private_ips, public_ips = proxmox._parse_ips(invalid_ip_config, "lxc")
    assert not private_ips
    assert not public_ips


def test__stringlist_to_dictionary():
    """
    Test that a valid stringlist returns a valid dict
    """
    result = proxmox._stringlist_to_dictionary("foo=bar,some_key=some_value")
    assert result == {"foo": "bar", "some_key": "some_value"}


def test__stringlist_to_dictionary_when_empty():
    """
    Test that an empty stringlist returns an empty dict
    """
    result = proxmox._stringlist_to_dictionary("")
    assert result == {}  # pylint: disable=use-implicit-booleaness-not-comparison


def test__stringlist_to_dictionary_when_containing_leading_or_trailing_spaces():
    """
    Test that spaces before and after "key=value" are removed
    """
    result = proxmox._stringlist_to_dictionary("foo=bar, space_before=bar,space_after=bar ")
    assert result == {"foo": "bar", "space_before": "bar", "space_after": "bar"}


def test__stringlist_to_dictionary_when_containing_spaces():
    """
    Test that spaces in key or value persist
    """
    result = proxmox._stringlist_to_dictionary(
        "foo=bar,internal key space=bar,space_in_value= internal value space"
    )
    assert result == {
        "foo": "bar",
        "internal key space": "bar",
        "space_in_value": " internal value space",
    }


def test__stringlist_to_dictionary_when_invalid():
    """
    Test that invalid stringlists raise errors
    """
    with pytest.raises(ValueError):
        proxmox._stringlist_to_dictionary("foo=bar,foo")

    with pytest.raises(ValueError):
        proxmox._stringlist_to_dictionary("foo=bar,totally=invalid=assignment")
