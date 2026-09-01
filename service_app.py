"""
PyInstaller entry point for the Collection AI Scheduler Service exe.

Usage (elevated / Administrator prompt):
    CollectionAI-Service.exe install
    CollectionAI-Service.exe start
    CollectionAI-Service.exe stop
    CollectionAI-Service.exe remove
    CollectionAI-Service.exe debug
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.scheduler.win_service import main

if __name__ == "__main__":
    main()
