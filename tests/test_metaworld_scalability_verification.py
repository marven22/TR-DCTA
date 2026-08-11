import json
from pathlib import Path

import pytest

from scripts.verify_metaworld_scalability import OUTPUT, verify


pytestmark = pytest.mark.skipif(
    not Path(OUTPUT).is_file(), reason="requires the external scalability artifact bundle"
)


def test_frozen_scalability_package_passes_all_verification_checks():
    result = verify()
    assert result["passed"]
    assert result["failed_count"] == 0
    assert result["passed_count"] == result["check_count"] == 20


def test_stored_verification_record_matches_current_audit():
    stored = json.loads(Path(OUTPUT).read_text(encoding="utf-8"))
    current = verify()
    assert stored["passed"] == current["passed"]
    assert stored["checks"] == current["checks"]
