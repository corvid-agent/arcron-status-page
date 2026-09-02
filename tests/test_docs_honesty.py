"""Static honesty: docs/due.json is TestNet overdue-split; refresh skips 81."""

from __future__ import annotations

from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]
DUE = json.loads((ROOT / "docs" / "due.json").read_text())
README = (ROOT / "README.md").read_text()
REFRESH = (ROOT / "scripts" / "refresh_due.py").read_text()
APP_JS = (ROOT / "docs" / "app.js").read_text()

BUCKET_KEYS = ("unfunded", "reverting", "waiting", "other")
REQUIRED_TOP = (
    "network",
    "chain",
    "keeper",
    "pulse",
    "rainHub",
    "lastRound",
    "frozen",
    "probedAt",
    "feeMicroAlgos",
    "selector",
    "skipped",
    "unfunded",
    "reverting",
    "waiting",
    "other",
    "onSchedule",
)
ENTRY_KEYS = (
    "id",
    "targetApp",
    "roundsLate",
    "balance",
    "effectiveFee",
    "intervalRounds",
    "nextExecutionRound",
    "note",
)


def test_refresh_due_script_exists_and_skips_81() -> None:
    assert (ROOT / "scripts" / "refresh_due.py").is_file()
    assert "SKIP_IDS" in REFRESH
    assert "81" in REFRESH
    assert "87" in REFRESH
    assert "frozenset({81, 87})" in REFRESH or "{81, 87}" in REFRESH
    assert 'OUT = Path(__file__).resolve().parents[1] / "docs" / "due.json"' in REFRESH
    assert "testnet-api.algonode.cloud" in REFRESH
    assert "No MainNet" in REFRESH or "no MainNet" in REFRESH
    assert "No mnemonic" in REFRESH or "no mnemonic" in REFRESH.lower()
    assert "allow-empty-signatures" in REFRESH
    assert "Never submits" in REFRESH or "never submits" in REFRESH


def test_due_json_schema_and_network() -> None:
    for key in REQUIRED_TOP:
        assert key in DUE, f"missing {key}"
    assert DUE["network"] == "testnet-v1.0"
    assert int(DUE["chain"]) == 81
    assert int(DUE["keeper"]) == 769891898
    assert int(DUE["pulse"]) == 769891902
    assert int(DUE["rainHub"]) == 770130162
    assert int(DUE["lastRound"]) > 0
    assert int(DUE["frozen"]) == 0
    assert int(DUE["feeMicroAlgos"]) == 3000
    assert DUE["selector"] == "5b49cc5c"
    assert isinstance(DUE["probedAt"], str) and DUE["probedAt"].endswith("Z")
    assert isinstance(DUE["onSchedule"], list)
    assert all(isinstance(x, int) for x in DUE["onSchedule"])


def test_due_json_bucket_entries() -> None:
    for bucket in BUCKET_KEYS:
        items = DUE[bucket]
        assert isinstance(items, list)
        for item in items:
            for key in ENTRY_KEYS:
                assert key in item, f"{bucket} missing {key}"
            assert int(item["id"]) > 0
            assert int(item["targetApp"]) > 0
            assert int(item["roundsLate"]) >= 0
            assert int(item["balance"]) >= 0
            assert int(item["effectiveFee"]) > 0
            assert int(item["intervalRounds"]) > 0
            assert int(item["nextExecutionRound"]) > 0


def test_due_json_skips_vigil_81_never_invents_txid() -> None:
    skipped = DUE["skipped"]
    assert isinstance(skipped, list)
    assert any(int(s.get("id") or 0) == 81 for s in skipped)
    blob = json.dumps(DUE)
    # No invented full txids in snapshot notes (simulate quotes strip them).
    assert not re.search(r"\b[A-Z2-7]{52}\b", blob)
    # Never paint LocalNet / MainNet as this board's network.
    assert "localnet" not in blob.lower()
    assert "mainnet" not in blob.lower()
    assert "localhost" not in blob.lower()


def test_due_json_ids_partition_no_81_in_buckets() -> None:
    seen: set[int] = set()
    for bucket in BUCKET_KEYS:
        for item in DUE[bucket]:
            uid = int(item["id"])
            assert uid != 81
            assert uid != 87  # do not poke
            assert uid not in seen
            seen.add(uid)
    for uid in DUE["onSchedule"]:
        assert int(uid) != 81
        assert int(uid) not in seen
        seen.add(int(uid))
    # 81 only in skipped
    assert 81 not in seen
    assert any(int(s["id"]) == 81 for s in DUE["skipped"])


def test_readme_live_proof_matches_due_snapshot() -> None:
    round_ = int(DUE["lastRound"])
    assert f"**{round_}**" in README or f" {round_} " in README or str(round_) in README
    assert "python3 scripts/refresh_due.py" in README
    assert "docs/due.json" in README
    assert "769891898" in README
    assert "frozen=0" in README
    assert "skips 81" in README.lower() or "skip" in README.lower() and "81" in README
    assert "do not poke 87" in README.lower() or "does not poke 87" in README
    assert "TestNet" in README
    assert "MainNet is out of scope" in README or "no MainNet" in README
    assert "Apache-2.0" in README
    # Counts in live-proof bullets track snapshot buckets.
    assert f"**unfunded** {len(DUE['unfunded'])}" in README
    assert f"**reverting** {len(DUE['reverting'])}" in README
    assert f"**waiting** {len(DUE['waiting'])}" in README
    assert f"**other** {len(DUE['other'])}" in README
    assert f"**on schedule** {len(DUE['onSchedule'])}" in README
    assert "**skipped** 1" in README or f"**skipped** {len(DUE['skipped'])}" in README


def test_app_js_loads_due_json_and_skips_81() -> None:
    assert 'fetch("due.json"' in APP_JS or "fetch('due.json'" in APP_JS
    assert "testnet-api.algonode.cloud" in APP_JS
    assert "const SKIP = 81n" in APP_JS or "SKIP = 81" in APP_JS
    assert "allow-empty-signatures" in APP_JS
    assert "INDEXER" not in APP_JS  # algod-only board
    assert "mainnet" not in APP_JS.lower()
    assert "mnemonic" not in APP_JS.lower()
    assert "769891898" in APP_JS


def test_no_localnet_story_forced_onto_pages() -> None:
    # Status board is TestNet overdue split; no deploy.json appId 0 / localnet.json required.
    assert not (ROOT / "docs" / "localnet.json").exists()
    assert not (ROOT / "docs" / "deploy.json").exists()
    assert "localnet" not in APP_JS.lower()
