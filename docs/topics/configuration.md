# Configuration

## Provider
Set up the cloud configuration at `/etc/salt/cloud.providers` or `/etc/salt/cloud.providers.d/proxmox.conf`:

```yaml
my-proxmox-config:
  # Required parameters
  host: hypervisor.domain.tld:8006
  user: myuser@pam  # or myuser@pve
  token_name: myapitoken_name
  token_value: myapitoken_value
  driver: proxmox
```

## Profile examples
### Create a new LXC container
```yaml
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

    hostname: my-lxc-container
    net0: name=eth0,bridge=vmbr0,firewall=1,gw=192.168.101.1,ip=192.168.101.2/24,tag=101,type=veth
    password: supersecret
```

### Clone an existing LXC container
```yaml
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

    hostname: my-lxc-container
    description: cloned vm
```

### Create a new QEMU VM
```yaml
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

    name: my-qemu-vm
    ipconfig0: ip=192.168.101.2/24,gw=192.168.101.1
```

### Clone an existing QEMU VM
```yaml
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

    name: my-qemu-vm
    description: cloned vm
```
