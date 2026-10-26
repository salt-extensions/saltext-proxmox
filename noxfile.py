import datetime
import json
import os
import shutil
import sys
from contextlib import contextmanager
from pathlib import Path

# pylint: disable=import-error
import nox
from nox.command import CommandFailed
from packaging.requirements import InvalidRequirement
from packaging.requirements import Requirement

# pylint: enable=import-error

# Global Path Definitions
REPO_ROOT = Path(__file__).resolve().parent
# Change current directory to REPO_ROOT
os.chdir(str(REPO_ROOT))


@contextmanager
def prepend_path(path):
    try:
        idx = sys.path.index(str(path))
    except ValueError:
        idx = None
    else:
        sys.path.remove(path)
    sys.path.insert(0, str(path))
    try:
        yield
    finally:
        try:
            sys.path.remove(str(path))
        except ValueError:
            pass
        if idx is not None:
            sys.path.insert(idx, str(path))


with prepend_path(REPO_ROOT / "tools"):
    # pylint: disable=import-error
    from helpers.venv import INSTALL_HASH_FILE
    from helpers.venv import get_venv_pyver
    from helpers.venv import state_hash

    # pylint: enable=import-error

# Nox options
#  Reuse existing virtualenvs
nox.options.reuse_existing_virtualenvs = True
#  Don't fail on missing interpreters
nox.options.error_on_missing_interpreters = False
# Support development against system-wide packages, e.g. for OS-specific
# extensions whose dependencies are only available as system packages.
# Note: When toggling this, remove existing session venvs (`make clean`).
SYSTEM_SITE_PACKAGES = os.environ.get("VENV_SYSTEM_SITE_PACKAGES", "0") == "1"
VENV_PARAMS = ("--system-site-packages",) if SYSTEM_SITE_PACKAGES else ()
if SYSTEM_SITE_PACKAGES:
    # uv does not consider packages inherited via --system-site-packages
    # during installs (astral-sh/uv#4466), so don't use it here.
    nox.options.default_venv_backend = "virtualenv"
else:
    # Speed up all sessions by using uv if possible
    nox.options.default_venv_backend = "uv|virtualenv"

# Python versions to test against
PYTHON_VERSIONS = ("3.11", "3.12", "3.13", "3.14")
VENV_PYVER = get_venv_pyver()

# Be verbose when running under a CI context
CI_RUN = (
    os.environ.get("JENKINS_URL") or os.environ.get("CI") or os.environ.get("DRONE") is not None
)
PIP_INSTALL_SILENT = CI_RUN is False
SKIP_REQUIREMENTS_INSTALL = os.environ.get("SKIP_REQUIREMENTS_INSTALL", "0") == "1"
EXTRA_REQUIREMENTS_INSTALL = os.environ.get("EXTRA_REQUIREMENTS_INSTALL")

COVERAGE_REQUIREMENT = os.environ.get("COVERAGE_REQUIREMENT") or "coverage==7.17.0"
SALT_REQUIREMENT = os.environ.get("SALT_REQUIREMENT") or "salt>=3006"
if SALT_REQUIREMENT == "salt==master":
    SALT_REQUIREMENT = "git+https://github.com/saltstack/salt.git@master"
elif SALT_REQUIREMENT.endswith(".x"):
    branch = SALT_REQUIREMENT.split("==", maxsplit=1)[1]
    SALT_REQUIREMENT = f"git+https://github.com/saltstack/salt.git@{branch}"

# Prevent Python from writing bytecode
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

ARTIFACTS_DIR = REPO_ROOT / "artifacts"
# Make sure the artifacts directory exists
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
CUR_TIME = datetime.datetime.now().strftime("%Y%m%d%H%M%S.%f")
RUNTESTS_LOGFILE = ARTIFACTS_DIR / f"runtests-{CUR_TIME}.log"
COVERAGE_REPORT_DB = REPO_ROOT / ".coverage"
COVERAGE_REPORT_PROJECT = ARTIFACTS_DIR.relative_to(REPO_ROOT) / "coverage-project.xml"
COVERAGE_REPORT_TESTS = ARTIFACTS_DIR.relative_to(REPO_ROOT) / "coverage-tests.xml"
COVERAGE_REPORT_HTML_DIR = ARTIFACTS_DIR.relative_to(REPO_ROOT) / "coverage-html"
JUNIT_REPORT = ARTIFACTS_DIR.relative_to(REPO_ROOT) / "junit-report.xml"


