import hashlib
import os
from pathlib import Path
from shutil import rmtree

from . import prompt
from .cmd import CommandNotFound
from .cmd import local
from .copier import discover_project_name
from .copier import discover_venv_python
from .pre_commit import pre_commit_cmd
from .pre_commit import quiet_installed_hook
from .pre_commit import quiet_venv_pre_commit
from .pre_commit import upgrade_hook_to_prek

# Fallback when the `venv_python` answer is unavailable.
# Should follow the version used for relenv packages, see
# https://github.com/saltstack/salt/blob/master/cicd/shared-gh-workflows-context.yml
RECOMMENDED_PYVER = "3.14"
# For discovery of existing virtual environment, descending priority.
VENV_DIRS = (
    ".venv",
    "venv",
    ".env",
    "env",
)
# Records the install-state hash of the last project install into the venv,
# allowing `reinstall="auto"` to skip redundant reinstalls.
INSTALL_HASH_FILE = ".install-hash"


def state_hash(*parts, project_root="."):
    """
    Hash of pyproject.toml plus arbitrary stringified parts that
    determine an environment's installed requirements. Used to skip
    redundant reinstalls into existing venvs (dev and nox session ones).
    """
    try:
        pyproject = (Path(project_root) / "pyproject.toml").read_bytes()
    except OSError:
        return None
    digest = hashlib.sha256(pyproject)
    digest.update(repr(parts).encode())
    return digest.hexdigest()


def install_state_hash(project_root, groups, project):
    """
    Hash of the inputs that determine the venv's installed project
    requirements: pyproject.toml plus the requested dependency
    groups/extras.
    """
    return state_hash(tuple(groups), project, project_root=project_root)


def stored_install_hash(venv):
    """
    The install-state hash recorded during the last project install,
    if any.
    """
    try:
        return (venv / INSTALL_HASH_FILE).read_text().strip()
    except OSError:
        return None


def discover_uv():
    try:
        return local["uv"]
    except CommandNotFound:
        pass


def system_site_packages_requested():
    """
    Whether the development venv should inherit system-wide packages,
    e.g. for OS-specific extensions whose dependencies are only
    available as system packages.
    """
    return os.environ.get("VENV_SYSTEM_SITE_PACKAGES", "0") == "1"


def is_venv(path):
    if (venv_path := Path(path)).is_dir() and (venv_path / "pyvenv.cfg").exists():
        return venv_path
    return False


def discover_venv(project_root="."):
    base = Path(project_root).resolve()
    for name in VENV_DIRS:
        if found := is_venv(base / name):
            return found
    raise RuntimeError(f"No venv found in {base}")


def venv_pyver(venv):
    for line in (venv / "pyvenv.cfg").read_text().splitlines():
        if line.startswith(("version =", "version_info =")):
            pyver = line.split(" = ")[1].split(".")
            return f"{pyver[0]}.{pyver[1]}"


def venv_system_site_packages(venv):
    for line in (venv / "pyvenv.cfg").read_text().splitlines():
        if line.startswith("include-system-site-packages"):
            return line.split("=")[1].strip().lower() == "true"
    return False


def get_venv_pyver():
    """
    Return the Python version the project venv should use,
    as configured in the answers file (`venv_python`).
    Can be overridden locally by setting $VENV_PYTHON.
    """
    if override := os.environ.get("VENV_PYTHON"):
        return override
    try:
        return discover_venv_python() or RECOMMENDED_PYVER
    except RuntimeError:
        return RECOMMENDED_PYVER


def create_venv(project_root=".", directory=None, pyver=None, system_site_packages=None):
    if system_site_packages is None:
        system_site_packages = system_site_packages_requested()
    pyver = pyver or get_venv_pyver()
    base = Path(project_root).resolve()
    venv = (base / (directory or VENV_DIRS[0])).resolve()
    if is_venv(venv):
        raise RuntimeError(f"Venv at {venv} already exists")
    prompt.status(f"Creating virtual environment at {venv}")
    # When inheriting system-wide packages, the venv must be based on the
    # system Python (uv-managed interpreters don't carry system packages).
    uv = None if system_site_packages else discover_uv()
    if uv is not None:
        prompt.status("Found `uv`. Creating venv")
        uv(
            "venv",
            # Install pip/setuptools/wheel for compatibility
            "--seed",
            "--python",
            pyver,
            f"--prompt=saltext-{discover_project_name()}",
            directory or VENV_DIRS[0],
        )
    else:
        if system_site_packages:
            prompt.status("System-site-packages venv requested. Using `venv`")
        else:
            prompt.status("Did not find `uv`. Falling back to `venv`")
        venv_params = ["--system-site-packages"] if system_site_packages else []
        try:
            python = local[f"python{pyver}"]
        except CommandNotFound as err:
            try:
                python = local["python3"]
            except CommandNotFound:
                python = local["python"]  # Windows needs this without uv
            version = python("--version").split(" ")[1]
            if not version.startswith(pyver):
                raise RuntimeError(
                    f"No `python{pyver}` executable found in $PATH, exiting"
                ) from err
        python(
            "-m",
            "venv",
            directory or VENV_DIRS[0],
            f"--prompt=saltext-{discover_project_name()}",
            *venv_params,
        )
    return venv


