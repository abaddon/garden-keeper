#!/usr/bin/env python3
"""Monthly garden review — stdout is injected into the garden agent's cron prompt.

Run by the `garden-monthly-review` cron job (1st of the month). 31-day horizon, plus the
month's seasonal headline.
"""
import subprocess
import sys
from pathlib import Path

PROFILE = Path(__file__).resolve().parent.parent
GARDEN = PROFILE / "garden" / "scripts" / "garden.py"

if not GARDEN.exists():
    print(f"garden registry CLI missing at {GARDEN} — nothing to report.")
    raise SystemExit(0)

subprocess.run([sys.executable, str(GARDEN), "init"], capture_output=True, text=True)
raise SystemExit(subprocess.call([sys.executable, str(GARDEN), "brief", "--mode", "monthly"]))
