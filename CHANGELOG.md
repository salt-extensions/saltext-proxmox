The changelog format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

This project uses [Semantic Versioning](https://semver.org/) - MAJOR.MINOR.PATCH

# Changelog

# Saltext.Proxmox 1.1.0 (2023-10-11)

### Removed

- removed superfluous code from `_get_properties()` and its callees (#8)
- removed dead code from repository (#20)
- removed OpenVZ code paths (#27)

### Changed

- Replaced IPy dependency with built-in module ipaddress (#22)

### Fixed

- fixed location parameter for `avail_images()` (#25)


# Saltext.Proxmox 1.0.0 (2023-04-26)

### Added

- Initial version of Proxmox Cloud Modules Extension for Salt. This release
  tracks the functionality in the core Salt code base as of version 3006.0.
