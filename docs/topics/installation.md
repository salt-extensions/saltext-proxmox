# Installation

Generally, extensions need to be installed into the same Python environment Salt uses.

:::{tab} State
```yaml
Install Salt Proxmox extension:
  pip.installed:
    - name: saltext-proxmox
```
:::

:::{tab} Onedir installation
```bash
salt-pip install saltext-proxmox
```
:::

:::{tab} Regular installation
```bash
pip install saltext-proxmox
```
:::

:::{important}
Currently, there is [an issue][issue-second-saltext] where the installation of a Saltext fails silently
if the environment already has another one installed. You can workaround this by
removing all Saltexts and reinstalling them in one transaction.
:::

:::{hint}
Saltexts are not distributed automatically via the fileserver like custom modules, they need to be installed
on each node you want them to be available on.
:::

[issue-second-saltext]: https://github.com/saltstack/salt/issues/65433
