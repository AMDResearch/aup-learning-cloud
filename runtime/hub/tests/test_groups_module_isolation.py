import subprocess
import sys
from itertools import permutations
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
GROUPS = "runtime/hub/tests/test_groups.py"
ONBOARDING = "runtime/hub/tests/test_onboarding_handlers.py"


@pytest.mark.parametrize("test_order", permutations((GROUPS, ONBOARDING)))
def test_groups_collection_does_not_contaminate_onboarding(test_order: tuple[str, str]) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "--collect-only", "-q", *test_order],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
