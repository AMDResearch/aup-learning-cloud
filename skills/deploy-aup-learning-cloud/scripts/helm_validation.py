# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.

import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

CHART = "runtime/chart"


@dataclass(frozen=True, slots=True)
class HelmValidationReporter:
    ok: Callable[[str], None]
    warn: Callable[[str], None]
    fail: Callable[[str], None]


def check_helm(repo: Path, values: list[str], reporter: HelmValidationReporter) -> None:
    if not shutil.which("helm"):
        reporter.warn("helm not on PATH; skipped chart dry-run")
        return
    chart = repo / CHART
    if not chart.exists():
        reporter.warn(f"chart not found at {CHART}; skipped dry-run")
        return
    cmd = ["helm", "template", "jupyterhub", str(chart)]
    for rel in values or ["runtime/values.yaml"]:
        path = (repo / rel) if not Path(rel).is_absolute() else Path(rel)
        if path.exists():
            cmd += ["-f", str(path)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode == 0:
        reporter.ok("helm template rendered the chart successfully")
    else:
        tail = (proc.stderr or proc.stdout).strip().splitlines()[-5:]
        reporter.fail("helm template failed:\n        " + "\n        ".join(tail))
