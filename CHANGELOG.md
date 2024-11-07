The changelog format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

This project uses [Semantic Versioning](https://semver.org/) - MAJOR.MINOR.PATCH

# Changelog

## 2.0.1 (2024-11-07)


### Fixed

- Fixed profile error: name '__opts__' is not defined [#45](https://github.com/salt-extensions/saltext-proxmox/issues/45)


## v2.0.0 (2024-08-08)


### Changed

- changed parameter structure for profiles [#9](https://github.com/salt-extensions/saltext-proxmox/issues/9)
- removed custom parameters for VMs (ip_address). instead, VM parameters are forwarded directly to proxmox api [#21](https://github.com/salt-extensions/saltext-proxmox/issues/21)
- removed arbitrary limit for indexed parameters. instead, VM parameters are forwarded directly to proxmox api [#29](https://github.com/salt-extensions/saltext-proxmox/issues/29)


### Added

- VM parameters are forwarded directly to proxmox api. the documentation references the proxmox api docs to look up possible parameters [#12](https://github.com/salt-extensions/saltext-proxmox/issues/12)


## v1.1.0 (2023-10-11)

### Removed

- removed superfluous code from `_get_properties()` and its callees (#8)
- removed dead code from repository (#20)
- removed OpenVZ code paths (#27)

### Changed

- Replaced IPy dependency with built-in module ipaddress (#22)

### Fixed

- fixed location parameter for `avail_images()` (#25)


## v1.0.0 (2023-04-26)

### Added

- Initial version of Proxmox Cloud Modules Extension for Salt. This release
  tracks the functionality in the core Salt code base as of version 3006.0.
