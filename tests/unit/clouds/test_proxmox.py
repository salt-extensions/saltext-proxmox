"""
:maintainer: EITR Technologies, LLC <devops@eitr.tech>
"""

import pytest
from salt.exceptions import SaltCloudExecutionTimeout
from salt.exceptions import SaltCloudNotFound
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
            "__opts__": {
                "sock_dir": True,
                "transport": True,
            },
            "__utils__": {
                "cloud.filter_event": MagicMock(),
            },
            "__active_provider_name__": "",
        }
    }


@patch(_fqn(proxmox.show_instance))
@patch(_fqn(proxmox._wait_for_task))
@patch(_fqn(proxmox.start))
@patch(_fqn(proxmox._get_proxmox_client))
def test_create(
    mock__get_proxmox_client: MagicMock,
    mock_start: MagicMock,
    mock__wait_for_task: MagicMock,
    mock_show_instance: MagicMock,
):
    """
    Test that `create()` calls the correct endpoint with the correct arguments and waits for VM creation
    """
    create_config = {
        "name": "my-vm",
        "technology": "qemu",
        "create": {
            "vmid": 123,
            "node": "proxmox-node1",
        },
    }

    upid = "UPID:node1:0016BEC6:568EF5F4:669FB044:qmcreate:101:user@pam!mytoken:"
    mock__get_proxmox_client.return_value.post.return_value = upid

    with patch("salt.utils.cloud.bootstrap", MagicMock()), patch(
        "salt.utils.cloud.fire_event", MagicMock()
    ):
        proxmox.create(create_config)

    mock__get_proxmox_client.return_value.post.assert_called_with(
        "nodes/proxmox-node1/qemu", **create_config["create"]
    )
    mock__wait_for_task.assert_called_once_with(upid=upid)


def test_create_with_missing_technology_argument():
    """
    Test that `create()` fails when the 'technology' argument is missing in the profile configuration
    """
    create_config = {
        "name": "my-vm",
        "profile": "my-vm-profile",
        "create": {
            "vmid": 123,
            "node": "proxmox-node1",
        },
    }

    with pytest.raises(SaltCloudSystemExit), patch(
        "salt.utils.cloud.bootstrap", MagicMock()
    ), patch("salt.utils.cloud.fire_event", MagicMock()):
        proxmox.create(create_config)


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

    with patch("salt.utils.cloud.bootstrap", MagicMock()), patch(
        "salt.utils.cloud.fire_event", MagicMock()
    ):
        proxmox.create(clone_config)

    mock_clone.assert_called()