def _inherited_salt_satisfies(session):
    """
    Check whether the session venv already provides a suitable Salt
    without installation, i.e. inherited from system site-packages on
    platforms testing against the OS-packaged Salt release.
    """
    try:
        requirement = Requirement(SALT_REQUIREMENT)
    except InvalidRequirement:
        # VCS requirements (salt==master, salt==3008.x) always (re)install
        return False
    installed_version = session.run_install(
        "python",
        "-c",
        "import contextlib, importlib.metadata, sys\n"
        "with contextlib.suppress(importlib.metadata.PackageNotFoundError):\n"
        '    sys.stdout.write(importlib.metadata.version("salt"))',
        silent=True,
        log=False,
    )
    if not installed_version:
        return False
    return requirement.specifier.contains(installed_version, prereleases=True)


def _install_requirements(
    session,
    *groups,
    install_coverage_requirements=False,
    install_source="editable",
    install_salt=True,
):
    groups = groups or []
    if session.venv_backend == "uv":
        no_progress = "--no-progress"
    else:
        no_progress = "--progress-bar=off"
    if SKIP_REQUIREMENTS_INSTALL is False:
        # Skip reinstalls into reused session venvs when the requirement
        # sources are unchanged since the last install. The project itself
        # is installed editably, so source changes don't need a refresh.
        # Remove the session venv (`make clean`) to force a reinstall.
        state = state_hash(
            tuple(groups),
            install_coverage_requirements,
            install_source,
            install_salt,
            COVERAGE_REQUIREMENT,
            SALT_REQUIREMENT,
            EXTRA_REQUIREMENTS_INSTALL,
            SYSTEM_SITE_PACKAGES,
        )
        marker = Path(session.virtualenv.location) / INSTALL_HASH_FILE
        try:
            if state and marker.read_text(encoding="utf-8").strip() == state:
                session.log("Reusing requirements installed into the session venv earlier")
                if install_source and install_source != "editable":
                    # Unlike the requirements, non-editable project installs
                    # go stale with source changes and need a refresh. Its
                    # dependencies are unchanged (hashed via pyproject.toml).
                    session.install(no_progress, "--no-deps", ".", silent=PIP_INSTALL_SILENT)
                return
        except OSError:
            pass
        if install_coverage_requirements:
            session.install(no_progress, COVERAGE_REQUIREMENT, silent=PIP_INSTALL_SILENT)

        # When testing against an OS-packaged Salt release (inherited via
        # system site-packages), pip must not resolve Salt's declared
        # dependencies: the OS satisfies them with package versions that
        # can violate the PyPI metadata's lower bounds, making pip replace
        # them with PyPI releases - swapping out the versions under test
        # at best, endlessly compiling sdists of binary packages on
        # platforms without wheels at worst (e.g. pyzmq on OpenBSD).
        # This is also why the project declares Salt as an extra instead
        # of a requirement, keeping it out of pip's dependency resolution
        # when the project itself is installed below.
        if install_salt:
            if SYSTEM_SITE_PACKAGES and _inherited_salt_satisfies(session):
                session.log("Relying on the Salt installation inherited from system site-packages")
            else:
                session.install(no_progress, SALT_REQUIREMENT, silent=PIP_INSTALL_SILENT)

        if EXTRA_REQUIREMENTS_INSTALL:
            session.log(
                "Installing the following extra requirements because the "
                "EXTRA_REQUIREMENTS_INSTALL environment variable was set: "
                "EXTRA_REQUIREMENTS_INSTALL='%s'",
                EXTRA_REQUIREMENTS_INSTALL,
            )
            install_command = [no_progress]
            install_command += [req.strip() for req in EXTRA_REQUIREMENTS_INSTALL.split()]
            session.install(*install_command, silent=PIP_INSTALL_SILENT)

        cmd = [f"--group={group}" for group in groups]
        if install_source:
            cmd.extend(("-e", ".") if install_source == "editable" else (".",))

        try:
            session.install(*cmd, silent=PIP_INSTALL_SILENT)
        except CommandFailed as err:
            # --group requires pip >= 25.1. Check if that's the cause and upgrade it if so.
            if err.return_code != 2 or session.venv_backend == "uv":
                raise
            pip_version = tuple(
                int(elem)
                for elem in session.run("pip", "--version", silent=True, log=False)
                .removeprefix("pip ")
                .split(maxsplit=1)[0]
                .split(".")
            )
            if pip_version >= (25, 1):
                raise
            session.install("pip>=25.1")
            session.install(*cmd, silent=PIP_INSTALL_SILENT)
        if state:
            marker.write_text(state, encoding="utf-8")


