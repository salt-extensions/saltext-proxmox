import argparse

from helpers import prompt
from helpers.copier import finish_task
from helpers.git import ensure_git
from helpers.venv import ensure_project_venv

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Initialize or update the project development environment"
    )
    parser.add_argument(
        "--no-extras",
        action="store_true",
        help="Do not install optional development tools into the venv (dev_extra group)",
    )
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help=(
            "Only (re)install the project if the venv was freshly created "
            "or pyproject.toml changed since the last install. "
            "Speeds up repeated invocations, e.g. on each shell entry via direnv"
        ),
    )
    parser.add_argument(
        "--print-venv",
        action="store_true",
        help="Print the path of the virtual environment to stdout (used by .envrc)",
    )
    args = parser.parse_args()
    init_or_update = True
    try:
        prompt.ensure_utf8()
        ensure_git()
        venv, init_or_update = ensure_project_venv(
            reinstall="auto" if args.skip_install else True,
            no_extras=args.no_extras,
        )
    except Exception as err:  # pylint: disable=broad-except
        finish_task(
            f"Failed initializing environment: {err}",
            False,
            True,
            extra=(
                "No worries, just follow the manual steps documented here: "
                "https://salt-extensions.github.io/salt-extension-copier/topics/creation.html#first-steps"
            ),
        )
    if args.print_venv:
        print(venv)
    if init_or_update:
        finish_task("Successfully initialized environment", True)
    finish_task("venv OK", True, tight=True)
