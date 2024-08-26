"""
Proxmox Cloud Module
====================

The Proxmox cloud module is used to control access to Proxmox.

This cloud module is a wrapper for the Proxmox API. As such, all supported parameters
for VM operations (create, clone, start, ...) by the Proxmox API are also
supported through this cloud module.

:maintainer: EITR Technologies, LLC <devops@eitr.tech>
:depends: proxmoxer >= 2.0.1
"""

import logging
import time
from ipaddress import ip_interface

import salt.config
import salt.utils.cloud
from salt.exceptions import SaltCloudExecutionTimeout
from salt.exceptions import SaltCloudNotFound
from salt.exceptions import SaltCloudSystemExit

try:
    from proxmoxer import ProxmoxAPI
    from proxmoxer.tools import Tasks

    HAS_PROXMOXER = True
except ImportError:
    HAS_PROXMOXER = False

# Get logging started
log = logging.getLogger(__name__)

__virtualname__ = "proxmox"


def __virtual__():
    """
    Check for Proxmox configurations
    """
    if get_configured_provider() is False:
        return False

    if get_dependencies() is False:
        return False

    return __virtualname__


def _get_active_provider_name():
    try:
        return __active_provider_name__.value()
    except AttributeError:
        return __active_provider_name__


def get_configured_provider():
    """
    Return the first configured instance.
    """
    return salt.config.is_provider_configured(
        __opts__,
        _get_active_provider_name() or __virtualname__,
        ("host", "user", "token_name", "token_value"),
    )


def get_dependencies():
    """
    Warn if dependencies aren't met.
    """
    deps = {"proxmoxer": HAS_PROXMOXER}
    return salt.config.check_driver_dependencies(__virtualname__, deps)


def create(vm_):
    """
    Create a single Proxmox VM.
    """
    salt.utils.cloud.fire_event(
        "event",
        "starting create",
        f"salt/cloud/{vm_['name']}/creating",
        # calling this via salt.utils.cloud.filter_event causes "name '__opts__' is not defined" error
        args=__utils__["cloud.filter_event"](  # pylint: disable=undefined-variable
            "creating", vm_, ["name", "profile", "provider", "driver"]
        ),
        sock_dir=__opts__["sock_dir"],
        transport=__opts__["transport"],
    )

    try:
        type = vm_["technology"]
    except KeyError as e:
        raise SaltCloudSystemExit(
            f"The VM profile '{vm_['profile']}' is missing the 'technology' parameter."
        ) from e

    clone_options = vm_.get("clone")

    if clone_options:
        clone(call="function", kwargs=clone_options)
    else:
        upid = _get_proxmox_client().post(f"nodes/{vm_['create']['node']}/{type}", **vm_["create"])
        _wait_for_task(upid=upid)

    # sometimes it takes proxmox a while to propagate the information about the new VM
    max_retries = 5
    wait_time = 5
    for _ in range(max_retries):
        try:
            start(call="action", name=vm_["name"])
            break
        except SaltCloudNotFound:
            log.warning(
                "Newly created VM '%s' is not yet listed via the API. Retrying in %s seconds...",
                vm_["name"],
                wait_time,
            )
            time.sleep(wait_time)
    else:
        raise SaltCloudSystemExit(
            f"Failed to start the VM '{vm_['name']}' after {max_retries} attempts."
        )

    # cloud.bootstrap expects the ssh_password to be set in vm_["password"]
    vm_["password"] = vm_.get("ssh_password")
    # calling this via salt.utils.cloud.bootstrap causes "name '__opts__' is not defined" error
    ret = __utils__["cloud.bootstrap"](vm_, __opts__)  # pylint: disable=undefined-variable

    ret.update(show_instance(call="action", name=vm_["name"]))

    salt.utils.cloud.fire_event(
        "event",
        "created instance",
        f"salt/cloud/{vm_['name']}/created",
        # calling this via salt.utils.cloud.filter_event causes "name '__opts__' is not defined" error
        args=__utils__["cloud.filter_event"](  # pylint: disable=undefined-variable
            "created", vm_, ["name", "profile", "provider", "driver"]
        ),
        sock_dir=__opts__["sock_dir"],
        transport=__opts__["transport"],
    )

    return ret


