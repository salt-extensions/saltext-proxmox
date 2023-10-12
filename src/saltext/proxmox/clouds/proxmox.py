"""
Proxmox Cloud Module
======================

The Proxmox cloud module is used to control access to Proxmox

Set up the cloud configuration at ``/etc/salt/cloud.providers`` or
 ``/etc/salt/cloud.providers.d/proxmox.conf``:

.. code-block:: yaml

    my-proxmox-config:
      # Required parameters
      user: myuser@pam # or myuser@pve
      token: myapitoken
      url: https://hypervisor.domain.tld:8006
      driver: proxmox

Profile configuration examples:

.. collapse:: Create a new LXC container

    .. code-block:: yaml

        my-lxc-container:
            provider: my-proxmox-config
            technology: lxc

            # Required for cloud.bootstrap()
            ssh_host: 192.168.101.2
            ssh_username: root
            ssh_password: supersecret

            create:
                # For parameters check https://<PROXMOX_URL>/pve-docs/api-viewer/index.html#/nodes/{node}/lxc
                vmid: 123
                ostemplate:  local:vztmpl/ubuntu-22.04-standard_22.04-1_amd64.tar.zst
                node: proxmox-node1

                net0: name=eth0,bridge=vmbr0,firewall=1,gw=192.168.101.1,ip=192.168.101.2/24,tag=101,type=veth
                password: supersecret

.. collapse:: Clone an existing LXC container

    .. code-block:: yaml

       my-lxc-container:
            provider: my-proxmox-config
            technology: lxc

            # Required for cloud.bootstrap()
            ssh_host: 192.168.101.2
            ssh_username: root
            ssh_password: supersecret

            clone:
                # For parameters check https://<PROXMOX_URL>/pve-docs/api-viewer/index.html#/nodes/{node}/lxc/clone
                vmid: 123
                newid: 456
                node: proxmox-node1

                description: cloned vm

.. collapse:: Create a new QEMU VM

    .. code-block:: yaml

        my-qemu-vm:
            provider: my-proxmox-config
            technology: qemu

            # Required for cloud.bootstrap()
            ssh_host: 192.168.101.2
            ssh_username: root
            ssh_password: supersecret

            create:
                # For parameters check https://<PROXMOX_URL>/pve-docs/api-viewer/index.html#/nodes/{node}/qemu
                vmid: 123
                node: proxmox-node1

                ipconfig0: ip=192.168.101.2/24,gw=192.168.101.1

.. collapse:: Clone an existing QEMU VM:

    .. code-block:: yaml

        my-qemu-vm:
            provider: my-proxmox-config
            technology: qemu

            # Required for cloud.bootstrap()
            ssh_host: 192.168.101.2
            ssh_username: root
            ssh_password: supersecret

            clone:
                # For parameters check https://<PROXMOX_URL>/pve-docs/api-viewer/index.html#/nodes/{node}/qemu/clone
                vmid: 123
                newid: 456
                node: proxmox-node1

                description: cloned vm

:maintainer: Bernhard Gally <github.com/I3urny>
:depends: requests >= 2.2.1
"""
import logging
import time
from ipaddress import ip_interface

import salt.config as config
import salt.utils.cloud
import salt.utils.json
from salt.exceptions import SaltCloudExecutionTimeout
from salt.exceptions import SaltCloudNotFound
from salt.exceptions import SaltCloudSystemExit

try:
    import requests

    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

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
    return config.is_provider_configured(
        __opts__,
        _get_active_provider_name() or __virtualname__,
        ("url", "user", "token"),
    )


def get_dependencies():
    """
    Warn if dependencies aren't met.
    """
    deps = {"requests": HAS_REQUESTS}
    return config.check_driver_dependencies(__virtualname__, deps)