def _discover_matching_venv(project_root, pyver, system_site_packages):
    """
    Return an existing project venv matching the requested configuration.
    A venv with mismatching Python version or system-site-packages
    setting is removed. Returns None if a venv needs to be created.
    """
    try:
        venv = discover_venv(project_root)
    except RuntimeError:
        return None

    existing_pyver = venv_pyver(venv)
    if existing_pyver != pyver:
        prompt.status(
            f"Existing venv has Python {existing_pyver}, but configured is {pyver}. Recreating."
        )
        rmtree(venv)
        return None

    if venv_system_site_packages(venv) != system_site_packages:
        if system_site_packages:
            msg = (
                "Existing venv does not inherit system site packages, "
                "but $VENV_SYSTEM_SITE_PACKAGES is set. Recreating."
            )
        else:
            msg = (
                "Existing venv inherits system site packages, "
                "but $VENV_SYSTEM_SITE_PACKAGES is unset. Recreating."
            )
        prompt.status(msg)
        rmtree(venv)
        return None

    return venv


def _install_pending(venv, state_hash):
    """
    Whether the venv's last recorded project install is out of sync
    with the current install state (``reinstall="auto"``).
    """
    stored = stored_install_hash(venv)
    if stored is None and state_hash:
        # Venvs created before this marker existed don't carry it.
        # Assume they are in sync (the previous auto semantics)
        # and adopt the current state.
        (venv / INSTALL_HASH_FILE).write_text(state_hash)
        stored = state_hash
    return stored != state_hash


def _install_project(groups, project, system_site_packages):
    """
    Install the project into the active venv, preferring uv where
    appropriate. Must be called within a ``local.venv`` context.
    """
    # uv pip install does not consider packages inherited via
    # --system-site-packages (astral-sh/uv#4466), so avoid it for such venvs.
    uv = None
    if not system_site_packages:
        uv = discover_uv()
        if uv is None:
            try:
                # We install uv into the virtualenv, so it might be available now.
                # It speeds up this step a lot.
                uv = local["uv"]
            except CommandNotFound:
                pass
    if uv is not None:
        uv("pip", "install", *groups, "-e", project)
    else:
        local["python"]("-m", "pip", "install", *groups, "-e", project)


def ensure_project_venv(project_root=".", reinstall=True, no_extras=False, pyver=None):
    """
    Ensure the project venv exists and uses the configured Python version.

    ``reinstall`` semantics:
      * ``True``: always (re)install the project into the venv
      * ``"auto"``: only install if the venv was freshly created or
        pyproject.toml changed since the last install
      * ``False``: never install, just ensure the venv exists
    """
    pyver = pyver or get_venv_pyver()
    system_site_packages = system_site_packages_requested()
    venv = _discover_matching_venv(project_root, pyver, system_site_packages)
    exists = venv is not None
    if not exists:
        venv = create_venv(project_root, pyver=pyver, system_site_packages=system_site_packages)
    groups = []
    for group in (["dev_required", "tests", "docs"] if no_extras else ["dev_all"]):
        groups.extend(("--group", group))
    # Salt is only an extra. When inheriting system site packages, it is
    # expected to be provided by the system - resolving the extra would
    # make pip pull Salt's declared dependencies from PyPI, replacing
    # the system-provided versions (cf. noxfile._install_requirements).
    project = "." if system_site_packages else ".[salt]"
    state_hash = install_state_hash(project_root, groups, project)
    if reinstall == "auto":
        reinstall = not exists or _install_pending(venv, state_hash)
    if not reinstall:
        upgrade_hook_to_prek(venv, project_root)
        quiet_installed_hook(project_root)
        quiet_venv_pre_commit(venv)
        return venv, not exists
    # Message only here to keep happy path output minimal
    prompt.status(f"Found existing virtual environment at {venv}")
    prompt.status(("Reinstalling" if exists else "Installing") + " project and dependencies")
    with local.venv(venv):
        _install_project(groups, project, system_site_packages)
        if state_hash:
            (venv / INSTALL_HASH_FILE).write_text(state_hash)
        if not exists or not (Path(project_root) / ".git" / "hooks" / "pre-commit").exists():
            prompt.status("Installing pre-commit hooks")
            install_args = ["install"]
            # --install-hooks prepares environments for all hooks, disregarding SKIP,
            # which can fail for skipped ones on unsupported platforms. Hook runs
            # install missing environments on demand, honoring SKIP.
            if not os.environ.get("SKIP"):
                install_args.append("--install-hooks")
            pre_commit_cmd()(*install_args)
    upgrade_hook_to_prek(venv, project_root)
    quiet_installed_hook(project_root)
    quiet_venv_pre_commit(venv)
    return venv, True