def clone(kwargs=None, call=None):
    """
    Clone a VM

    kwargs
        Parameters to be passed as dict.

    For required and optional parameters please check the Proxmox API documentation:
        * ``https://<PROXMOX_URL>/pve-docs/api-viewer/index.html#/nodes/{node}/lxc/{vmid}/clone``
        * ``https://<PROXMOX_URL>/pve-docs/api-viewer/index.html#/nodes/{node}/qemu/{vmid}/clone``

    CLI Example:

    .. code-block:: bash

        salt-cloud -f clone my-proxmox-config vmid=123 newid=456
    """
    if call != "function":
        raise SaltCloudSystemExit("The clone function must be called with -f or --function.")

    if kwargs is None:
        kwargs = {}

    try:
        vmid = int(kwargs["vmid"])
    except KeyError as e:
        raise SaltCloudSystemExit("The required parameter 'vmid' was not given.") from e

    vm = _get_vm_by_id(vmid)

    upid = _get_proxmox_client().post(f"nodes/{vm['node']}/{vm['type']}/{vmid}/clone", **kwargs)
    _wait_for_task(upid=upid)


def reconfigure(name=None, kwargs=None, call=None):
    """
    Reconfigure a Proxmox VM

    name
        The name of VM to be be reconfigured.

    kwargs
        Addtional parameters to be passed as dict.

    For additional parameters please check the Proxmox API documentation:
        * ``https://<PROXMOX_URL>/pve-docs/api-viewer/index.html#/nodes/{node}/lxc/{vmid}/config``
        * ``https://<PROXMOX_URL>/pve-docs/api-viewer/index.html#/nodes/{node}/qemu/{vmid}/config``

    CLI Example:

    .. code-block:: bash

        salt-cloud -a reconfigure vm_name
    """
    if call == "function":
        raise SaltCloudSystemExit("The reconfigure action must be called with -a or --action.")

    vm = _get_vm_by_name(name)

    if kwargs is None:
        kwargs = {}

    _get_proxmox_client().put(f"nodes/{vm['node']}/{vm['type']}/{vm['vmid']}/config", **kwargs)

    return {
        "success": True,
        "action": "reconfigure",
    }


def destroy(name=None, kwargs=None, call=None):
    """
    Destroy a Proxmox VM by name

    name
        The name of VM to be be destroyed.

    CLI Example:

    .. code-block:: bash

        salt-cloud -d vm_name
    """
    if call == "function":
        raise SaltCloudSystemExit(
            "The destroy action must be called with -d, --destroy, -a or --action."
        )

    salt.utils.cloud.fire_event(
        "event",
        "destroying instance",
        f"salt/cloud/{name}/destroying",
        args={"name": name},
        sock_dir=__opts__["sock_dir"],
        transport=__opts__["transport"],
    )

    vm = _get_vm_by_name(name)

    if kwargs is None:
        kwargs = {}

    _get_proxmox_client().delete(f"nodes/{vm['node']}/{vm['type']}/{vm['vmid']}", **kwargs)

    salt.utils.cloud.fire_event(
        "event",
        "destroyed instance",
        f"salt/cloud/{name}/destroyed",
        args={"name": name},
        sock_dir=__opts__["sock_dir"],
        transport=__opts__["transport"],
    )


def avail_locations(call=None):
    """
    Return available Proxmox datacenter locations (nodes)

    CLI Example:

    .. code-block:: bash

        salt-cloud --list-locations my-proxmox-config
    """
    if call == "action":
        raise SaltCloudSystemExit(
            "The avail_locations function must be called with "
            "-f or --function, or with the --list-locations option"
        )

    locations = _get_proxmox_client().get("nodes")

    ret = {}
    for location in locations:
        name = location["node"]
        if location.get("status") == "online":
            ret[name] = location
        else:
            log.warning("Ignoring Proxmox node '%s' because it is not online.", name)

    return ret


def avail_images(kwargs=None, call=None):
    """
    Return available Proxmox images

    storage
        Name of the storage location that should be searched.

    kwargs
        Addtional parameters to be passed as dict.

    CLI Example:

    .. code-block:: bash

        salt-cloud --list-images my-proxmox-config
        salt-cloud -f avail_images my-proxmox-config storage="storage1"
    """
    if call == "action":
        raise SaltCloudSystemExit(
            "The avail_images function must be called with "
            "-f or --function, or with the --list-images option"
        )

    if kwargs is None:
        kwargs = {}

    storage = kwargs.get("storage", "local")

    ret = {}
    for location in avail_locations():
        ret[location] = {}
        for item in _get_proxmox_client().get(f"nodes/{location}/storage/{storage}/content"):
            if item["content"] in ("images", "vztmpl", "iso"):
                ret[location][item["volid"]] = item

    return ret


