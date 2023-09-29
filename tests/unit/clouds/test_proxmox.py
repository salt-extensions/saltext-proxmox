"""
    :codeauthor: Tyler Johnson <tjohnson@saltstack.com>
"""
import io
import textwrap
import urllib

import pytest
import requests
from salt import config
from saltext.proxmox.clouds import proxmox

from tests.support.mock import ANY
from tests.support.mock import call
from tests.support.mock import MagicMock
from tests.support.mock import patch
from tests.utils.names import fqn


@pytest.fixture
def profile():
    return {
        "my_proxmox": {
            "provider": "my_proxmox",
            "image": "local:some_image.tgz",
        }
    }


@pytest.fixture
def provider_config(profile):
    return {
        "my_proxmox": {
            "proxmox": {
                "driver": "proxmox",
                "url": "pve@domain.com",
                "user": "cloud@pve",
                "password": "verybadpass",
                "profiles": profile,
            }
        }
    }


@pytest.fixture
def vm():
    return {
        "profile": "my_proxmox",
        "name": "vm4",
        "driver": "proxmox",
        "technology": "qemu",
        "host": "127.0.0.1",
        "clone": True,
        "ide0": "data",
        "sata0": "data",
        "scsi0": "data",
        "net0": "a=b,c=d",
    }


@pytest.fixture
def configure_loader_modules(profile, provider_config):
    return {
        proxmox: {
            "__utils__": {
                "cloud.fire_event": MagicMock(),
                "cloud.filter_event": MagicMock(),
                "cloud.bootstrap": MagicMock(),
            },
            "__opts__": {
                "sock_dir": True,
                "transport": True,
                "providers": provider_config,
                "profiles": profile,
            },
            "__active_provider_name__": "my_proxmox:proxmox",
        }
    }


def test___virtual__():
    result = proxmox.__virtual__()
    assert result == "proxmox"


def test__stringlist_to_dictionary():
    result = proxmox._stringlist_to_dictionary("")
    assert not result

    result = proxmox._stringlist_to_dictionary("foo=bar, ignored_space=bar,internal space=bar")
    assert result == {"foo": "bar", "ignored_space": "bar", "internal space": "bar"}

    # Negative cases
    pytest.raises(ValueError, proxmox._stringlist_to_dictionary, "foo=bar,foo")
    pytest.raises(
        ValueError,
        proxmox._stringlist_to_dictionary,
        "foo=bar,totally=invalid=assignment",
    )


def test__dictionary_to_stringlist():
    result = proxmox._dictionary_to_stringlist({})
    assert result == ""

    result = proxmox._dictionary_to_stringlist({"a": "a"})
    assert result == "a=a"

    result = proxmox._dictionary_to_stringlist({"a": "a", "b": "b"})
    assert result == "a=a,b=b"


@patch(fqn(proxmox._get_properties), MagicMock(return_value=["net0", "ide0", "sata0", "scsi0"]))
@patch(fqn(proxmox._query))
def test__reconfigure_clone_net_hdd(mock_query, vm):
    # The return_value is for the net reconfigure assertions, it is irrelevant for the rest
    mock_query.return_value = {"net0": "c=overwritten,g=h"}

    # Test a vm that lacks the required attributes
    proxmox._reconfigure_clone({}, 0)
    mock_query.assert_not_called()

    # Test a fully mocked vm
    proxmox._reconfigure_clone(vm, 0)

    # net reconfigure
    mock_query.assert_any_call("get", "nodes/127.0.0.1/qemu/0/config")
    mock_query.assert_any_call("post", "nodes/127.0.0.1/qemu/0/config", {"net0": "a=b,c=d,g=h"})

    # hdd reconfigure
    mock_query.assert_any_call("post", "nodes/127.0.0.1/qemu/0/config", {"ide0": "data"})
    mock_query.assert_any_call("post", "nodes/127.0.0.1/qemu/0/config", {"sata0": "data"})
    mock_query.assert_any_call("post", "nodes/127.0.0.1/qemu/0/config", {"scsi0": "data"})


