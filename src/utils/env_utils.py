# src/utils/env_utils.py
# Console-only environment utilities (no plotting).

import sys
import os
import platform
import importlib
from datetime import datetime
from pathlib import Path

def show_system_info():
    """Display basic system and Python environment info."""
    
    print("\n🖥️  System Information:")
    print("  - Platform:      {}".format(platform.system()))
    print("  - Release:       {}".format(platform.release()))
    print("  - Python:        {}".format(sys.version.split()[0]))
    print("  - Architecture:  {}".format(platform.machine()))
    print("  - Working dir:   {}".format(os.getcwd()))
    print("  - Time:          {}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

def print_tree(root=".", max_depth=2, ignore_names=None, ignore_ext=None, show_hidden=False):
    """
    Print a tree of folders and files up to max_depth (default: 2).

    ignore_names : set of directory/file names to skip (e.g., {'.git', '__pycache__'})
    ignore_ext   : set of file extensions to skip (e.g., {'.log', '.pyc'})
    show_hidden  : if False, hide files/folders starting with '.'
    """
    if ignore_names is None:
        ignore_names = {
            ".git", ".gitkeep",
            "__pycache__", ".venv",
            "node_modules", ".mypy_cache", ".ruff_cache", ".idea"
        }
    if ignore_ext is None:
        ignore_ext = {".log", ".pyc", ".tmp"}

    root_path = Path(root).resolve()

    def _is_ignored(p):
        name = p.name

        # hide dotfiles / dotdirs unless allowed
        if not show_hidden and name.startswith("."):
            return True

        # exact name match
        if name in ignore_names:
            return True

        # extension-based ignore (always uses dot-based suffix)
        if p.is_file() and p.suffix in ignore_ext:
            return True

        return False

    def _list_entries(path):
        try:
            entries = list(path.iterdir())
        except PermissionError:
            entries = []
        entries.sort(key=lambda q: (not q.is_dir(), q.name.lower()))
        return entries

    def _print_dir(path, prefix, depth):
        if depth > max_depth:
            return
        entries = [e for e in _list_entries(path) if not _is_ignored(e)]
        count = len(entries)
        for i, entry in enumerate(entries):
            connector = "└── " if i == count - 1 else "├── "
            display = entry.name + ("/" if entry.is_dir() else "")
            print("{}{}{}".format(prefix, connector, display))
            if entry.is_dir() and depth < max_depth:
                extension = "    " if i == count - 1 else "│   "
                _print_dir(entry, prefix + extension, depth + 1)

    print("\n📂 Project Tree (root='{}', depth={}):".format(str(root_path), max_depth))
    print(root_path.name + "/")
    _print_dir(root_path, "", 1)