def list_nodes(call=None):
    """
    Return a list of the VMs that are managed by the provider

    CLI Example:

    .. code-block:: bash

        salt-cloud -Q
        salt-cloud -f list_nodes my-proxmox-config
    """
    if call == "action":
        raise SaltCloudSystemExit("The list_nodes function must be called with -f or --function.")

    vms = list_nodes_full(call="function")

    ret = {}
    for vm, props in vms.items():
        ret[vm] = {}

        for prop in ("id", "image", "private_ips", "public_ips", "size", "state"):
            ret[vm][prop] = props[prop]

    return ret


def list_nodes_full(call=None):
    """
    Return a list of the VMs that are managed by the provider, with full configuration details

    CLI Example:

    .. code-block:: bash

        salt-cloud -F
        salt-cloud -f list_nodes_full my-proxmox-config
    """
    if call == "action":
        raise SaltCloudSystemExit(
            "The list_nodes_full function must be called with -f or --function."
        )

    vms = _get_proxmox_client().get("cluster/resources", type="vm")

    ret = {}
    for vm in vms:
        name = vm["name"]

        config = _get_proxmox_client().get(f"nodes/{vm['node']}/{vm['type']}/{vm['vmid']}/config")
        private_ips, public_ips = _parse_ips(config, vm["type"])

        ret[name] = {}
        ret[name]["id"] = str(vm["vmid"])
        ret[name]["image"] = ""  # proxmox does not carry that information
        ret[name]["private_ips"] = private_ips
        ret[name]["public_ips"] = public_ips
        ret[name]["size"] = ""  # proxmox does not have VM sizes like AWS (e.g: t2-small)
        ret[name]["state"] = str(vm["status"])
        ret[name]["config"] = config
        ret[name]["resource"] = vm

    return ret


def list_nodes_select(call=None):
    """
    Return a list of the VMs that are managed by the provder, with select fields
    """
    return salt.utils.cloud.list_nodes_select(
        list_nodes_full(),
        __opts__["query.selection"],
        call,
    )


def show_instance(name=None, call=None):
    """
    Show the details from Proxmox concerning an instance

    name
        The name of the VM for which to display details.

    CLI Example:

    .. code-block:: bash

        salt-cloud -a show_instance vm_name
    """
    if call != "action":
        raise SaltCloudSystemExit("The show_instance action must be called with -a or --action.")

    for k, v in list_nodes_full().items():
        if k == name:
            return v

    raise SaltCloudNotFound(f"The specified VM named '{name}' could not be found.")


def start(name=None, kwargs=None, call=None):
    """
    Start a node.

    name
        The name of the VM. Required.

    kwargs
        Addtional parameters to be passed as dict.

    For additional parameters please check the Proxmox API documentation:
        * ``https://<PROXMOX_URL>/pve-docs/api-viewer/index.html#/nodes/{node}/lxc/{vmid}/status/start``
        * ``https://<PROXMOX_URL>/pve-docs/api-viewer/index.html#/nodes/{node}/qemu/{vmid}/status/start``

    CLI Example:

    .. code-block:: bash

        salt-cloud -a start vm_name
    """
    if call != "action":
        raise SaltCloudSystemExit("The start action must be called with -a or --action.")

    _set_vm_status(name, "start", kwargs)

    return {
        "success": True,
        "state": "running",
        "action": "start",
    }


def stop(name=None, kwargs=None, call=None):
    """
    Stop a node.

    For additional parameters please check the Proxmox API documentation:
        * ``https://<PROXMOX_URL>/pve-docs/api-viewer/index.html#/nodes/{node}/lxc/{vmid}/status/stop``
        * ``https://<PROXMOX_URL>/pve-docs/api-viewer/index.html#/nodes/{node}/qemu/{vmid}/status/stop``

    name
        The name of the VM. Required.

    kwargs
        Addtional parameters to be passed as dict.

    CLI Example:

    .. code-block:: bash

        salt-cloud -a stop vm_name
    """
    if call != "action":
        raise SaltCloudSystemExit("The stop action must be called with -a or --action.")

    _set_vm_status(name, "stop", kwargs)

    return {
        "success": True,
        "state": "stopped",
        "action": "stop",
    }


