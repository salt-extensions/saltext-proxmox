import ast
import pathlib
import re
import sys

CODE_ROOT = pathlib.Path(__file__).resolve().parent.parent
PACKAGE_PATH = CODE_ROOT / "src" / "saltext" / "proxmox"
EXECUTION_MODULES_PATH = PACKAGE_PATH / "modules"
RESOURCES_PATH = PACKAGE_PATH / "resources"


def _is_execution_module(path):
    try:
        relpath = path.relative_to(EXECUTION_MODULES_PATH)
        # We don't want to check nested packages
        return str(relpath.parent) == "."
    except ValueError:
        pass
    try:
        relpath = path.relative_to(RESOURCES_PATH)
    except ValueError:
        return False
    # Per-resource-type execution module overlays:
    # resources/<rtype>/modules/<module>.py
    return len(relpath.parts) == 3 and relpath.parts[1] == "modules"


def check_cli_examples(files):
    """
    Check that every function on every execution module provides a CLI example
    """
    errors = 0
    for file in files:
        path = pathlib.Path(file).resolve()
        if path.name == "__init__.py" or not _is_execution_module(path):
            continue
        module = ast.parse(path.read_text(), filename=str(path))
        for funcdef in [node for node in module.body if isinstance(node, ast.FunctionDef)]:
            if funcdef.name.startswith("_"):
                # We're not interested in internal functions
                continue

            docstring = ast.get_docstring(funcdef, clean=False)
            if not docstring:
                errors += 1
                print(
                    "The function {!r} on '{}' does not have a docstring".format(
                        funcdef.name,
                        path.relative_to(CODE_ROOT),
                    ),
                    file=sys.stderr,
                )
                continue

            if _check_cli_example_present(docstring) is False:
                errors += 1
                print(
                    "The function {!r} on '{}' does not have a 'CLI Example:' in its docstring".format(
                        funcdef.name,
                        path.relative_to(CODE_ROOT),
                    ),
                    file=sys.stderr,
                )
                continue
    sys.exit(errors)


CLI_EXAMPLE_PRESENT_RE = re.compile(r"CLI Example(?:s)?:")


def _check_cli_example_present(docstring):
    return CLI_EXAMPLE_PRESENT_RE.search(docstring) is not None


if __name__ == "__main__":
    check_cli_examples(sys.argv[1:])
