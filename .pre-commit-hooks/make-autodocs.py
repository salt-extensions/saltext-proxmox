import ast
import posixpath
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
                if (
                    isinstance(target, ast.Name)
                    and target.id == "__virtualname__"
                    and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, str)
                ):
                    virtualname = node.value.value
                    break
            else:
                continue
            break
    else:
        if path.name == "__init__.py":
            # Resource type packages carry their connection module there
            path = path.parent
        virtualname = path.with_suffix("").name
    return virtualname


def _kind_title(kind):
    if kind == "utils":
        return "Utilities"
    if kind.lower() == "modules":
        return "Execution Modules"
    return (kind.rstrip("s") + " modules").title()


def write_file(rst_path, contents):
    if not rst_path.exists() or rst_path.read_text() != contents:
        print(rst_path)
        rst_path.write_text(contents)
        return True
    return False


def write_module(rst_path, header, paths):
    header_len = len(header)
    # The check-merge-conflict pre-commit hook chokes here:
    # https://github.com/pre-commit/pre-commit-hooks/issues/100
    if header_len == 7:
        header_len += 1
    automodules = "\n".join(f""".. automodule:: {make_import_path(path)}
    :members:
""" for path in paths)
    module_contents = f"""\
{header}
{'='*header_len}

{automodules}"""
    return write_file(rst_path, module_contents)


def write_index(index_rst, import_paths, kind):
    header_text = _kind_title(kind)
    if kind in ("utils", "resources"):
        # These can contain nested modules, so find the common parent
        common_path = posixpath.commonpath(
            tuple(x.replace(".", "/") for x in import_paths)
        ).replace("/", ".")

        if any(x == common_path for x in import_paths):
            common_path = common_path[: common_path.rfind(".")]
    else:
        common_path = import_paths[0][: import_paths[0].rfind(".")]
    header = f"{'_'*len(header_text)}\n{header_text}\n{'_'*len(header_text)}"
    index_contents = f"""\
.. all-saltext.proxmox.{kind}:

{header}

.. currentmodule:: {common_path}

.. autosummary::
    :toctree:

{chr(10).join(sorted('    '+p[len(common_path)+1:] for p in import_paths))}
"""
    return write_file(index_rst, index_contents)


def make_import_path(path):
    if path.name == "__init__.py":
        path = path.parent
    return ".".join(path.relative_to(repo_path / "src").with_suffix("").parts)


tracked = set(
    subprocess.check_output(["git", "ls-files", "-z"], text=True, cwd=repo_path).split("\x00")
)

for path in src_dir.glob("*/*.py"):
    if path.name != "__init__.py" and path.relative_to(repo_path).as_posix() in tracked:
        kind = path.parent.name
        if kind not in ("utils", "resources"):
            docs_by_kind.setdefault(kind, set()).add(path)

# Utils can have subdirectories, treat them separately
for path in (src_dir / "utils").rglob("*.py"):
    if path.relative_to(repo_path).as_posix() not in tracked:
        continue
    if path.name == "__init__.py" and not path.read_text():
        continue
    docs_by_kind.setdefault("utils", set()).add(path)

# Resource types can be packages containing per-type loader overlay
# directories (resources/<rtype>/{modules,states,grains,...}), treat
# them separately
for path in (src_dir / "resources").rglob("*.py"):
    if path.relative_to(repo_path).as_posix() not in tracked:
        continue
    if (
        path.name == "__init__.py"
        and path.parent.parent != src_dir / "resources"
        or not path.read_text()
    ):
        # Only a resource type package's own __init__.py is a loader
        # module (the connection module), the other ones are packaging
        # artifacts.
        continue
    docs_by_kind.setdefault("resources", set()).add(path)


def _group_by_virtualname(paths):
    grouped = {}
    for path in sorted(paths):
        grouped.setdefault(_find_virtualname(path), []).append(path)
    # Make the module whose file name matches the virtualname the
    # canonical one, i.e. the first in the group and the one the
    # rst file is named after.
    for virtualname, group in grouped.items():
        for path in group:
            stem = path.parent.name if path.name == "__init__.py" else path.stem
            if stem in (virtualname, virtualname + "_mod", virtualname + "mod"):
                group.remove(path)
                group.insert(0, path)
                break
    return grouped


def _overlay_order(overlay_kind):
    """
    Order the per-type loader overlay sections like Salt's docs do,
    unknown kinds last in alphabetical order.
    """
    try:
        return (("modules", "states", "grains").index(overlay_kind), overlay_kind)
    except ValueError:
        return (99, overlay_kind)