@patch(_fqn(proxmox._wait_for_task))
@patch(_fqn(proxmox._get_vm_by_id))
@patch(_fqn(proxmox._get_proxmox_client))
def test_clone(
    mock__get_proxmox_client: MagicMock,
    mock__get_vm_by_id: MagicMock,
    mock__wait_for_task: MagicMock,
):
    """
    Test that `clone()` calls the correct endpoint with the correct arguments and waits for VM creation
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

    upid = "UPID:node1:0016BEC6:568EF5F4:669FB044:qmclone:101:user@pam!mytoken:"
    mock__get_proxmox_client.return_value.post.return_value = upid

    proxmox.clone(call="function", kwargs=clone_config)

    mock__get_proxmox_client.return_value.post.assert_called_with(
        "nodes/proxmox-node1/lxc/123/clone", **clone_config
    )
    mock__wait_for_task.assert_called_once_with(upid=upid)


def test_clone_with_missing_vmid_argument():
    """
    Test that `clone()` fails when the 'vmid' argument is missing
    """
    with pytest.raises(SaltCloudSystemExit):
        proxmox.clone(call="function")


def test_clone_when_called_as_action():
    """
    Test that `clone()` raises an error when called as action
    """
    with pytest.raises(SaltCloudSystemExit):
        proxmox.clone(call="action")


@patch(_fqn(proxmox._get_vm_by_name))
@patch(_fqn(proxmox._get_proxmox_client))
def test_reconfigure(mock__get_proxmox_client: MagicMock, mock__get_vm_by_name: MagicMock):
    """
    Test that `reconfigure()` calls the correct endpoint with the correct arguments
    """
    reconfigure_config = {"description": "custom description to be updated"}

    mock__get_vm_by_name.return_value = {
        "vmid": 123,
        "name": "my-proxmox-vm",
        "node": "proxmox-node1",
        "type": "lxc",
    }

    proxmox.reconfigure(call="action", name="my-proxmox-vm", kwargs=reconfigure_config)

    mock__get_proxmox_client.return_value.put.assert_called_with(
        "nodes/proxmox-node1/lxc/123/config", **reconfigure_config
    )


@patch(_fqn(proxmox._get_vm_by_name))
@patch(_fqn(proxmox._get_proxmox_client))
def test_reconfigure_with_no_arguments(
    mock__get_proxmox_client: MagicMock,
    mock__get_vm_by_name: MagicMock,
):
    """
    Test that `reconfigure()` calls the endpoint correctly with no arguments
    """
    mock__get_vm_by_name.return_value = {
        "vmid": 123,
        "name": "my-proxmox-vm",
        "node": "proxmox-node1",
        "type": "lxc",
    }

    proxmox.reconfigure(call="action", name="my-proxmox-vm")

    mock__get_proxmox_client.return_value.put.assert_called_with(
        "nodes/proxmox-node1/lxc/123/config"
    )


def test_reconfigure_when_called_as_function():
    """
    Test that `reconfigure()` raises an error when called as function
    """
    with pytest.raises(SaltCloudSystemExit):
        proxmox.reconfigure(call="function")


@patch(_fqn(proxmox._get_vm_by_name))
@patch(_fqn(proxmox._get_proxmox_client))
def test_destroy(mock__get_proxmox_client: MagicMock, mock__get_vm_by_name: MagicMock):
    """
    Test that `clone()` calls the correct endpoint with the correct arguments
    """
    destroy_config = {"force": True}

    mock__get_vm_by_name.return_value = {
        "vmid": 123,
        "name": "my-proxmox-vm",
        "node": "proxmox-node1",
        "type": "lxc",
    }

    with patch("salt.utils.cloud.fire_event", MagicMock()):
        proxmox.destroy(call="action", name="my-proxmox-vm", kwargs=destroy_config)

    mock__get_proxmox_client.return_value.delete.assert_called_with(
        "nodes/proxmox-node1/lxc/123", **destroy_config
    )


@patch(_fqn(proxmox._get_vm_by_name))
@patch(_fqn(proxmox._get_proxmox_client))
def test_destroy_with_no_arguments(
    mock__get_proxmox_client: MagicMock,
    mock__get_vm_by_name: MagicMock,
):
    """
    Test that `clone()` calls the endpoint correctly with no arguments
    """
    mock__get_vm_by_name.return_value = {
        "vmid": 123,
        "name": "my-proxmox-vm",
        "node": "proxmox-node1",
        "type": "lxc",
    }

    with patch("salt.utils.cloud.fire_event", MagicMock()):
        proxmox.destroy(call="action", name="my-proxmox-vm")

    mock__get_proxmox_client.return_value.delete.assert_called_with("nodes/proxmox-node1/lxc/123")


def test_destroy_when_called_as_function():
    """
    Test that `clone()` raises an error when called as function
    """
    with pytest.raises(SaltCloudSystemExit):
        proxmox.destroy(call="function")


@patch(_fqn(proxmox._get_proxmox_client))
def test_avail_locations(mock__get_proxmox_client: MagicMock):
    """
    Test that only nodes with the status online are listed
    """
    mock__get_proxmox_client.return_value.get.return_value = [
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
@patch(_fqn(proxmox._get_proxmox_client))
def test_avail_images(mock__get_proxmox_client: MagicMock, mock_avail_locations: MagicMock):
    """
    Test that avail_images returns images (content type: vztmpl, images or iso) in the correct data structure
    """
    mock_avail_locations.return_value = {"node1": {}}
    mock__get_proxmox_client.return_value.get.return_value = [
        {
            "volid": "other_storage:vztmpl/ubuntu-20.04-standard_20.04-1_amd64.tar.gz",
            "content": "vztmpl",
        },
        {
            "volid": "other_storage:vztmpl/ubuntu-22.04-standard_22.04-1_amd64.tar.zst",
            "content": "vztmpl",
        },
        {
            "volid": "other_storage:vm-201-disk-0",
            "content": "images",
        },
        {
            "volid": "other_storage:iso/ubuntu-22.04.2-live-server-amd64.iso",
            "content": "iso",
        },
        {
            "volid": "other_storage:backup/template-backup.tar.gz",
            "content": "backup",
        },
    ]

    result = proxmox.avail_images(call="function")

    assert result == {
        "node1": {
            "other_storage:vztmpl/ubuntu-20.04-standard_20.04-1_amd64.tar.gz": {
                "volid": "other_storage:vztmpl/ubuntu-20.04-standard_20.04-1_amd64.tar.gz",
                "content": "vztmpl",
            },
            "other_storage:vztmpl/ubuntu-22.04-standard_22.04-1_amd64.tar.zst": {
                "volid": "other_storage:vztmpl/ubuntu-22.04-standard_22.04-1_amd64.tar.zst",
                "content": "vztmpl",
            },
            "other_storage:vm-201-disk-0": {
                "volid": "other_storage:vm-201-disk-0",
                "content": "images",
            },
            "other_storage:iso/ubuntu-22.04.2-live-server-amd64.iso": {
                "volid": "other_storage:iso/ubuntu-22.04.2-live-server-amd64.iso",
                "content": "iso",
            },
        }
    }


@patch(_fqn(proxmox.avail_locations))
@patch(_fqn(proxmox._get_proxmox_client))
def test_avail_images_when_storage_given(
    mock__get_proxmox_client: MagicMock, mock_avail_locations: MagicMock
):
    """
    Test that avail_images queries given storage
    """
    mock_avail_locations.return_value = {"node1": {}}
    kwargs = {"storage": "other_storage"}

    proxmox.avail_images(call="function", kwargs=kwargs)

    mock__get_proxmox_client.return_value.get.assert_called_with(
        "nodes/node1/storage/other_storage/content"
    )


@patch(_fqn(proxmox.avail_locations))
@patch(_fqn(proxmox._get_proxmox_client))
def test_avail_images_when_no_storage_given(
    mock__get_proxmox_client: MagicMock, mock_avail_locations: MagicMock
):
    """
    Test that avail_images queries storage "local" when not specifying a storage
    """
    mock_avail_locations.return_value = {"node1": {}}

    proxmox.avail_images(call="function")

    mock__get_proxmox_client.return_value.get.assert_called_with(
        "nodes/node1/storage/local/content"
    )


def test_avail_images_when_called_as_action():
    """
    Test that `avail_images()` raises an error when called as action
    """
    with pytest.raises(SaltCloudSystemExit):
        proxmox.avail_images(call="action")


@patch(_fqn(proxmox.list_nodes_full))
def test_list_nodes(mock_list_nodes_full: MagicMock):
    """
    Test that `list_nodes()` returns a list of managed VMs with the following fields:
        * id
        * image
        * private_ips
        * public_ips
        * size
        * state
    """
    mock_list_nodes_full.return_value = {
        "my-proxmox-vm1": {
            "id": "100",
            "image": "",
            "private_ips": ["192.168.1.2"],
            "public_ips": [],
            "size": "",
            "state": "stopped",
            "config": {
                "ostype": "ubuntu",
                "hostname": "my-proxmox-vm1",
                "net0": "name=eth0,bridge=vmbr0,hwaddr=BA:F9:3B:F7:9E:A7,ip=192.168.1.2/24,type=veth",
            },
            "resource": {
                "vmid": 100,
                "name": "my-proxmox-vm1",
                "status": "stopped",
                "node": "node1",
                "type": "lxc",
                "maxcpu": 2,
                "maxdisk": 123456,
            },
        },
    }

    result = proxmox.list_nodes()

    assert result == {
        "my-proxmox-vm1": {
            "id": "100",
            "image": "",
            "private_ips": ["192.168.1.2"],
            "public_ips": [],
            "size": "",
            "state": "stopped",
        }
    }


def test_list_nodes_when_called_as_action():
    """
    Test that `list_nodes()` raises an error when called as action
    """
    with pytest.raises(SaltCloudSystemExit):
        proxmox.list_nodes(call="action")


@patch(_fqn(proxmox._get_proxmox_client))
def test_list_nodes_full(mock__get_proxmox_client: MagicMock):
    """
    Test that `list_nodes_full()` returns a list of managed VMs with their respective config
    """
    responses = [
        # first response (all vm resources)
        [
            {
                "vmid": 100,
                "name": "my-proxmox-vm1",
                "status": "stopped",
                "node": "node1",
                "type": "lxc",
                "maxcpu": 2,
                "maxdisk": 123456,
            },
            {
                "vmid": 101,
                "name": "my-proxmox-vm2",
                "status": "stopped",
                "node": "node1",
                "type": "lxc",
                "maxcpu": 4,
                "maxdisk": 234567,
            },
        ],
        # second response (vm configs)
        {
            "ostype": "ubuntu",
            "hostname": "my-proxmox-vm1",
            "net0": "name=eth0,bridge=vmbr0,hwaddr=BA:F9:3B:F7:9E:A7,ip=192.168.1.2/24,type=veth",
        },
        {
            "ostype": "ubuntu",
            "hostname": "my-proxmox-vm2",
            "net0": "name=eth0,bridge=vmbr0,hwaddr=BA:F9:3B:F7:9E:A8,ip=192.168.1.3/24,type=veth",
        },
    ]

    mock__get_proxmox_client.return_value.get.side_effect = responses

    result = proxmox.list_nodes_full()

    assert result == {
        "my-proxmox-vm1": {
            "id": "100",
            "image": "",
            "private_ips": ["192.168.1.2"],
            "public_ips": [],
            "size": "",
            "state": "stopped",
            "config": {
                "ostype": "ubuntu",
                "hostname": "my-proxmox-vm1",
                "net0": "name=eth0,bridge=vmbr0,hwaddr=BA:F9:3B:F7:9E:A7,ip=192.168.1.2/24,type=veth",
            },
            "resource": {
                "vmid": 100,
                "name": "my-proxmox-vm1",
                "status": "stopped",
                "node": "node1",
                "type": "lxc",
                "maxcpu": 2,
                "maxdisk": 123456,
            },
        },
        "my-proxmox-vm2": {
            "id": "101",
            "image": "",
            "private_ips": ["192.168.1.3"],
            "public_ips": [],
            "size": "",
            "state": "stopped",
            "config": {
                "ostype": "ubuntu",
                "hostname": "my-proxmox-vm2",
                "net0": "name=eth0,bridge=vmbr0,hwaddr=BA:F9:3B:F7:9E:A8,ip=192.168.1.3/24,type=veth",
            },
            "resource": {
                "vmid": 101,
                "name": "my-proxmox-vm2",
                "status": "stopped",
                "node": "node1",
                "type": "lxc",
                "maxcpu": 4,
                "maxdisk": 234567,
            },
        },
    }


def test_list_nodes_full_when_called_as_action():
    """
    Test that `list_nodes_full()` raises an error when called as action
    """
    with pytest.raises(SaltCloudSystemExit):
        proxmox.list_nodes_full(call="action")


@patch(_fqn(proxmox.list_nodes_full))
def test_show_instance(mock_list_nodes_full: MagicMock):
    """
    Test that `show_instance()` returns full information of requested node
    """
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


@patch(_fqn(proxmox._set_vm_status))
def test_start(mock__set_vm_status: MagicMock):
    """
    Test that `start()` uses `_set_vm_status()` correctly
    """
    name = "my-proxmox-vm"
    kwargs = {"some-optional-argument": True}

    proxmox.start(call="action", name=name, kwargs=kwargs)

    mock__set_vm_status.assert_called_with(name, "start", kwargs)


def test_start_when_called_as_function():
    """
    Test that `start()` raises an error when called as function
    """
    with pytest.raises(SaltCloudSystemExit):
        proxmox.start(call="function")


@patch(_fqn(proxmox._set_vm_status))
def test_stop(mock__set_vm_status: MagicMock):
    """
    Test that `stop()` uses `_set_vm_status() correctly
    """
    name = "my-proxmox-vm"
    kwargs = {"some-optional-argument": True}

    proxmox.stop(call="action", name=name, kwargs=kwargs)

    mock__set_vm_status.assert_called_with(name, "stop", kwargs)


def test_stop_when_called_as_function():
    """
    Test that `stop()` raises an error when called as function
    """
    with pytest.raises(SaltCloudSystemExit):
        proxmox.stop(call="function")


@patch(_fqn(proxmox._set_vm_status))
def test_shutdown(mock__set_vm_status: MagicMock):
    """
    Test that `shutdown()` uses `_set_vm_status()` correctly
    """
    name = "my-proxmox-vm"
    kwargs = {"some-optional-argument": True}

    proxmox.shutdown(call="action", name=name, kwargs=kwargs)

    mock__set_vm_status.assert_called_with(name, "shutdown", kwargs)


def test_shutdown_when_called_as_function():
    """
    Test that `shutdown()` raises an error when called as function
    """
    with pytest.raises(SaltCloudSystemExit):
        proxmox.shutdown(call="function")


@patch(_fqn(proxmox._get_proxmox_client))
def test__get_vm_by_name(mock__get_proxmox_client: MagicMock):
    """
    Test that `_get_vm_by_name()` returns the first matching VM
    """
    mock__get_proxmox_client.return_value.get.return_value = [
        {"vmid": 100, "name": "duplicate name vm"},
        {"vmid": 200, "name": "duplicate name vm"},
    ]

    result = proxmox._get_vm_by_name("duplicate name vm")

    assert result["vmid"] == 100


@patch(_fqn(proxmox._get_proxmox_client))
def test__get_vm_by_name_when_vm_not_found(mock__get_proxmox_client: MagicMock):
    """
    Test that `_get_vm_by_name()` raises an error when no VM with given name exists
    """
    mock__get_proxmox_client.return_value.get.return_value = []

    with pytest.raises(SaltCloudNotFound):
        proxmox._get_vm_by_name("my-proxmox-vm")


@patch(_fqn(proxmox._get_proxmox_client))
def test__get_vm_by_id(mock__get_proxmox_client: MagicMock):
    """
    Test that `_get_vm_by_id()` returns the matching VM
    """
    mock__get_proxmox_client.return_value.get.return_value = [
        {"vmid": 100, "name": "my-proxmox-vm"},
    ]

    result = proxmox._get_vm_by_id(100)

    assert result["vmid"] == 100


@patch(_fqn(proxmox._get_proxmox_client))
def test__get_vm_by_id_when_vm_not_found(mock__get_proxmox_client: MagicMock):
    """
    Test that `_get_vm_by_id()` raises an error when no VM with given vmid
    """
    mock__get_proxmox_client.return_value.get.return_value = []

    with pytest.raises(SaltCloudNotFound):
        proxmox._get_vm_by_id("my-proxmox-vm")


@patch(_fqn(proxmox._wait_for_task))
@patch(_fqn(proxmox._get_vm_by_name))
@patch(_fqn(proxmox._get_proxmox_client))
def test__set_vm_status(
    mock__get_proxmox_client: MagicMock,
    mock__get_vm_by_name: MagicMock,
    mock__wait_for_task: MagicMock,
):
    """
    Test that _set_vm_status calls the endpoint with all arguments and waits for the task to finish
    """
    mock__get_vm_by_name.return_value = {
        "name": "my-vm",
        "vmid": "101",
        "type": "qemu",
        "node": "node1",
    }

    upid = "UPID:node1:0016BEC6:568EF5F4:669FB044:qmstop:101:user@pam!mytoken:"
    mock__get_proxmox_client.return_value.post.return_value = upid
    kwargs = {"forceStop": 1, "timeout": 30}

    proxmox._set_vm_status(name="my-vm", status="stop", kwargs=kwargs)

    mock__get_proxmox_client.return_value.post.assert_called_once_with(
        "nodes/node1/qemu/101/status/stop", **kwargs
    )
    mock__wait_for_task.assert_called_once_with(upid=upid)


@patch(_fqn(proxmox._wait_for_task))
@patch(_fqn(proxmox._get_vm_by_name))
@patch(_fqn(proxmox._get_proxmox_client))
def test__set_vm_status_with_no_arguments(
    mock__get_proxmox_client: MagicMock,
    mock__get_vm_by_name: MagicMock,
    mock__wait_for_task: MagicMock,
):
    """
    Test that _set_vm_status calls the endpoint correctly with no arguments
    """
    mock__get_vm_by_name.return_value = {
        "name": "my-vm",
        "vmid": "101",
        "type": "qemu",
        "node": "node1",
    }

    upid = "UPID:node1:0016BEC6:568EF5F4:669FB044:qmstop:101:user@pam!mytoken:"
    mock__get_proxmox_client.return_value.post.return_value = upid

    proxmox._set_vm_status(name="my-vm", status="stop")

    mock__get_proxmox_client.return_value.post.assert_called_once_with(
        "nodes/node1/qemu/101/status/stop"
    )


@patch(_fqn(proxmox._get_proxmox_client))
def test__wait_for_task(mock__get_proxmox_client: MagicMock):
    response = {"status": "stopped", "exitstatus": "OK"}

    mock__get_proxmox_client.return_value.get.return_value = response
    upid = "UPID:node1:0016BEC6:568EF5F4:669FB044:qmstart:101:user@pam!mytoken:"

    result = proxmox._wait_for_task(upid=upid, timeout=1)

    assert response == result


@patch(_fqn(proxmox._get_proxmox_client))
def test__wait_for_task_when_timeout_reached(mock__get_proxmox_client: MagicMock):
    response = {"status": "running"}

    mock__get_proxmox_client.return_value.get.return_value = response
    upid = "UPID:node1:0016BEC6:568EF5F4:669FB044:qmstart:101:user@pam!mytoken:"

    with pytest.raises(SaltCloudExecutionTimeout):
        proxmox._wait_for_task(upid=upid, timeout=1)


@patch(_fqn(proxmox._get_proxmox_client))
def test__wait_for_task_when_task_failed(mock__get_proxmox_client: MagicMock):
    response = {"status": "stopped", "exitstatus": "VM quit/powerdown failed - got timeout"}

    mock__get_proxmox_client.return_value.get.return_value = response
    upid = "UPID:node1:0016BEC6:568EF5F4:669FB044:qmshutdown:101:user@pam!mytoken:"

    with pytest.raises(SaltCloudSystemExit):
        proxmox._wait_for_task(upid=upid, timeout=1)


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