@patch(fqn(proxmox._get_properties))
@patch(fqn(proxmox._query))
def test__reconfigure_clone_params(mock_query, mock_get_properties):
    """
    Test cloning a VM with parameters to be reconfigured.
    """
    vmid = 201
    properties = {
        "ide2": "cdrom",
        "sata1": "satatest",
        "scsi0": "bootvol",
        "net0": "model=virtio",
        "agent": "1",
        "args": "argsvalue",
        "balloon": "128",
        "ciuser": "root",
        "cores": "2",
        "description": "desc",
        "memory": "256",
        "name": "new2",
        "onboot": "0",
        "sshkeys": "ssh-rsa ABCDEF user@host\n",
    }
    query_calls = [call("get", "nodes/myhost/qemu/{}/config".format(vmid))]
    for key, value in properties.items():
        if key == "sshkeys":
            value = urllib.parse.quote(value, safe="")
        query_calls.append(
            call(
                "post",
                "nodes/myhost/qemu/{}/config".format(vmid),
                {key: value},
            )
        )

    mock_get_properties.return_value = list(properties.keys())
    mock_query.return_value = ""

    vm_ = {
        "profile": "my_proxmox",
        "driver": "proxmox",
        "technology": "qemu",
        "name": "new2",
        "host": "myhost",
        "clone": True,
        "clone_from": 123,
        "ip_address": "10.10.10.10",
    }
    vm_.update(properties)

    proxmox._reconfigure_clone(vm_, vmid)
    mock_query.assert_has_calls(query_calls, any_order=True)


@patch(fqn(proxmox._get_properties), MagicMock(return_value=["vmid"]))
@patch(fqn(proxmox._get_next_vmid), MagicMock(return_value=ANY))
@patch(fqn(proxmox._query))
def test_clone(mock_query):
    """
    Test that an integer value for clone_from
    """
    vm_ = {
        "technology": "qemu",
        "name": "new2",
        "host": "myhost",
        "clone": True,
        "clone_from": 123,
    }

    # CASE 1: Numeric ID
    result = proxmox._create_node(vm_)
    mock_query.assert_called_once_with(
        "post",
        "nodes/myhost/qemu/123/clone",
        {"newid": ANY},
    )
    assert result == {"vmid": ANY}

    # CASE 2: host:ID notation
    mock_query.reset_mock()
    vm_["clone_from"] = "otherhost:123"
    result = proxmox._create_node(vm_)
    mock_query.assert_called_once_with(
        "post",
        "nodes/otherhost/qemu/123/clone",
        {"newid": ANY},
    )
    assert result == {"vmid": ANY}


@patch(fqn(proxmox._get_properties), MagicMock(return_value=["vmid"]))
@patch(fqn(proxmox._get_next_vmid), MagicMock(return_value=ANY))
@patch(fqn(proxmox._query))
def test_clone_pool(mock_query):
    """
    Test that cloning a VM passes the pool parameter if present
    """
    vm_ = {
        "technology": "qemu",
        "name": "new2",
        "host": "myhost",
        "clone": True,
        "clone_from": 123,
        "pool": "mypool",
    }

    result = proxmox._create_node(vm_)
    mock_query.assert_called_once_with(
        "post",
        "nodes/myhost/qemu/123/clone",
        {"newid": ANY, "pool": "mypool"},
    )
    assert result == {"vmid": ANY}


