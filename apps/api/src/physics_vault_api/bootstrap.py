from __future__ import annotations

import sys
from pathlib import Path


def configure_workspace_imports() -> None:
    project_root = Path(__file__).resolve().parents[4]
    packages_root = project_root / "packages"
    if packages_root.exists():
        path = str(packages_root)
        if path not in sys.path:
            sys.path.insert(0, path)


configure_workspace_imports()