@nox.session(python=PYTHON_VERSIONS, venv_params=VENV_PARAMS)
def tests(session):
    _install_requirements(session, "tests", install_coverage_requirements=True)

    sitecustomize_dir = session.run("salt-factories", "--coverage", silent=True, log=False)
    python_path_env_var = os.environ.get("PYTHONPATH") or None
    if python_path_env_var is None:
        python_path_env_var = sitecustomize_dir
    else:
        python_path_entries = python_path_env_var.split(os.pathsep)
        if sitecustomize_dir in python_path_entries:
            python_path_entries.remove(sitecustomize_dir)
        python_path_entries.insert(0, sitecustomize_dir)
        python_path_env_var = os.pathsep.join(python_path_entries)

    env = {
        # The updated python path so that sitecustomize is importable
        "PYTHONPATH": python_path_env_var,
        # The full path to the .coverage data file. Makes sure we always write
        # them to the same directory
        "COVERAGE_FILE": str(COVERAGE_REPORT_DB),
        # Instruct sub processes to also run under coverage
        "COVERAGE_PROCESS_START": str(REPO_ROOT / "pyproject.toml"),
    }

    session.run("coverage", "erase")
    args = [
        "--rootdir",
        str(REPO_ROOT),
        f"--log-file={RUNTESTS_LOGFILE.relative_to(REPO_ROOT)}",
        "--log-file-level=debug",
        "--show-capture=no",
        f"--junitxml={JUNIT_REPORT}",
        "--showlocals",
        "-ra",
        "-s",
    ]
    if session._runner.global_config.forcecolor:
        args.append("--color=yes")
    if not session.posargs:
        args.append("tests/")
    else:
        for arg in session.posargs:
            if arg.startswith("--color") and args[0].startswith("--color"):
                args.pop(0)
            args.append(arg)
        for arg in session.posargs:
            if arg.startswith("-"):
                continue
            if arg.startswith(f"tests{os.sep}"):
                break
            try:
                Path(arg).resolve().relative_to(REPO_ROOT / "tests")
                break
            except ValueError:
                continue
        else:
            args.append("tests/")
    try:
        session.run("coverage", "run", "-m", "pytest", *args, env=env)
    finally:
        # Always combine and generate the XML coverage report
        try:
            session.run("coverage", "combine")
        except CommandFailed:
            # Sometimes some of the coverage files are corrupt which would
            # trigger a CommandFailed exception
            pass
        # Generate report for salt code coverage
        session.run(
            "coverage",
            "xml",
            "-o",
            str(COVERAGE_REPORT_PROJECT),
            "--omit=tests/*",
            "--include=src/saltext/proxmox/*",
        )
        # Generate report for tests code coverage
        session.run(
            "coverage",
            "xml",
            "-o",
            str(COVERAGE_REPORT_TESTS),
            "--omit=src/saltext/proxmox/*",
            "--include=tests/*",
        )
        try:
            session.run(
                "coverage",
                "report",
                "--show-missing",
                "--include=src/saltext/proxmox/*",
            )
            # If you also want to display the code coverage report on the CLI
            # for the tests, comment the call above and uncomment the line below
            # session.run(
            #    "coverage", "report", "--show-missing",
            #    "--include=src/saltext/proxmox/*,tests/*"
            # )
        finally:
            # Move the coverage DB to artifacts/coverage in order for it to be archived by CI
            if COVERAGE_REPORT_DB.exists():
                shutil.move(str(COVERAGE_REPORT_DB), str(ARTIFACTS_DIR / COVERAGE_REPORT_DB.name))


@nox.session
def test(session):
    """
    Only run the test suite with the selected venv Python version.
    """
    session.notify(f"tests-{VENV_PYVER}")


@nox.session(python=VENV_PYVER, name="cov-dev", venv_params=VENV_PARAMS)
def cov_dev(session):
    """
    Build and serve the HTML coverage report, rebuilding and reloading it whenever
    a test run refreshes the coverage database, via livereload.

    Note: Only use this in INTERACTIVE DEVELOPMENT MODE. This SHOULD NOT be called
        in CI/CD pipelines, as it will hang.
    """
    _install_requirements(
        session,
        "coverageauto",
        install_coverage_requirements=True,
        install_source=None,
        install_salt=False,
    )

    # Allow specifying server options, like --host.
    session.run(
        "python",
        str(Path("tools", "coverage_dev.py")),
        f"--data-file={ARTIFACTS_DIR.relative_to(REPO_ROOT) / COVERAGE_REPORT_DB.name}",
        f"--report-dir={COVERAGE_REPORT_HTML_DIR}",
        "--include=src/saltext/proxmox/*",
        *session.posargs,
    )


