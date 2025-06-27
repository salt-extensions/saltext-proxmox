import tempfile
from pathlib import Path

from . import prompt
from .cmd import CommandNotFound
from .cmd import local
from .copier import discover_project_name

# Should follow the version used for relenv packages, see
# https://github.com/saltstack/salt/blob/master/cicd/shared-gh-workflows-context.yml
RECOMMENDED_PYVER = "3.10"
# For discovery of existing virtual environment, descending priority.
VENV_DIRS = (
    ".venv",
    "venv",
    ".env",
    "env",
)


try:
    uv = local["uv"]
except CommandNotFound:
    uv = None


def is_venv(path):
    if (venv_path := Path(path)).is_dir and (venv_path / "pyvenv.cfg").exists():
        return venv_path
    return False


def discover_venv(project_root="."):
    base = Path(project_root).resolve()
    for name in VENV_DIRS:
        if found := is_venv(base / name):
            return found
    raise RuntimeError(f"No venv found in {base}")


def create_venv(project_root=".", directory=None):
    base = Path(project_root).resolve()
    venv = (base / (directory or VENV_DIRS[0])).resolve()
    if is_venv(venv):
        raise RuntimeError(f"Venv at {venv} already exists")
    prompt.status(f"Creating virtual environment at {venv}")
    if uv is not None:
        prompt.status("Found `uv`. Creating venv")
        uv(
            "venv",
            # Install pip/setuptools/wheel for compatibility
            "--seed",
            "--python",
            RECOMMENDED_PYVER,
            f"--prompt=saltext-{discover_project_name()}",
        )
    else:
        prompt.status("Did not find `uv`. Falling back to `venv`")
        try:
            python = local[f"python{RECOMMENDED_PYVER}"]
        except CommandNotFound:
            python = local["python3"]
            version = python("--version").split(" ")[1]
            if not version.startswith(RECOMMENDED_PYVER):
                raise RuntimeError(
                    f"No `python{RECOMMENDED_PYVER}` executable found in $PATH, exiting"
                )
        python("-m", "venv", VENV_DIRS[0], f"--prompt=saltext-{discover_project_name()}")
    return venv


def ensure_project_venv(project_root=".", reinstall=True, install_extras=False):
    exists = False
    try:
        venv = discover_venv(project_root)
        prompt.status(f"Found existing virtual environment at {venv}")
        exists = True
    except RuntimeError:
        venv = create_venv(project_root)
    if not reinstall:
        return venv
    extras = ["dev", "tests", "docs"]
    if install_extras:
        extras.append("dev_extra")
    prompt.status(("Reinstalling" if exists else "Installing") + " project and dependencies")
    with local.venv(venv):
        if uv is not None:
            uv("pip", "install", "-e", f".[{','.join(extras)}]")
        else:
            try:
                # We install uv into the virtualenv, so it might be available now.
                # It speeds up this step a lot.
                local["uv"]("pip", "install", "-e", f".[{','.join(extras)}]")
            except CommandNotFound:
                # Salt does not build correctly with setuptools >= 75.6.0.
                # uv reads this constraint from pyproject.toml, but pip needs this workaround.
                with tempfile.NamedTemporaryFile(delete=False) as constraints_file:
                    setuptools_constraint = "setuptools<75.6.0"
                    constraints_file.write(setuptools_constraint.encode())
                try:
                    with local.env(PIP_CONSTRAINT=constraints_file.name):
                        local["python"]("-m", "pip", "install", "-e", f".[{','.join(extras)}]")
                finally:
                    Path(constraints_file.name).unlink()
        if not exists or not (Path(project_root) / ".git" / "hooks" / "pre-commit").exists():
            prompt.status("Installing pre-commit hooks")
            local["python"]("-m", "pre_commit", "install", "--install-hooks")
    return venv
