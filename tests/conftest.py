import logging
import os

import pytest
from saltfactories.utils import random_string

from saltext.proxmox import PACKAGE_ROOT

# Reset the root logger to its default level(because salt changed it)
logging.root.setLevel(logging.WARNING)


# This swallows all logging to stdout.
# To show select logs, set --log-cli-level=<level>
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)
    handler.close()


@pytest.fixture(scope="session")
def salt_factories_config():
    """
    Return a dictionary with the keyword arguments for FactoriesManager
    """
    return {
        "code_dir": str(PACKAGE_ROOT),
        "inject_sitecustomize": "COVERAGE_PROCESS_START" in os.environ,
        "start_timeout": 120 if os.environ.get("CI") else 60,
    }


@pytest.fixture(scope="package")
def master_config():
    """
    Salt master configuration overrides for integration tests.
    """
    return {}


@pytest.fixture(scope="package")
def master(salt_factories, master_config):
    return salt_factories.salt_master_daemon(random_string("master-"), overrides=master_config)


@pytest.fixture(scope="package")
def minion_config():
    """
    Salt minion configuration overrides for integration tests.
    """
    return {}


@pytest.fixture(scope="package")
def minion(master, minion_config):
    return master.salt_minion_daemon(random_string("minion-"), overrides=minion_config)