def create(vm_):
    """
    Create a single Proxmox VM.
    """
    __utils__["cloud.fire_event"](
        "event",
        "starting create",
        "salt/cloud/{}/creating".format(vm_["name"]),
        args=__utils__["cloud.filter_event"](
            "creating", vm_, ["name", "profile", "provider", "driver"]
        ),
        sock_dir=__opts__["sock_dir"],
        transport=__opts__["transport"],
    )

    type = vm_.get("technology")

    clone_options = vm_.get("clone")
    should_clone = True if clone_options else False

    if should_clone:
        clone(call="function", kwargs=clone_options)
    else:
        _query("POST", f"nodes/{vm_['create']['node']}/{type}", vm_["create"])

    start(call="action", name=vm_["name"])

    # cloud.bootstrap expects the ssh_password to be set in vm_["password"]
    vm_["password"] = vm_.get("ssh_password")
    ret = __utils__["cloud.bootstrap"](vm_, __opts__)

    ret.update(show_instance(call="action", name=vm_["name"]))

    __utils__["cloud.fire_event"](
        "event",
        "created instance",
        f"salt/cloud/{vm_['name']}/created",
        args=__utils__["cloud.filter_event"](
            "created", vm_, ["name", "profile", "provider", "driver"]
        ),
        sock_dir=__opts__["sock_dir"],
        transport=__opts__["transport"],
    )

    return ret


def clone(call=None, kwargs=None):
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

    if not isinstance(kwargs, dict):
        kwargs = {}

    vmid = kwargs.get("vmid")

    vm = _get_vm_by_id(vmid)

    _query("POST", f"nodes/{vm['node']}/{vm['type']}/{vmid}/clone", kwargs)

    # TODO: optionally wait for it to exist
    # timeout = 300
    # start_time = time.time()
    # while time.time() < start_time + timeout:
    #     try:
    #         _get_vm_by_id(newid)
    #     except SaltCloudNotFound:
    #         log.debug("blabla")

    # raise SaltCloudExecutionTimeout("Timeout to wait for VM cloning reached")


def reconfigure(call=None, name=None, kwargs=None):
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
        raise SaltCloudSystemExit(
            "The reconfigure action must be called with -d, --destroy, -a or --action."
        )

    vm = _get_vm_by_name(name)

    _query("PUT", f"nodes/{vm['node']}/{vm['type']}/{vm['vmid']}/config", kwargs)

    return {
        "success": True,
        "action": "reconfigure",
    }


def destroy(call=None, name=None, kwargs=None):
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

    __utils__["cloud.fire_event"](
        "event",
        "destroying instance",
        f"salt/cloud/{name}/destroying",
        args={"name": name},
        sock_dir=__opts__["sock_dir"],
        transport=__opts__["transport"],
    )

    vm = _get_vm_by_name(name)

    _query("DELETE", f"nodes/{vm['node']}/{vm['type']}/{vm['vmid']}", kwargs)

    __utils__["cloud.fire_event"](
        "event",
        "destroyed instance",
        f"salt/cloud/{name}/destroyed",
        args={"name": name},
        sock_dir=__opts__["sock_dir"],
        transport=__opts__["transport"],
    )


def avail_locations(call=None):
    """
    Return available Proxmox datacenter locations

    CLI Example:

    .. code-block:: bash

        salt-cloud --list-locations my-proxmox-config
    """
    if call == "action":
        raise SaltCloudSystemExit(
            "The avail_locations function must be called with "
            "-f or --function, or with the --list-locations option"
        )

    locations = _query("GET", "nodes")

    ret = {}
    for location in locations:
        name = location["node"]
        if location.get("status") == "online":
            ret[name] = location
        else:
            log.warning("Ignoring Proxmox node '%s' because it is not online.", name)

    return ret