def _process_resources(kind_path, paths):
    """
    Document each resource type with its connection module page (headed
    by its virtualname) as the entry point. Each per-type loader overlay
    directory (``resources/<rtype>/<loader_dir>/``) gets its own index
    page ("Execution Modules", "State Modules", ...) hanging off the
    type page, so the overlay modules nest under a per-kind subheading
    in the navigation instead of being appended to one flat list.

    There is no kind index: the root document's "Provided Resources"
    toctree globs ``ref/resources/*``, which picks up exactly the type
    pages because everything else is written to a ``<rtype>/``
    subdirectory (toctree globs do not cross directories).
    """
    resources_dir = src_dir / "resources"
    types = {}
    for path in sorted(paths):
        rel = path.relative_to(resources_dir).parts
        if len(rel) == 1:
            # Flat connection module
            types.setdefault(path.stem, {"conn": None, "overlays": {}})["conn"] = path
        elif len(rel) == 2 and path.name == "__init__.py":
            # Resource type package's connection module
            types.setdefault(rel[0], {"conn": None, "overlays": {}})["conn"] = path
        else:
            overlays = types.setdefault(rel[0], {"conn": None, "overlays": {}})["overlays"]
            overlays.setdefault(rel[1], set()).add(path)

    changed = False
    index_paths = []
    written_rst_paths = set()
    kind_path.mkdir(parents=True, exist_ok=True)
    for rtype, info in sorted(types.items()):
        conn = info["conn"]
        blocks = []
        if conn is not None:
            header = f"``{_find_virtualname(conn)}``"
            type_import_path = make_import_path(conn)
            blocks.append(f".. automodule:: {type_import_path}\n    :members:\n")
        else:
            # Overlay modules without a connection module (unusual)
            header = f"``{rtype}``"
            type_import_path = f"saltext.proxmox.resources.{rtype}"
        header_len = len(header)
        if header_len == 7:
            header_len += 1
        blocks.insert(0, f"{header}\n{'='*header_len}\n")

        type_path = kind_path / rtype
        if info["overlays"]:
            type_path.mkdir(parents=True, exist_ok=True)
        overlay_index_paths = []
        for overlay_kind in sorted(info["overlays"], key=_overlay_order):
            overlay_import_path = f"saltext.proxmox.resources.{rtype}.{overlay_kind}"
            entries = []
            for virtualname, group in _group_by_virtualname(info["overlays"][overlay_kind]).items():
                import_path = make_import_path(group[0])
                rst_path = type_path / (import_path + ".rst")
                written_rst_paths.add(rst_path)
                changed |= write_module(rst_path, f"``{virtualname}``", group)
                entries.append(import_path[len(overlay_import_path) + 1 :])
            # One index page per overlay kind: its title provides the
            # per-kind subheading the overlay modules nest under in the
            # navigation.
            title = _kind_title(overlay_kind)
            overlay_index_contents = f"""\
{title}
{'='*len(title)}

.. currentmodule:: {overlay_import_path}

.. autosummary::
    :toctree:

{chr(10).join('    ' + entry for entry in sorted(entries))}
"""
            overlay_index_rst = type_path / (overlay_import_path + ".rst")
            written_rst_paths.add(overlay_index_rst)
            changed |= write_file(overlay_index_rst, overlay_index_contents)
            overlay_index_paths.append(f"{rtype}/{overlay_import_path}")

        if overlay_index_paths:
            heading = "Provided Modules"
            blocks.append(f"{heading}\n{'-'*len(heading)}\n")
            blocks.append(
                ".. toctree::\n    :maxdepth: 1\n\n"
                + "\n".join("    " + p for p in overlay_index_paths)
                + "\n"
            )

        type_rst_path = kind_path / (type_import_path + ".rst")
        written_rst_paths.add(type_rst_path)
        changed |= write_file(type_rst_path, "\n".join(blocks))
        index_paths.append(type_import_path)
    return changed, index_paths, written_rst_paths


for kind, mods in docs_by_kind.items():
    kind_path = doc_dir / "ref" / kind
    index_rst = kind_path / "index.rst"
    import_paths = []
    written_rst_paths = set()
    if kind == "resources":
        change, import_paths, written_rst_paths = _process_resources(kind_path, mods)
        changed_something = changed_something or change
    else:
        if kind == "utils":
            # Utils are documented under their import path, no grouping necessary
            grouped = {make_import_path(path): [path] for path in sorted(mods)}
        else:
            grouped = {
                f"``{virtualname}``": paths
                for virtualname, paths in _group_by_virtualname(mods).items()
            }
        for header, paths in grouped.items():
            import_path = make_import_path(paths[0])
            import_paths.append(import_path)
            rst_path = kind_path / (import_path + ".rst")
            rst_path.parent.mkdir(parents=True, exist_ok=True)
            written_rst_paths.add(rst_path)
            change = write_module(rst_path, header, paths)
            changed_something = changed_something or change

    # Remove stale generated rst files, e.g. after a module has been renamed/
    # removed or merged into another one's docs by sharing its virtualname.
    # Resource type docs nest in per-type subdirectories, search recursively.
    stale_glob = kind_path.rglob if kind == "resources" else kind_path.glob
    for rst_path in stale_glob(f"saltext.proxmox.{kind}.*.rst"):
        if rst_path not in written_rst_paths:
            print(f"Removing stale {rst_path}")
            rst_path.unlink()
            changed_something = True

    if kind == "resources":
        # No kind index: the root document's "Provided Resources" toctree
        # globs the per-type pages directly.
        if index_rst.exists():
            print(f"Removing stale {index_rst}")
            index_rst.unlink()
            changed_something = True
    else:
        changed_something |= write_index(index_rst, sorted(import_paths), kind)


# Ensure pre-commit realizes we did something
if changed_something:
    raise SystemExit(2)
