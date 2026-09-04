import sys
from pathlib import Path
import shutil
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
FIXTURES = Path(__file__).parent / "fixtures"


def pytest_collection_modifyitems(config, items):
    if shutil.which("node"):
        return
    skip_node = pytest.mark.skip(reason="node not available")
    for item in items:
        if "needs_node" in item.keywords:
            item.add_marker(skip_node)