@patch(fqn(proxmox._get_properties), MagicMock(return_value=["vmid"]))
@patch(fqn(proxmox._get_next_vmid), MagicMock(return_value=101))
@patch(fqn(proxmox._set_vm_status), MagicMock(return_value=True))
@patch(fqn(proxmox._wait_for_state))
@patch(fqn(proxmox._query))
def test_clone_id(mock_query, mock_wait_for_state):
    """
    Test cloning a VM with a specified vmid.
    """
    next_vmid = 101
    explicit_vmid = 201
    upid = "UPID:myhost:00123456:12345678:9ABCDEF0:qmclone:123:root@pam:"

    def mock_query_response(conn_type, option, post_data=None):
        if conn_type == "get" and option == "cluster/tasks":
            return [{"upid": upid, "status": "OK"}]
        if conn_type == "post" and option.endswith("/clone"):
            return upid
        return None

    mock_wait_for_state.return_value = True
    mock_query.side_effect = mock_query_response

    vm_ = {
        "profile": "my_proxmox",
        "driver": "proxmox",
        "technology": "qemu",
        "name": "new2",
        "host": "myhost",
        "clone": True,
        "clone_from": 123,
        "ip_address": "10.10.10.10",
    }

    # CASE 1: No vmid specified in profile (previous behavior)
    proxmox.create(vm_)
    mock_wait_for_state.assert_called_with(
        next_vmid,
        "running",
    )

    # CASE 2: vmid specified in profile
    vm_["vmid"] = explicit_vmid
    proxmox.create(vm_)
    mock_wait_for_state.assert_called_with(
        explicit_vmid,
        "running",
    )


@patch(fqn(proxmox.avail_locations), MagicMock(return_value={"node1": {}}))
@patch(fqn(proxmox._query))
def test_avail_images(mock_query):
    """
    Test avail_images with different values for location parameter
    """

    # CASE 1: location not set should default to "local"
    proxmox.avail_images()
    mock_query.assert_called_with("get", "nodes/{}/storage/{}/content".format("node1", "local"))

    # CASE 2: location set should query location
    kwargs = {"location": "other_storage"}
    proxmox.avail_images(kwargs=kwargs)
    mock_query.assert_called_with(
        "get", "nodes/{}/storage/{}/content".format("node1", kwargs["location"])
    )


@patch(fqn(proxmox._query))
def test_avail_locations(mock_query):
    """
    Test if the available locations make sense
    """
    mock_query.return_value = [
        {
            "node": "node1",
            "status": "online",
        },
        {
            "node": "node2",
            "status": "offline",
        },
    ]

    result = proxmox.avail_locations()
    assert result == {
        "node1": {
            "node": "node1",
            "status": "online",
        },
    }


@patch(fqn(proxmox._query))
def test_find_agent_ips(mock_query):
    """
    Test find_agent_ip will return an IP
    """

    mock_query.return_value = {
        "result": [
            {
                "name": "eth0",
                "ip-addresses": [
                    {"ip-address": "1.2.3.4", "ip-address-type": "ipv4"},
                    {"ip-address": "2001::1:2", "ip-address-type": "ipv6"},
                ],
            },
            {
                "name": "eth1",
                "ip-addresses": [
                    {"ip-address": "2.3.4.5", "ip-address-type": "ipv4"},
                ],
            },
            {
                "name": "dummy",
            },
        ]
    }

    vm_ = {
        "technology": "qemu",
        "host": "myhost",
        "driver": "proxmox",
        "ignore_cidr": "1.0.0.0/8",
    }

    # CASE 1: Test ipv4 and ignore_cidr
    result = proxmox._find_agent_ip(vm_, ANY)
    mock_query.assert_any_call(
        "get", "nodes/myhost/qemu/{}/agent/network-get-interfaces".format(ANY)
    )

    assert result == "2.3.4.5"

    # CASE 2: Test ipv6

    vm_["protocol"] = "ipv6"
    result = proxmox._find_agent_ip(vm_, ANY)
    mock_query.assert_any_call(
        "get", "nodes/myhost/qemu/{}/agent/network-get-interfaces".format(ANY)
    )

    assert result == "2001::1:2"


@patch("salt.config.get_cloud_config_value")
@patch("requests.post")
def test__authenticate_with_token(mock_post, mock_get_cloud_config_value):
    """
    Test that no ticket is requested when using an API token
    """
    get_cloud_config_mock = [
        "fakeuser",
        None,
        True,
        "faketoken",
    ]

    mock_get_cloud_config_value.side_effect = get_cloud_config_mock

    proxmox._authenticate()
    mock_post.assert_not_called()


