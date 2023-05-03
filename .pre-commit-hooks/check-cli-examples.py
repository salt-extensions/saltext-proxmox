import ast
import pathlib
import re
import sys

CODE_ROOT = pathlib.Path(__file__).resolve().parent.parent
EXECUTION_MODULES_PATH = CODE_ROOT / "src" / "saltext" / "proxmox" / "modules"


def check_cli_examples(files):
    """
    Check that every function on every execution module provides a CLI example
    """
    errors = 0
    for file in files:
        path = pathlib.Path(file).resolve()
        try:
            relpath = path.relative_to(EXECUTION_MODULES_PATH)
            if str(relpath.parent) != ".":
                # We don't want to check nested packages
                continue
        except ValueError:
            # We're only interested in execution modules
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
                    "The function {!r} on '{}' does not have a 'CLI Example:' in it's docstring".format(
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
