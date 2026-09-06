"""PyInstaller entry point for the Collection AI Configuration exe."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.gui_config.app import run

if __name__ == "__main__":
    run()
