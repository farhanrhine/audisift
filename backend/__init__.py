"""Audisift backend package."""

import os
import sys
import platform
from pathlib import Path

# Fix for DLL loading issues on Windows (e.g. greenlet dependency of SQLAlchemy)
# If running on Windows, register the virtualenv's scripts and root directories
# with os.add_dll_directory to ensure compiled C++ extensions can find their runtimes.
if platform.system() == "Windows":
    base_dir = Path(__file__).resolve().parent.parent
    # Check for local .venv
    venv_dir = base_dir / ".venv"
    if venv_dir.exists():
        try:
            os.add_dll_directory(str(venv_dir))
            scripts_dir = venv_dir / "Scripts"
            if scripts_dir.exists():
                os.add_dll_directory(str(scripts_dir))
        except Exception as e:
            # Fallback gracefully
            print(f"[DLL Init Warning] Failed to register DLL directory: {e}", file=sys.stderr)
