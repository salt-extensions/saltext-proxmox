"""
    :codeauthor: Bernhard Gally <github.com/I3urny>
"""
import io

import pytest
import requests
from salt.exceptions import SaltCloudSystemExit
from saltext.proxmox.clouds import proxmox

from tests.support.mock import MagicMock
from tests.support.mock import patch


def _fqn(function):
    """
    Return the fully qualified name of a function.
    """
    return ".".join([function.__module__, function.__qualname__])


@pytest.fixture
def configure_loader_modules():
    return {
        proxmox: {
            "__utils__": {
                "cloud.bootstrap": MagicMock(),
                "cloud.filter_event": MagicMock(),
                "cloud.fire_event": MagicMock(),
            },
            "__opts__": {
                "sock_dir": True,
                "transport": True,
            },
            "__active_provider_name__": "",
        }
    }


@patch(_fqn(proxmox.show_instance))
@patch(_fqn(proxmox._query))
def test_create(mock__query: MagicMock, mock_show_instance: MagicMock):
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

    proxmox.create(create_config)
    mock__query.assert_called_with("POST", "nodes/proxmox-node1/qemu", create_config["create"])


@patch(_fqn(proxmox.show_instance))
@patch(_fqn(proxmox.clone))
def test_create_with_clone(mock_clone: MagicMock, mock_show_instance: MagicMock):
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

    proxmox.create(clone_config)
    mock_clone.assert_called()


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


@patch(_fqn(proxmox.avail_locations))
@patch(_fqn(proxmox._query))
def test_avail_images(mock__query: MagicMock, mock_avail_locations: MagicMock):
    """
    Test that avail_images returns images in the correct data structure
    """
    mock_avail_locations.return_value = {"node1": {}}
    mock__query.return_value = [
        {
            "volid": "other_storage:vztmpl/ubuntu-22.04-standard_22.04-1_amd64.tar.zst",
            "content": "vztmpl",
            "size": 129824858,
        },
    ]

    result = proxmox.avail_images(call="function")
    assert result == {
        "node1": {
            "other_storage:vztmpl/ubuntu-22.04-standard_22.04-1_amd64.tar.zst": {
                "volid": "other_storage:vztmpl/ubuntu-22.04-standard_22.04-1_amd64.tar.zst",
                "content": "vztmpl",
                "size": 129824858,
            }
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
    mock__query.assert_called_with(
        "GET", "nodes/{}/storage/{}/content".format("node1", kwargs["storage"])
    )


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
    mock__query.assert_called_with("GET", "nodes/{}/storage/{}/content".format("node1", "local"))


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
    mock__query.return_value = [
        {"vmid": 100, "name": "duplicate name vm"},
        {"vmid": 200, "name": "duplicate name vm"},
    ]

    result = proxmox._get_vm_by_name("duplicate name vm")
    assert result["vmid"] == 100


@patch(_fqn(proxmox._query))
def test__get_vm_by_name_when(mock__query: MagicMock):
    mock__query.return_value = [
        {"vmid": 100, "name": "duplicate name vm"},
        {"vmid": 200, "name": "duplicate name vm"},
    ]

    result = proxmox._get_vm_by_name("duplicate name vm")
    assert result["vmid"] == 100


def test__parse_ips_when_qemu_config():
    qemu_config = {
        "ipconfig0": "ip=192.168.1.10/24,gw=192.168.1.1",
        "ipconfig1": "ip=200.200.200.200/24,gw=200.200.200.1",
    }

    private_ips, public_ips = proxmox._parse_ips(qemu_config, "qemu")
    assert private_ips == ["192.168.1.10"]
    assert public_ips == ["200.200.200.200"]


def test__parse_ips_when_lxc_config():
    lxc_config = {
        "net0": "name=eth0,bridge=vmbr0,hwaddr=BA:F9:3B:F7:9E:A7,ip=192.168.1.10/24,type=veth",
        "net1": "name=eth1,bridge=vmbr0,hwaddr=B2:4B:C6:39:1D:10,ip=200.200.200.200/24,type=veth",
    }

    private_ips, public_ips = proxmox._parse_ips(lxc_config, "lxc")
    assert private_ips == ["192.168.1.10"]
    assert public_ips == ["200.200.200.200"]


def test__parse_ips_when_empty_config():
    private_ips, public_ips = proxmox._parse_ips({}, "lxc")
    assert not private_ips
    assert not public_ips


def test__parse_ips_when_invalid_config():
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
    assert result == dict()


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
