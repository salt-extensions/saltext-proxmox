# Installation

Generally, extensions need to be installed into the same Python
environment Salt uses.

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

Salt itself is expected to be provided by the environment. If it
should be pip-managed as well, request the `salt` extra:

```bash
pip install 'saltext-proxmox[salt]'
```
:::

:::{hint}
Saltexts are not distributed automatically via the fileserver like
custom modules, they need to be installed on each node you want them
to be available on.
:::