def avail_images(call=None, kwargs=None):
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

    if not isinstance(kwargs, dict):
        kwargs = {}

    storage = kwargs.get("storage", "local")

    ret = {}
    for location in avail_locations():
        ret[location] = {}
        for item in _query("GET", f"nodes/{location}/storage/{storage}/content"):
            ret[location][item["volid"]] = item
            # TODO: filter to actual images. what is an imagetype? images, vztmpl, iso

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

    vms = _query("GET", "cluster/resources", data={"type": "vm"})

    ret = {}
    for vm in vms:
        name = vm["name"]

        ret[name] = {}
        ret[name]["id"] = str(vm["vmid"])
        ret[name]["image"] = ""  # proxmox does not carry that information
        ret[name]["size"] = ""  # proxmox does not have VM sizes like AWS (e.g: t2-small)
        ret[name]["state"] = str(vm["status"])

        config = _query("GET", f"nodes/{vm['node']}/{vm['type']}/{vm['vmid']}/config")
        private_ips, public_ips = _parse_ips(config, vm["type"])

        ret[name]["private_ips"] = private_ips
        ret[name]["public_ips"] = public_ips

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

    vms = _query("GET", "cluster/resources", data={"type": "vm"})

    ret = {}
    for vm in vms:
        name = vm["name"]
        config = _query("GET", f"nodes/{vm['node']}/{vm['type']}/{vm['vmid']}/config")

        ret[name] = vm
        ret[name]["config"] = config

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


def show_instance(call=None, name=None):
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


def start(call=None, name=None, kwargs=None):
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

    _wait_for_vm_status(name, "running")

    return {
        "success": True,
        "state": "running",
        "action": "start",
    }


def stop(call=None, name=None, kwargs=None):
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

    _wait_for_vm_status(name, "stopped")

    return {
        "success": True,
        "state": "stopped",
        "action": "stop",
    }


def shutdown(call=None, name=None, kwargs=None):
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

    _wait_for_vm_status(name, "stopped")

    return {
        "success": True,
        "state": "stopped",
        "action": "shutdown",
    }


def _query(method, path, data=None):
    """
    Query the Proxmox API
    """
    base_url = _get_url()
    api_token = _get_api_token()

    url = f"{base_url}/api2/json/{path}"

    headers = {
        "Accept": "application/json",
        "User-Agent": "salt-cloud-proxmox",
        "Authorization": f"PVEAPIToken={api_token}",
    }

    try:
        response = None

        if method == "GET":
            response = requests.get(
                url=url,
                headers=headers,
                params=data,
            )
        else:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                data=data,
            )

        response.raise_for_status()
        returned_data = response.json()
        return returned_data.get("data")

    except requests.exceptions.RequestException as err:
        log.error("Error in query to %s:\n%s", url, response.text)
        raise SaltCloudSystemExit(err)


def _get_url():
    """
    Returns the configured Proxmox URL
    """
    return config.get_cloud_config_value(
        "url", get_configured_provider(), __opts__, search_global=False
    )


def _get_api_token():
    """
    Returns the API token for the Proxmox API
    """
    username = config.get_cloud_config_value(
        "user", get_configured_provider(), __opts__, search_global=False
    )
    token = config.get_cloud_config_value(
        "token", get_configured_provider(), __opts__, search_global=False
    )
    return f"{username}!{token}"


def _get_vm_by_name(name):
    """
    Return VM identified by name

    name
        The name of the VM. Required.

    .. note:

        This function will return the first occurrence of a VM matching the given name.
    """
    vms = _query("GET", "cluster/resources", {"type": "vm"})
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
    vms = _query("GET", "cluster/resources", {"type": "vm"})
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

    _query("POST", f"nodes/{vm['node']}/{vm['type']}/{vm['vmid']}/status/{status}", kwargs)


def _wait_for_vm_status(name, status, timeout=300, interval=0.2):
    """
    Wait for the VM to reach a given status

    name
        The name of the VM. Required.

    status
        The expected status of the VM. Required.

    timeout
        The timeout in seconds on how long to wait for the task. Default: 300 seconds

    interval
        The interval in seconds at which the API should be queried for updates. Default: 0.2 seconds
    """
    vm = _get_vm_by_name(name)

    start_time = time.time()
    while time.time() < start_time + timeout:
        response = _query("GET", f"nodes/{vm['node']}/{vm['type']}/{vm['vmid']}/status/current")

        if response["status"] == status:
            return True

        time.sleep(interval)

    raise SaltCloudExecutionTimeout("Timeout to wait for VM status reached.")


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
