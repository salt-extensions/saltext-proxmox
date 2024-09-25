import sys
from functools import wraps
from pathlib import Path

from . import prompt

try:
    # In case we have it, use it.
    # It's always installed in the Copier environment, so if you ensure you
    # call this via ``copier_python``, this will work.
    import yaml
except ImportError:
    yaml = None


COPIER_ANSWERS = Path(".copier-answers.yml").resolve()


def _needs_answers(func):
    @wraps(func)
    def _wrapper(*args, **kwargs):
        if not COPIER_ANSWERS.exists():
            raise RuntimeError(f"Missing answers file at {COPIER_ANSWERS}")
        return func(*args, **kwargs)

    return _wrapper


@_needs_answers
def load_answers():
    """
    Load the complete answers file. Depends on PyYAML.
    """
    if not yaml:
        raise RuntimeError("Missing pyyaml in environment")
    with open(COPIER_ANSWERS) as f:
        return yaml.safe_load(f)


@_needs_answers
def discover_project_name():
    """
    Specifically discover project name. No dependency.
    """
    for line in COPIER_ANSWERS.read_text().splitlines():
        if line.startswith("project_name"):
            return line.split(":", maxsplit=1)[1].strip()
    raise RuntimeError("Failed discovering project name")


def finish_task(msg, success, err_exit=False, extra=None):
    """
    Print final conclusion of task (migration) run in Copier.

    We usually want to exit with 0, even when something fails,
    because a failing task/migration should not crash Copier.
    """
    print("\n", file=sys.stderr)
    if success:
        prompt.pprint(f"\n    ✓ {msg}", bold=True, bg=prompt.DARKGREEN, stream=sys.stderr)
    elif success is None:
        prompt.pprint(
            f"\n    ✓ {msg}", bold=True, fg=prompt.YELLOW, bg=prompt.DARKGREEN, stream=sys.stderr
        )
        success = True
    else:
        prompt.warn(f"    ✗ {msg}", extra)
    raise SystemExit(int(not success and err_exit))
