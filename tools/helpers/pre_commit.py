import re

from . import prompt
from .cmd import ProcessExecutionError
from .cmd import git
from .cmd import local
from .git import list_untracked

PRE_COMMIT_TEST_REGEX = re.compile(
    r"^(?P<test>[^\n]+?)\.{4,}.*(?P<resolution>Failed|Passed|Skipped)$"
)
NON_IDEMPOTENT_HOOKS = (
    "trim trailing whitespace",
    "mixed line ending",
    "fix end of files",
    "Remove Python Import Header Comments",
    "Check rST doc files exist for modules/states",
    "Salt extensions docstrings auto-fixes",
    "Rewrite the test suite",
    "Rewrite Code to be Py3.",
    "isort",
    "black",
    "blacken-docs",
)


def parse_pre_commit(data):
    """
    Parse pre-commit output into a list of passing hooks and a mapping of
    failing hooks to their output.
    """
    passing = []
    failing = {}
    cur = None
    for line in data.splitlines():
        if match := PRE_COMMIT_TEST_REGEX.match(line):
            cur = None
            if match.group("resolution") != "Failed":
                passing.append(match.group("test"))
                continue
            cur = match.group("test")
            failing[cur] = []
            continue
        try:
            failing[cur].append(line)
        except KeyError:
            # in case the parsing logic fails, let's not crash everything
            continue
    return passing, {test: "\n".join(output).strip() for test, output in failing.items()}


def check_pre_commit_rerun(data):
    """
    Check if we can expect failing hooks to turn green during a rerun.
    """
    _, failing = parse_pre_commit(data)
    for hook in failing:
        if hook.startswith(NON_IDEMPOTENT_HOOKS):
            return True
    return False


def run_pre_commit(venv, retries=2):
    """
    Run pre-commit in a loop until it passes, there is no chance of
    autoformatting to make it pass or a maximum number of runs is reached.

    Usually, a maximum of two runs is necessary (if a hook reformats the
    output of another later one again).
    """
    new_files = set()

    def _run_pre_commit_loop(retries_left):
        untracked_files = set(map(str, list_untracked()))
        nonlocal new_files
        new_files = new_files.union(untracked_files)
        # Ensure pre-commit runs on all paths.
        # We don't want to git add . because this removes merge conflicts
        git("add", "--intent-to-add", *untracked_files)
        with local.venv(venv):
            try:
                local["python"]("-m", "pre_commit", "run", "--all-files")
            except ProcessExecutionError as err:
                if retries_left > 0 and check_pre_commit_rerun(err.stdout):
                    return _run_pre_commit_loop(retries_left - 1)
                raise

    prompt.status(
        "Running pre-commit hooks against all files. This can take a minute, please be patient"
    )

    try:
        _run_pre_commit_loop(retries)
        return True
    except ProcessExecutionError as err:
        _, failing = parse_pre_commit(err.stdout)
        if failing:
            msg = f"Please fix all ({len(failing)}) failing hooks"
        else:
            msg = f"Output: {err.stderr or err.stdout}"
        prompt.warn(f"Pre-commit is failing. {msg}")
        for i, failing_hook in enumerate(failing):
            prompt.warn(f"✗ Failing hook ({i + 1}): {failing_hook}", failing[failing_hook])
    finally:
        # Undo git add --intent-to-add to allow RenovateBot to detect new files correctly
        git("restore", "--staged", *new_files)
    return False
