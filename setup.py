# pylint: disable=missing-module-docstring
from pathlib import Path

import setuptools

version_path = Path(__file__).parent / "src" / "saltext" / "azurerm" / "version.py"

with version_path.open() as f:
    for line in f:
        if line.startswith("__version__"):
            # We only want the bare string pls
            version = line.partition("=")[-1].strip().strip('"').strip("'")
            break
    else:
        version = "0.0.1dev1"  # pylint: disable=invalid-name


if __name__ == "__main__":
    setuptools.setup(use_scm_version=True, version=version)