@patch("salt.config.get_cloud_config_value")
def test__get_url_with_custom_port(mock_get_cloud_config_value):
    """
    Test the use of a custom port for Proxmox connection
    """
    get_cloud_config_mock = [
        "proxmox.connection.url",
        "9999",
    ]

    mock_get_cloud_config_value.side_effect = get_cloud_config_mock

    assert proxmox._get_url() == "https://proxmox.connection.url:9999"


@patch("requests.get")
def _test__import_api(mock_get, response):
    """
    Test _import_api recognition of varying Proxmox VE responses.
    """
    mock_get.return_value.status_code = 200
    mock_get.return_value.text = response

    proxmox._import_api()
    assert proxmox.api == [{"info": {}}]


def test__import_api_v6():
    """
    Test _import_api handling of a Proxmox VE 6 response.
    """
    response = textwrap.dedent(
        """\
        var pveapi = [
            {
                "info" : {
                }
            }
        ]
        ;
        """
    )
    _test__import_api(response=response)  # pylint: disable=no-value-for-parameter


def test__import_api_v7():
    """
    Test _import_api handling of a Proxmox VE 7 response.
    """
    response = textwrap.dedent(
        """\
        const apiSchema = [
            {
                "info" : {
                }
            }
        ]
        ;
        """
    )
    _test__import_api(response=response)  # pylint: disable=no-value-for-parameter


@patch("requests.post")
def test__authenticate_success(mock_post):
    response = requests.Response()
    response.status_code = 200
    response.reason = "OK"
    response.raw = io.BytesIO(
        b"""{"data":{"CSRFPreventionToken":"01234567:dG9rZW4=","ticket":"PVE:cloud@pve:01234567::dGlja2V0"}}"""
    )

    mock_post.return_value = response
    proxmox._authenticate()
    assert proxmox.csrf and proxmox.ticket


@patch("requests.post")
def test__authenticate_failure(mock_post):
    """
    Confirm that authentication failure raises an exception.
    """
    response = requests.Response()
    response.status_code = 401
    response.reason = "authentication failure"
    response.raw = io.BytesIO(b"""{"data":null}""")

    mock_post.return_value = response
    pytest.raises(requests.exceptions.HTTPError, proxmox._authenticate)


@patch(fqn(proxmox._get_properties), MagicMock(return_value=set()))
@patch(fqn(proxmox._query))
def test_creation_failure_logging(mock_query, caplog):
    """
    Test detailed logging on HTTP errors during VM creation.
    """
    vm_ = {
        "profile": "my_proxmox",
        "name": "vm4",
        "technology": "lxc",
        "host": "127.0.0.1",
        "image": "local:some_image.tgz",
        "onboot": True,
    }
    assert (
        config.is_profile_configured(proxmox.__opts__, "my_proxmox:proxmox", "my_proxmox", vm_=vm_)
        is True
    )

    response = requests.Response()
    response.status_code = 400
    response.reason = "Parameter verification failed."
    response.raw = io.BytesIO(
        b"""{"data":null,"errors":{"onboot":"type check ('boolean') failed - got 'True'"}}"""
    )

    def mock_query_response(conn_type, option, post_data=None):
        if conn_type == "get" and option == "cluster/nextid":
            return 104
        if conn_type == "post" and option == "nodes/127.0.0.1/lxc":
            response.raise_for_status()
            return response
        return None

    mock_query.side_effect = mock_query_response

    assert proxmox.create(vm_) is False

    # Search for these messages in a multi-line log entry.
    missing = {
        "{} Client Error: {} for url:".format(response.status_code, response.reason),
        response.text,
    }
    for required in list(missing):
        for record in caplog.records:
            if required in record.message:
                missing.remove(required)
                break
    if missing:
        raise AssertionError("Did not find error messages: {}".format(sorted(list(missing))))
