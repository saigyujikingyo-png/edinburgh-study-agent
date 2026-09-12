"""Portable source launcher. Install requirements first; no package download at server startup."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from edinburgh_study_agent.server import main
main()
