import sys

from helpers import prompt
from helpers.copier import finish_task
from helpers.git import ensure_git
from helpers.venv import ensure_project_venv

if __name__ == "__main__":
    args = sys.argv[1:]
    try:
        prompt.ensure_utf8()
        ensure_git()
        venv = ensure_project_venv(install_extras="--extras" in args)
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
    if "--print-venv" in args:
        print(venv)
    finish_task("Successfully initialized environment", True)
