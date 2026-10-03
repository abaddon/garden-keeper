#!/usr/bin/env python3
"""Rewrite the generated section of docs/CLI.md from the CLI itself.

The reference must not be able to drift from the tool: run this after touching
garden/scripts/garden.py and commit both files together.

    python docs/tools/regen-cli.py        # rewrites between the generated markers in docs/CLI.md
"""
import datetime
import hashlib
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]          # the profile directory
CLI = ROOT / "garden/scripts/garden.py"
DOC = ROOT / "docs/CLI.md"
BEGIN = "<!-- generated:begin -->"
END = "<!-- generated:end -->"

GROUPS = [
    (None, "Top level"),
    ("needs", "What is waiting on the user (the one definition)"),
    ("plant", "The plant registry"),
    ("task", "Work items"),
    ("photo", "Photos and their assessments"),
    ("obs", "Observations, including follow-ups"),
    ("treat", "Feeding and treatments"),
    ("pond", "The pond and its readings"),
    ("journal", "The agent's own log"),
    ("advice", "Advice given"),
    ("rule", "Standing rules"),
    ("intake", "The capture queue"),
    ("brief", "The digests the cron jobs send"),
    ("stats", "Counts, and which database this is"),
    ("search", "Free-text search across the registry"),
    ("export", "Dump the registry"),
    ("init", "Create or upgrade the tables"),
]


def help_text(args):
    done = subprocess.run([sys.executable, str(CLI), *args, "--help"],
                          capture_output=True, text=True, cwd=ROOT)
    return (done.stdout or done.stderr).strip()


def main():
    digest = hashlib.sha256(CLI.read_bytes()).hexdigest()[:10]
    out = [BEGIN,
           f"<!-- garden.py sha256:{digest} — regenerate with `python docs/tools/regen-cli.py` -->",
           "",
           f"_Generated from `garden/scripts/garden.py` on {datetime.date.today().isoformat()}._",
           ""]
    for cmd, title in GROUPS:
        if cmd is None:
            out += ["Every command takes `--json` (before the subcommand) for machine-readable output.",
                    "", "```text", help_text([]), "```", ""]
            continue
        text = help_text([cmd])
        if not text:
            continue
        out += [f"### `{cmd}` — {title}", "", "```text", text, "```", ""]
        # one level deeper: the subcommands of a command group
        head = text.splitlines()[0] if text else ""
        if "{" in head:
            subs = head.split("{", 1)[1].split("}", 1)[0].split(",")
            for sub in [s.strip() for s in subs if s.strip() and s.strip() != "-h"]:
                deeper = help_text([cmd, sub])
                if deeper:
                    out += [f"**`{cmd} {sub}`**", "", "```text", deeper, "```", ""]
    out.append(END)

    body = DOC.read_text()
    start, stop = body.index(BEGIN), body.index(END) + len(END)
    DOC.write_text(body[:start] + "\n".join(out) + body[stop:])
    print(f"CLI.md regenerated from garden.py @ {digest}")


if __name__ == "__main__":
    main()
