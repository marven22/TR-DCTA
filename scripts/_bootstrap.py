"""Put ``src/`` on the path so scripts can ``import mcx`` without installation."""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

RESULTS_DIR = os.path.join(_ROOT, "results")
DOCS_DIR = os.path.join(_ROOT, "docs")