def _lint(session, rcfile, flags, paths):
    _install_requirements(
        session,
        "lint",
        "tests",
        # Editable keeps pylint's view of the package in sync with the
        # source without reinstalls (cf. the skip in _install_requirements)
        install_source="editable",
    )
    session.run("pylint", "--version")

    cmd_args = ["pylint", f"--rcfile={rcfile}"] + list(flags) + list(paths)

    src_path = str(REPO_ROOT / "src")
    python_path_env_var = os.environ.get("PYTHONPATH") or None
    if python_path_env_var is None:
        python_path_env_var = src_path
    else:
        python_path_entries = python_path_env_var.split(os.pathsep)
        if src_path in python_path_entries:
            python_path_entries.remove(src_path)
        python_path_entries.insert(0, src_path)
        python_path_env_var = os.pathsep.join(python_path_entries)

    env = {
        # The updated python path so that the project is importable without installing it
        "PYTHONPATH": python_path_env_var,
        "PYTHONUNBUFFERED": "1",
    }

    session.run(*cmd_args, env=env)


@nox.session(python=VENV_PYVER, venv_params=VENV_PARAMS)
def lint(session):
    """
    Run PyLint against the code and the test suite.
    """
    session.notify(f"lint-code-{session.python}")
    session.notify(f"lint-tests-{session.python}")


@nox.session(python=VENV_PYVER, name="lint-code", venv_params=VENV_PARAMS)
def lint_code(session):
    """
    Run PyLint against the code.
    """
    flags = ["--disable=I"]
    if session.posargs:
        paths = session.posargs
    else:
        paths = ["noxfile.py", "src/"]
    _lint(session, "pyproject.toml", flags, paths)


@nox.session(python=VENV_PYVER, name="lint-tests", venv_params=VENV_PARAMS)
def lint_tests(session):
    """
    Run PyLint against the test suite.
    """
    flags = [
        "--disable=I,redefined-outer-name,no-member,missing-module-docstring,missing-function-docstring,missing-class-docstring,attribute-defined-outside-init,inconsistent-return-statements,too-few-public-methods,too-many-arguments,too-many-positional-arguments,too-many-public-methods,unused-argument",
    ]
    if session.posargs:
        paths = session.posargs
    else:
        paths = ["tests/"]
    _lint(session, "pyproject.toml", flags, paths)


@nox.session(python=VENV_PYVER, venv_params=VENV_PARAMS)
def docs(session):
    """
    Build Docs
    """
    _install_requirements(session, "docs")
    os.chdir("docs/")
    session.run("make", "clean", external=True)
    session.run("make", "linkcheck", "SPHINXOPTS=-W", external=True)
    session.run("make", "coverage", "SPHINXOPTS=-W", external=True)
    docs_coverage_file = os.path.join("_build", "html", "python.txt")
    if os.path.exists(docs_coverage_file):
        with open(docs_coverage_file) as rfh:  # pylint: disable=unspecified-encoding
            contents = rfh.readlines()[2:]
            if contents:
                session.error("\n" + "".join(contents))
    session.run("make", "html", "SPHINXOPTS=-W", external=True)
    os.chdir(str(REPO_ROOT))


@nox.session(python=VENV_PYVER, name="docs-dev", venv_params=VENV_PARAMS)
def docs_dev(session):
    """
    Build and serve the Sphinx HTML documentation, with live reloading on file changes, via sphinx-autobuild.

    Note: Only use this in INTERACTIVE DEVELOPMENT MODE. This SHOULD NOT be called
        in CI/CD pipelines, as it will hang.
    """
    _install_requirements(session, "docsauto")

    build_dir = Path("docs", "_build", "html")

    # Allow specifying sphinx-autobuild options, like --host.
    args = ["--watch", ".", "--ignore", ".*/", "--ignore", "*/__pycache__/*"] + session.posargs
    if not any(arg.startswith("--host") for arg in args):
        # If the user is overriding the host to something other than localhost,
        # it's likely they are rendering on a remote/headless system and don't
        # want the browser to open.
        args.append("--open-browser")
    args += ["docs", str(build_dir)]

    if build_dir.exists():
        shutil.rmtree(build_dir)

    session.run("sphinx-autobuild", *args)


@nox.session(python=VENV_PYVER, name="docs-crosslink-info", venv_params=VENV_PARAMS)
def docs_crosslink_info(session):
    """
    Report intersphinx cross links information
    """
    _install_requirements(session, "docs")
    os.chdir("docs/")
    intersphinx_mapping = json.loads(
        session.run(
            "python",
            "-c",
            "import json; import conf; print(json.dumps(conf.intersphinx_mapping))",
            silent=True,
            log=False,
        )
    )
    intersphinx_mapping_list = ", ".join(list(intersphinx_mapping))
    try:
        mapping_entry = intersphinx_mapping[session.posargs[0]]
    except IndexError:
        session.error(
            f"You need to pass at least one argument whose value must be one of: {intersphinx_mapping_list}"
        )
    except KeyError:
        session.error(f"Only acceptable values for first argument are: {intersphinx_mapping_list}")
    session.run(
        "python", "-m", "sphinx.ext.intersphinx", mapping_entry[0].rstrip("/") + "/objects.inv"
    )
    os.chdir(str(REPO_ROOT))
