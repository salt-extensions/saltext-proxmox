import ast
import os.path
import subprocess
from pathlib import Path

repo_path = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"]).decode().strip())
src_dir = repo_path / "src" / "saltext" / "proxmox"
doc_dir = repo_path / "docs"

docs_by_kind = {}
changed_something = False


def _find_virtualname(path):
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__virtualname__":
                    if isinstance(node.value, ast.Str):
                        virtualname = node.value.s
                        break
            else:
                continue
            break
    else:
        virtualname = path.with_suffix("").name
    return virtualname


def write_module(rst_path, path, use_virtualname=True):
    if use_virtualname:
        virtualname = "``" + _find_virtualname(path) + "``"
    else:
        virtualname = make_import_path(path)
    header_len = len(virtualname)
    # The check-merge-conflict pre-commit hook chokes here:
    # https://github.com/pre-commit/pre-commit-hooks/issues/100
    if header_len == 7:
        header_len += 1
    module_contents = f"""\
{virtualname}
{'='*header_len}

.. automodule:: {make_import_path(path)}
    :members:
"""
    if not rst_path.exists() or rst_path.read_text() != module_contents:
        print(rst_path)
        rst_path.write_text(module_contents)
        return True
    return False


def write_index(index_rst, import_paths, kind):
    if kind == "utils":
        header_text = "Utilities"
        common_path = os.path.commonpath(tuple(x.replace(".", "/") for x in import_paths)).replace(
            "/", "."
        )
        if any(x == common_path for x in import_paths):
            common_path = common_path[: common_path.rfind(".")]
    else:
        header_text = (
            "execution modules" if kind.lower() == "modules" else kind.rstrip("s") + " modules"
        )
        common_path = import_paths[0][: import_paths[0].rfind(".")]
    header = f"{'_'*len(header_text)}\n{header_text.title()}\n{'_'*len(header_text)}"
    index_contents = f"""\
.. all-saltext.proxmox.{kind}:

{header}

.. currentmodule:: {common_path}

.. autosummary::
    :toctree:

{chr(10).join(sorted('    '+p[len(common_path)+1:] for p in import_paths))}
"""
    if not index_rst.exists() or index_rst.read_text() != index_contents:
        print(index_rst)
        index_rst.write_text(index_contents)
        return True
    return False


def make_import_path(path):
    if path.name == "__init__.py":
        path = path.parent
    return ".".join(path.relative_to(repo_path / "src").with_suffix("").parts)


for path in src_dir.glob("*/*.py"):
    if path.name != "__init__.py":
        kind = path.parent.name
        if kind != "utils":
            docs_by_kind.setdefault(kind, set()).add(path)

# Utils can have subdirectories, treat them separately
for path in (src_dir / "utils").rglob("*.py"):
    if path.name == "__init__.py" and not path.read_text():
        continue
    docs_by_kind.setdefault("utils", set()).add(path)

for kind in docs_by_kind:
    kind_path = doc_dir / "ref" / kind
    index_rst = kind_path / "index.rst"
    import_paths = []
    for path in sorted(docs_by_kind[kind]):
        import_path = make_import_path(path)
        import_paths.append(import_path)
        rst_path = kind_path / (import_path + ".rst")
        rst_path.parent.mkdir(parents=True, exist_ok=True)
        change = write_module(rst_path, path, use_virtualname=kind != "utils")
        changed_something = changed_something or change

    write_index(index_rst, import_paths, kind)


# Ensure pre-commit realizes we did something
if changed_something:
    exit(2)
