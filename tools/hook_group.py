"""
Print the IDs/aliases of all pre-commit hooks in the given prek group.

Allows pre-commit, which does not support prek's hook groups, to be
used as a fallback for running them, e.g. in the Makefile's ``fmt``
and ``lint`` targets. pre-commit guarantees the availability of
``yaml`` since it depends on it.
"""

import sys

import yaml


def list_group(group):
    """Yield the IDs/aliases of all hooks in the given group."""
    with open(".pre-commit-config.yaml", encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file)
    for repo in config["repos"]:
        for hook in repo["hooks"]:
            if group in hook.get("groups", ()):
                yield hook.get("alias", hook["id"])


if __name__ == "__main__":
    print("\n".join(list_group(sys.argv[1])))
