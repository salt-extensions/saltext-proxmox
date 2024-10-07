import logging
import shutil

import pytest
from saltfactories.utils.functional import Loaders

log = logging.getLogger(__name__)


@pytest.fixture(scope="package")
def minion_id():  # pragma: no cover
    return "func-tests-minion-opts"


@pytest.fixture(scope="module")
def state_tree(tmp_path_factory):  # pragma: no cover
    state_tree_path = tmp_path_factory.mktemp("state-tree-base")
    try:
        yield state_tree_path
    finally:
        shutil.rmtree(str(state_tree_path), ignore_errors=True)


@pytest.fixture(scope="module")
def state_tree_prod(tmp_path_factory):  # pragma: no cover
    state_tree_path = tmp_path_factory.mktemp("state-tree-prod")
    try:
        yield state_tree_path
    finally:
        shutil.rmtree(str(state_tree_path), ignore_errors=True)


@pytest.fixture(scope="module")
def minion_config_defaults():  # pragma: no cover
    """
    Functional test modules can provide this fixture to tweak the default
    configuration dictionary passed to the minion factory
    """
    return {}


@pytest.fixture(scope="module")
def minion_config_overrides():  # pragma: no cover
    """
    Functional test modules can provide this fixture to tweak the configuration
    overrides dictionary passed to the minion factory
    """
    return {}


@pytest.fixture(scope="module")
def minion_opts(
    salt_factories,
    minion_id,
    state_tree,
    state_tree_prod,
    minion_config_defaults,
    minion_config_overrides,
):  # pragma: no cover
    minion_config_overrides.update(
        {
            "file_client": "local",
            "file_roots": {
                "base": [
                    str(state_tree),
                ],
                "prod": [
                    str(state_tree_prod),
                ],
            },
        }
    )
    factory = salt_factories.salt_minion_daemon(
        minion_id,
        defaults=minion_config_defaults or None,
        overrides=minion_config_overrides,
    )
    return factory.config.copy()


@pytest.fixture(scope="module")
def master_config_defaults():  # pragma: no cover
    """
    Functional test modules can provide this fixture to tweak the default
    configuration dictionary passed to the master factory
    """
    return {}


@pytest.fixture(scope="module")
def master_config_overrides():  # pragma: no cover
    """
    Functional test modules can provide this fixture to tweak the configuration
    overrides dictionary passed to the master factory
    """
    return {}


@pytest.fixture(scope="module")
def master_opts(
    salt_factories,
    state_tree,
    state_tree_prod,
    master_config_defaults,
    master_config_overrides,
):  # pragma: no cover
    master_config_overrides.update(
        {
            "file_client": "local",
            "file_roots": {
                "base": [
                    str(state_tree),
                ],
                "prod": [
                    str(state_tree_prod),
                ],
            },
        }
    )
    factory = salt_factories.salt_master_daemon(
        "func-tests-master-opts",
        defaults=master_config_defaults or None,
        overrides=master_config_overrides,
    )
    return factory.config.copy()


@pytest.fixture(scope="module")
def loaders(minion_opts):  # pragma: no cover
    return Loaders(minion_opts, loaded_base_name=f"{__name__}.loaded")


@pytest.fixture(autouse=True)
def reset_loaders_state(loaders):  # pragma: no cover
    try:
        # Run the tests
        yield
    finally:
        # Reset the loaders state
        loaders.reset_state()


@pytest.fixture(scope="module")
def modules(loaders):  # pragma: no cover
    return loaders.modules


@pytest.fixture(scope="module")
def states(loaders):  # pragma: no cover
    return loaders.states
