"""
Polyfill for very basic ``plumbum`` functionality, no external libs required.
Makes scripts that call a lot of CLI commands much more pleasant to write.
"""

import os
import platform
import shlex
import shutil
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Union


class CommandNotFound(RuntimeError):
    """
    Raised when a command cannot be found in $PATH
    """


@dataclass(frozen=True)
class ProcessResult:
    """
    The full process result, returned by ``.run`` methods.
    The ``__call__`` ones just return stdout.
    """

    retcode: int
    stdout: Union[str, bytes]
    stderr: Union[str, bytes]
    argv: tuple

    def check(self, retcode=None):
        """
        Check if the retcode is expected. retcode can be a list.
        """
        if retcode is None:
            expected = [0]
        elif not isinstance(retcode, (list, tuple)):
            expected = [retcode]
        if self.retcode not in expected:
            raise ProcessExecutionError(self.argv, self.retcode, self.stdout, self.stderr)

    def __str__(self):
        msg = [
            "Process execution result:",
            f"Command: {shlex.join(self.argv)}",
            f"Retcode: {self.retcode}",
            "Stdout:   |",
        ]
        msg += [" " * 10 + "| " + line for line in str(self.stdout).splitlines()]
        msg.append("Stderr:   |")
        msg += [" " * 10 + "| " + line for line in str(self.stderr).splitlines()]
        return "\n".join(msg)


class ProcessExecutionError(OSError):
    """
    Raised by ProcessResult.check when an unexpected retcode was returned.
    """

    def __init__(self, argv, retcode, stdout, stderr):
        self.argv = argv
        self.retcode = retcode
        if isinstance(stdout, bytes):
            stdout = ascii(stdout)
        if isinstance(stderr, bytes):
            stderr = ascii(stderr)
        self.stdout = stdout
        self.stderr = stderr

    def __str__(self):
        msg = [
            "Process finished with unexpected exit code",
            f"Retcode: {self.retcode}",
            f"Command: {shlex.join(self.argv)}",
            "Stdout:   |",
        ]
        msg += [" " * 10 + "| " + line for line in str(self.stdout).splitlines()]
        msg.append("Stderr:   |")
        msg += [" " * 10 + "| " + line for line in str(self.stderr).splitlines()]
        return "\n".join(msg)


class Local:
    """
    Glue for command environment defaults.
    Should be treated as a singleton.

    Example:

        local = Local()

        some_cmd = local["some_cmd"]
        with local.cwd(some_path), local.env(FOO="bar"):
            some_cmd("baz")

        # A changed $PATH requires to rediscover commands.
        with local.prepend_path(important_path):
            local["other_cmd"]()
        with local.venv(venv_path):
            local["python"]("-m", "pip", "install", "salt")

    """

    def __init__(self):
        # Explicitly cast values to strings to avoid problems on Windows
        self._env = {k: str(v) for k, v in os.environ.items()}

    def __getitem__(self, exe):
        """
        Return a LocalCommand in this context.
        """
        return LocalCommand(exe, _local=self)

    @property
    def path(self):
        """
        List of paths in the context's $PATH.
        """
        return self._env.get("PATH", "").split(os.pathsep)

    @contextmanager
    def cwd(self, path):
        """
        Set the default current working directory for commands inside this context.
        """
        prev = Path(os.getcwd())
        new = prev / path
        os.cwd(new)
        try:
            yield
        finally:
            os.cwd(prev)

    @contextmanager
    def env(self, **kwargs):
        """
        Override default env vars (sourced from the current process' environment)
        for commands inside this context.
        """
        prev = self._env.copy()
        self._env.update((k, str(v)) for k, v in kwargs.items())
        try:
            yield
        finally:
            self._env = prev

    @contextmanager
    def path_prepend(self, *args):
        """
        Prepend paths to $PATH for commands inside this context.

        Note: If you have saved a reference to an already requested command,
        its $PATH will be updated, but it might not be the command
        that would have been returned by a new request.
        """
        new_path = [str(arg) for arg in args] + self.path
        with self.env(PATH=os.pathsep.join(new_path)):
            yield

    @contextmanager
    def venv(self, venv_dir):
        """
        Enter a Python virtual environment. Effectively prepends its bin dir
        to $PATH and sets ``VIRTUAL_ENV``.
        """
        venv_dir = Path(venv_dir)
        if not venv_dir.is_dir() or not (venv_dir / "pyvenv.cfg").exists():
            raise ValueError(f"Not a virtual environment: {venv_dir}")
        venv_bin_dir = venv_dir / "bin"
        if platform.system() == "Windows":
            venv_bin_dir = venv_dir / "Scripts"
        with self.path_prepend(venv_bin_dir), self.env(VIRTUAL_ENV=str(venv_dir)):
            yield


@dataclass(frozen=True)
class Executable:
    """
    Utility class used to avoid repeated command lookups.
    """

    _exe: str

    def __str__(self):
        return self._exe

    def __repr__(self):
        return f"Executable <{self._exe}>"


@dataclass(frozen=True)
class Command:
    """
    A command object, can be instantiated directly. Does not follow ``Local``.
    """

    exe: Union[Executable, str]
    args: tuple[str, ...] = ()

    def __post_init__(self):
        if not isinstance(self.exe, Executable):
            if not (full_exe := self._which(self.exe)):
                raise CommandNotFound(self.exe)
            object.__setattr__(self, "exe", Executable(full_exe))

    def _which(self, exe):
        return shutil.which(exe)

    def _get_env(self, overrides=None):
        base = {k: str(v) for k, v in os.environ.items()}
        base.update(overrides or {})
        return base

    def __getitem__(self, arg_or_args):
        """
        Returns a subcommand with bound parameters.

        Example:

            git = Command("git")["-c", "commit.gpgsign=0"]
            # ...
            git("add", ".")
            git("commit", "-m", "testcommit")

        """
        if not isinstance(arg_or_args, tuple):
            arg_or_args = (arg_or_args,)
        return type(self)(self.exe, tuple(*self.args, *arg_or_args), _local=self._local)

    def __call__(self, *args, **kwargs):
        """
        Run this command and return stdout.
        """
        return self.run(*args, **kwargs).stdout

    def __str__(self):
        return shlex.join([self.exe] + list(self.args))

    def __repr__(self):
        return f"Command<{self.exe}, {self.args!r}>"

    def run(self, *args, check=True, env=None, **kwargs):
        """
        Run this command and return the full output.
        """
        kwargs.setdefault("stdout", subprocess.PIPE)
        kwargs.setdefault("stderr", subprocess.PIPE)
        kwargs.setdefault("text", True)
        argv = [str(self.exe), *self.args, *args]
        proc = subprocess.run(argv, check=False, env=self._get_env(env), **kwargs)
        ret = ProcessResult(
            retcode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            argv=argv,
        )
        if check:
            ret.check()
        return ret


# Should be imported from here.
local = Local()


@dataclass(frozen=True)
class LocalCommand(Command):
    """
    Command returned by Local()["some_command"]. Follows local contexts.
    """

    if sys.version_info >= (3, 10):
        _local: Local = field(kw_only=True, repr=False, default=local)
    else:
        _local: Local = field(repr=False, default=local)

    def _which(self, exe):
        return shutil.which(exe, path=self._local._env.get("PATH", ""))

    def _get_env(self, overrides=None):
        base = self._local._env.copy()
        base.update(overrides or {})
        return base


# We must assume git is installed
git = local["git"]