def shutdown(name=None, kwargs=None, call=None):
    """
    Shutdown a node.

    name
        The name of the VM. Required.

    kwargs
        Addtional parameters to be passed as dict.

    For additional parameters please check the Proxmox API documentation:
        * ``https://<PROXMOX_URL>/pve-docs/api-viewer/index.html#/nodes/{node}/lxc/{vmid}/status/shutdown``
        * ``https://<PROXMOX_URL>/pve-docs/api-viewer/index.html#/nodes/{node}/qemu/{vmid}/status/shutdown``

    CLI Example:

    .. code-block:: bash

        salt-cloud -a shutdown vm_name
    """
    if call != "action":
        raise SaltCloudSystemExit("The shutdown action must be called with -a or --action.")

    _set_vm_status(name, "shutdown", kwargs)

    return {
        "success": True,
        "state": "stopped",
        "action": "shutdown",
    }


def _get_vm_by_name(name):
    """
    Return VM identified by name

    name
        The name of the VM. Required.

    .. note:

        This function will return the first occurrence of a VM matching the given name.
    """
    vms = _get_proxmox_client().get("cluster/resources", type="vm")

    for vm in vms:
        if vm["name"] == name:
            return vm

    raise SaltCloudNotFound(f"The specified VM with name '{name}' could not be found.")


def _get_vm_by_id(vmid):
    """
    Return VM identified by vmid.

    vmid
        The vmid of the VM. Required.
    """
    vms = _get_proxmox_client().get("cluster/resources", type="vm")

    for vm in vms:
        if vm["vmid"] == vmid:
            return vm

    raise SaltCloudNotFound(f"The specified VM with vmid '{vmid}' could not be found.")


def _set_vm_status(name, status, kwargs=None):
    """
    Set the VM status

    name
        The name of the VM. Required.

    status
        The target status of the VM. Required.

    kwargs
        Addtional parameters to be passed as dict.
    """
    vm = _get_vm_by_name(name)

    if kwargs is None:
        kwargs = {}

    upid = _get_proxmox_client().post(
        f"nodes/{vm['node']}/{vm['type']}/{vm['vmid']}/status/{status}", **kwargs
    )
    _wait_for_task(upid=upid)


def _wait_for_task(upid, timeout=300, interval=0.2):
    """
    Wait for the task to finish successfully

    upid
        The UPID of the task. Required.

    timeout
        The timeout in seconds on how long to wait for the task. Default: 300 seconds

    interval
        The interval in seconds at which the API should be queried for updates. Default: 0.2 seconds
    """
    node = Tasks.decode_upid(upid=upid)["node"]
    response = {"status": ""}

    start_time = time.monotonic()
    while response["status"] != "stopped":
        if time.monotonic() >= start_time + timeout:
            raise SaltCloudExecutionTimeout(f"Timeout to wait for task '{upid}' reached.")

        response = _get_proxmox_client().get(f"nodes/{node}/tasks/{upid}/status")
        time.sleep(interval)

    if "failed" in response["exitstatus"]:
        raise SaltCloudSystemExit(f"Task did not finish successfully: {response['exitstatus']}")

    return response


def _get_proxmox_client():
    host = salt.config.get_cloud_config_value(
        "host", get_configured_provider(), __opts__, search_global=False
    )
    user = salt.config.get_cloud_config_value(
        "user", get_configured_provider(), __opts__, search_global=False
    )
    token_name = salt.config.get_cloud_config_value(
        "token_name", get_configured_provider(), __opts__, search_global=False
    )
    token_value = salt.config.get_cloud_config_value(
        "token_value", get_configured_provider(), __opts__, search_global=False
    )

    return ProxmoxAPI(
        host=host,
        backend="https",
        service="PVE",
        user=user,
        token_name=token_name,
        token_value=token_value,
    )


def _stringlist_to_dictionary(input_string):
    """
    Convert a stringlist (comma separated settings) to a dictionary

    The result of the string "setting1=value1,setting2=value2" will be a python dictionary:

    {'setting1':'value1','setting2':'value2'}
    """
    return dict(item.strip().split("=") for item in input_string.split(",") if item)


def _parse_ips(vm_config, vm_type):
    """
    Parse IPs from a Proxmox VM config
    """
    private_ips = []
    public_ips = []

    ip_configs = []
    if vm_type == "lxc":
        ip_configs = [v for k, v in vm_config.items() if k.startswith("net")]
    else:
        ip_configs = [v for k, v in vm_config.items() if k.startswith("ipconfig")]

    for ip_config in ip_configs:
        try:
            ip_with_netmask = _stringlist_to_dictionary(ip_config).get("ip")
            ip = ip_interface(ip_with_netmask).ip

            if ip.is_private:
                private_ips.append(str(ip))
            else:
                public_ips.append(str(ip))
        except ValueError:
            log.error("Ignoring '%s' because it is not a valid IP", ip_with_netmask)

    return private_ips, public_ips
