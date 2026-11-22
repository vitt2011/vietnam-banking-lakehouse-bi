"""Streamlit Community Cloud entrypoint for Vietnam Banking Lakehouse BI."""
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "apps"))
sys.path.insert(0, str(ROOT_DIR / "src"))

from apps.dashboard.app import main

if __name__ == "__main__":
    main()
