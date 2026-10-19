"""Keep the virtual environment identity when launching an installed Python."""
from pathlib import Path


def interpreter_path(path):
    # venv/bin/python is commonly a symlink to the base interpreter. Resolving
    # it discards pyvenv.cfg discovery and runs the wrong installed packages.
    return str(Path(path).absolute())
