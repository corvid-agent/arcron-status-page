#!/usr/bin/env python3
"""Append one overdue-split sample into docs/history.json + docs/history.sqlite.

Reads current docs/due.json by default (honest TestNet snapshot). Pass --refresh
to run refresh_due.py first. Never submits, no mnemonic, TestNet only.
Skips keepers/upkeeps 81 and 87 as deploy targets (chain id 81 in due.json is fine).
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
DUE_PATH = DOCS / "due.json"
HIST_JSON = DOCS / "history.json"
HIST_DB = DOCS / "history.sqlite"
SKIP_UPKEEP = frozenset({81, 87})

SCHEMA = """
CREATE TABLE IF NOT EXISTS samples (
  t TEXT,
  round INTEGER,
  listed INTEGER,
  due INTEGER,
  skipped INTEGER,
  unfunded INTEGER,
  reverting INTEGER,
  waiting INTEGER,
  other INTEGER,
  on_schedule INTEGER,
  escrow_micro INTEGER,
  fee_pressure_micro INTEGER,
  source TEXT
)
"""


def sample_from_due(due: dict, source: str) -> dict:
    buckets = ("unfunded", "reverting", "waiting", "other")
    counts = {k: len(due.get(k) or []) for k in buckets}
    on_schedule = due.get("onSchedule") or []
    skipped = due.get("skipped") or []
    # Never count Vigil 81 / 87 as listed deploy targets in history math beyond skip tally.
    escrow = 0
    fee_pressure = 0
    for k in buckets:
        for e in due.get(k) or []:
            uid = int(e.get("id") or 0)
            if uid in SKIP_UPKEEP:
                continue
            escrow += int(e.get("balance") or 0)
            fee_pressure += int(e.get("effectiveFee") or 0)
    due_n = sum(counts.values())
    listed = due_n + len(on_schedule) + len(skipped)
    return {
        "t": due.get("probedAt") or "",
        "round": int(due["lastRound"]),
        "listed": listed,
        "due": due_n,
        "skipped": len(skipped),
        "unfunded": counts["unfunded"],
        "reverting": counts["reverting"],
        "waiting": counts["waiting"],
        "other": counts["other"],
        "on_schedule": len(on_schedule),
        "escrow_micro": escrow,
        "fee_pressure_micro": fee_pressure,
        "source": source,
    }


def load_history() -> list[dict]:
    if not HIST_JSON.exists():
        return []
    data = json.loads(HIST_JSON.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def rewrite_sqlite(rows: list[dict]) -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    if HIST_DB.exists():
        HIST_DB.unlink()
    con = sqlite3.connect(HIST_DB)
    con.execute(SCHEMA)
    con.executemany(
        "INSERT INTO samples VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            (
                r.get("t"),
                r.get("round"),
                r.get("listed"),
                r.get("due"),
                r.get("skipped"),
                r.get("unfunded"),
                r.get("reverting"),
                r.get("waiting"),
                r.get("other"),
                r.get("on_schedule"),
                r.get("escrow_micro"),
                r.get("fee_pressure_micro"),
                r.get("source"),
            )
            for r in rows
        ],
    )
    con.commit()
    con.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--refresh",
        action="store_true",
        help="run scripts/refresh_due.py before sampling due.json",
    )
    args = ap.parse_args()

    if args.refresh:
        refresh = ROOT / "scripts" / "refresh_due.py"
        print("running refresh_due.py …", file=sys.stderr)
        rc = subprocess.call([sys.executable, str(refresh)])
        if rc != 0:
            print(f"refresh_due failed rc={rc}", file=sys.stderr)
            return rc

    if not DUE_PATH.is_file():
        print(f"missing {DUE_PATH}", file=sys.stderr)
        return 1

    due = json.loads(DUE_PATH.read_text(encoding="utf-8"))
    if due.get("network") != "testnet-v1.0":
        print("refuse: due.json network is not testnet-v1.0", file=sys.stderr)
        return 1
    if int(due.get("chain") or 0) != 81:
        print("refuse: due.json chain is not Algorand TestNet chain id 81", file=sys.stderr)
        return 1

    sample = sample_from_due(due, source="probe_history.py from docs/due.json")
    hist = load_history()
    # Append-only: skip duplicate same round + same source label family.
    if any(int(h.get("round") or 0) == sample["round"] for h in hist):
        print(json.dumps({"skipped_duplicate": True, "round": sample["round"], "points": len(hist)}))
        rewrite_sqlite(hist)
        return 0

    hist.append(sample)
    hist.sort(key=lambda h: (int(h.get("round") or 0), str(h.get("t") or "")))
    HIST_JSON.write_text(json.dumps(hist, indent=2) + "\n", encoding="utf-8")
    rewrite_sqlite(hist)
    print(json.dumps({"appended": True, "round": sample["round"], "points": len(hist), "sample": sample}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
