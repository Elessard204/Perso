import sys
from datetime import date
from pathlib import Path

LOGICIEL = Path(__file__).resolve().parent.parent / "_logiciel"
sys.path.insert(0, str(LOGICIEL))

J = date(2026, 11, 3)
