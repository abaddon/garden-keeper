#!/usr/bin/env python3
"""Weekend garden brief — stdout is injected into the garden agent's cron prompt.

Run by the `garden-weekend-plan` cron job (Saturday). Makes sure the registry exists,
materialises any due work as tasks, then prints the weekend digest.
"""
import subprocess
import sys
from pathlib import Path

PROFILE = Path(__file__).resolve().parent.parent          # ~/.hermes/profiles/garden
GARDEN = PROFILE / "garden" / "scripts" / "garden.py"

if not GARDEN.exists():
    print(f"garden registry CLI missing at {GARDEN} — nothing to report.")
    raise SystemExit(0)

subprocess.run([sys.executable, str(GARDEN), "init"], capture_output=True, text=True)
raise SystemExit(subprocess.call([sys.executable, str(GARDEN), "brief", "--mode", "weekend"]))
