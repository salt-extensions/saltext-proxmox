from pathlib import Path

from .cmd import git


def ensure_git():
    """
    Ensure the repository has been initialized.
    """
    if Path(".git").is_dir():
        return
    git("init", "--initial-branch", "main")


def list_untracked():
    """
    List untracked files.
    """
    for path in git("ls-files", "-z", "-o", "--exclude-standard").split("\x00"):
        if path:
            yield path


def list_conflicted():
    """
    List files with merge conflicts.
    """
    for path in git("diff", "-z", "--name-only", "--diff-filter=U", "--relative").split("\x00"):
        if path:
            yield path
