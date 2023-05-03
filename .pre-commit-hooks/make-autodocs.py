from pathlib import Path


autodocs = {}

loader_dirs = (
    "engines",
    "modules",
    "returners",
    "states",
)

for ldir in loader_dirs:
    autodocs[ldir] = []

trans = str.maketrans({"_": r"\_"})
docs_path = Path("docs")
ref_path = docs_path / "ref"

for path in Path("src").glob("**/*.py"):
    if path.name == "__init__.py":
        continue
    kind = path.parent.name
    if kind in loader_dirs:
        import_path = ".".join(path.with_suffix("").parts[1:])
        autodocs[kind].append(import_path)
        rst_path = ref_path / kind / (import_path + ".rst")
        if rst_path.is_file():
            continue
        rst_path.parent.mkdir(parents=True, exist_ok=True)
        rst_path.write_text(
            f"""{import_path.translate(trans)}
{'='*len(import_path.translate(trans))}

.. currentmodule:: {'.'.join(import_path.split('.')[:-1])}

.. autodata:: {import_path.split('.')[-1]}"""
        )

for ldir in autodocs:
    if not autodocs[ldir]:
        continue
    all_rst = ref_path / ldir / "all.rst"
    if all_rst.is_file():
        continue
    all_rst.parent.mkdir(parents=True, exist_ok=True)
    all_rst.write_text(
        f"""
.. all-saltext.proxmox.{ldir}:

{'-'*len(ldir)}--------
{ldir.title()} Modules
{'-'*len(ldir)}--------

.. autosummary::
    :toctree:

{chr(10).join(sorted('    '+mod for mod in autodocs[ldir]))}
"""
    )
