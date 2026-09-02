#!/usr/bin/env python3
"""Refresh docs/due.json from TestNet algod — same overdue split as docs/app.js.

Read-only: GET status/apps/boxes + unsigned POST /v2/transactions/simulate.
No mnemonic, no MainNet, never submits a transaction. Skips upkeep 81 (Vigil)
and does not poke 87.
"""
from __future__ import annotations

import base64
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ALGOD = "https://testnet-api.algonode.cloud"
KEEPER = 769891898
CHAIN = 81
PULSE = 769891902
RAIN_HUB = 770130162
FEE = 3000
HEAD = 130
SELECTOR = bytes([0x5B, 0x49, 0xCC, 0x5C])
SKIP_IDS = frozenset({81, 87})  # 81 Vigil; never poke 87
UA = {"User-Agent": "arcron-status-page-refresh_due/1.0", "Accept": "application/json"}
OUT = Path(__file__).resolve().parents[1] / "docs" / "due.json"


def http_json(method: str, path: str, body: dict | None = None, timeout: int = 60) -> dict:
    data = None
    headers = dict(UA)
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(ALGOD + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        raw = e.read() if e.fp else b""
        try:
            return json.loads(raw.decode() or "{}")
        except json.JSONDecodeError:
            raise SystemExit(f"{method} {path} HTTP {e.code}: {raw[:200]!r}") from e


def get_json(path: str) -> dict:
    return http_json("GET", path)


def itob(n: int) -> bytes:
    return int(n).to_bytes(8, "big")


def box_name(upkeep_id: int) -> bytes:
    return b"u" + itob(upkeep_id)


def u64(raw: bytes, off: int) -> int:
    return int.from_bytes(raw[off : off + 8], "big")


def u16(raw: bytes, off: int) -> int:
    return int.from_bytes(raw[off : off + 2], "big")


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def quote_fail(msg: str) -> str:
    if not msg:
        return ""
    stripped = msg
    if stripped.startswith("transaction ") and ": " in stripped[:70]:
        # strip leading "transaction <txid>: "
        parts = stripped.split(": ", 1)
        if len(parts) == 2 and len(parts[0]) > 12:
            stripped = parts[1]
    return stripped.split(". Details")[0][:120]


def effective_fee(u: dict, round_: int) -> int:
    base = u["feePerExecution"]
    cap = u["feeCap"]
    if cap <= base or u["nextExecutionRound"] <= u["lastServicedRound"]:
        return base
    interval = u["intervalRounds"] if u["intervalRounds"] > 0 else 1
    lateness = round_ - u["lastServicedRound"] if round_ > u["lastServicedRound"] else 0
    excess = lateness - interval if lateness > interval else 0
    if excess > interval:
        excess = interval
    fee = base + ((cap - base) * excess) // interval
    return base if u["balance"] < fee else fee


def decode_upkeep(upkeep_id: int, raw: bytes) -> dict:
    if len(raw) < HEAD + 2:
        raise ValueError(f"box {upkeep_id} too short ({len(raw)})")
    tail = u16(raw, 40)
    if tail != HEAD:
        raise ValueError(f"box {upkeep_id} tail {tail} != {HEAD}")
    return {
        "id": upkeep_id,
        "targetApp": u64(raw, 32),
        "intervalRounds": u64(raw, 42),
        "nextExecutionRound": u64(raw, 50),
        "feePerExecution": u64(raw, 58),
        "balance": u64(raw, 66),
        "timesExecuted": u64(raw, 74),
        "policy": u64(raw, 82),
        "feeCap": u64(raw, 90),
        "lastServicedRound": u64(raw, 98),
        "feeAsset": u64(raw, 106),
        "assetFee": u64(raw, 114),
        "assetBalance": u64(raw, 122),
    }


def list_boxes() -> list[str]:
    names: list[str] = []
    next_token = ""
    while True:
        q = f"?next={urllib.parse.quote(next_token)}" if next_token else ""
        page = get_json(f"/v2/applications/{KEEPER}/boxes{q}")
        for box in page.get("boxes") or []:
            names.append(box["name"])
        next_token = page.get("next-token") or ""
        if not next_token:
            return names


def classify(can_pay: bool, failure: str) -> str:
    if not can_pay:
        return "UNFUNDED"
    msg = failure or ""
    if "inner tx" in msg and "failed" in msg:
        return "REVERTING"
    if not msg:
        return "WAITING"
    return "OTHER"


def simulate(u: dict, creator: str, params: dict, round_: int) -> str:
    fv = int(params.get("last-round") or round_)
    body = {
        "allow-empty-signatures": True,
        "allow-unnamed-resources": True,
        "txn-groups": [
            {
                "txns": [
                    {
                        "txn": {
                            "type": "appl",
                            "snd": creator,
                            "fee": FEE,
                            "fv": fv,
                            "lv": fv + 1000,
                            "gh": params["genesis-hash"],
                            "gen": params["genesis-id"],
                            "apid": KEEPER,
                            "apan": 0,
                            "apaa": [b64(SELECTOR), b64(itob(u["id"]))],
                            "apbx": [{"n": b64(box_name(u["id"]))}],
                            "apfa": [int(u["targetApp"])],
                        }
                    }
                ]
            }
        ],
    }
    json_resp = http_json("POST", "/v2/transactions/simulate", body=body, timeout=90)
    if "message" in json_resp and "txn-groups" not in json_resp:
        return str(json_resp.get("message") or "simulate failed")
    group = (json_resp.get("txn-groups") or [{}])[0]
    return (group.get("failure-message") or "").replace("\n", " ")


def entry(u: dict) -> dict:
    return {
        "id": int(u["id"]),
        "targetApp": int(u["targetApp"]),
        "roundsLate": int(u["roundsLate"]),
        "balance": int(u["balance"]),
        "effectiveFee": int(u["effFee"]),
        "intervalRounds": int(u["intervalRounds"]),
        "nextExecutionRound": int(u["nextExecutionRound"]),
        "note": u.get("note") or "",
    }


def main() -> int:
    probed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    print("GET /v2/status …", file=sys.stderr)
    try:
        status = get_json("/v2/status")
    except Exception as err:
        print(f"algod status failed: {err}", file=sys.stderr)
        return 1
    round_ = int(status["last-round"])
    print(f"round {round_}", file=sys.stderr)

    app = get_json(f"/v2/applications/{KEEPER}")
    params = get_json("/v2/transactions/params")
    gs: dict = {}
    for item in (app.get("params") or {}).get("global-state") or []:
        key = base64.b64decode(item["key"]).decode("ascii", "replace")
        gs[key] = item.get("value") or {}
    frozen = int((gs.get("frozen") or {}).get("uint") or 0)
    creator = (app.get("params") or {}).get("creator") or ""
    print(f"frozen={frozen} creator={creator}", file=sys.stderr)

    box_names = list_boxes()
    print(f"boxes {len(box_names)}", file=sys.stderr)

    upkeeps: list[dict] = []
    skipped: list[dict] = []
    seen_skip: set[int] = set()
    for name_b64 in box_names:
        name = base64.b64decode(name_b64)
        if len(name) < 9 or name[0] != 0x75:
            continue
        upkeep_id = u64(name, 1)
        if upkeep_id in SKIP_IDS:
            if upkeep_id not in seen_skip:
                seen_skip.add(upkeep_id)
                if upkeep_id == 81:
                    skipped.append(
                        {"id": 81, "reason": "Vigil; CoS does not top up or simulate"}
                    )
                elif upkeep_id == 87:
                    skipped.append({"id": 87, "reason": "do not poke; skipped by refresh_due"})
                print(f"skip {upkeep_id}", file=sys.stderr)
            continue
        box = get_json(
            f"/v2/applications/{KEEPER}/box?name=b64:{urllib.parse.quote(name_b64)}"
        )
        raw = base64.b64decode(box["value"])
        u = decode_upkeep(upkeep_id, raw)
        eff = effective_fee(u, round_)
        late = round_ - u["nextExecutionRound"] if round_ > u["nextExecutionRound"] else 0
        u["effFee"] = eff
        u["canPay"] = u["balance"] >= eff
        u["roundsLate"] = late
        u["overdue"] = late > u["intervalRounds"]
        upkeeps.append(u)

    upkeeps.sort(key=lambda x: x["id"])

    buckets: dict[str, list] = {
        "UNFUNDED": [],
        "REVERTING": [],
        "WAITING": [],
        "OTHER": [],
    }
    on_schedule: list[int] = []
    simmed = 0
    for u in upkeeps:
        if not u["overdue"]:
            on_schedule.append(int(u["id"]))
            continue
        simmed += 1
        print(f"simulate #{u['id']} ({simmed}) …", end=" ", file=sys.stderr, flush=True)
        try:
            failure = simulate(u, creator, params, round_)
        except Exception as err:
            failure = f"simulate unavailable ({err})"
        print((failure or "ok")[:100], file=sys.stderr)
        kind = classify(u["canPay"], failure)
        u["failure"] = failure
        u["kind"] = kind
        if kind == "UNFUNDED":
            u["note"] = quote_fail(failure) or "balance < effective fee"
        elif kind == "REVERTING":
            u["note"] = quote_fail(failure)
        elif kind == "WAITING":
            u["note"] = "would succeed"
        else:
            u["note"] = quote_fail(failure)
        buckets[kind].append(u)

    def map_bucket(kind: str) -> list[dict]:
        out = []
        for u in buckets[kind]:
            e = entry(u)
            if kind in ("REVERTING", "OTHER"):
                e["failure"] = quote_fail(u.get("failure") or "")
            out.append(e)
        return out

    due = {
        "network": "testnet-v1.0",
        "chain": CHAIN,
        "keeper": KEEPER,
        "pulse": PULSE,
        "rainHub": RAIN_HUB,
        "lastRound": round_,
        "frozen": frozen,
        "probedAt": probed_at,
        "feeMicroAlgos": FEE,
        "selector": "5b49cc5c",
        "skipped": skipped,
        "unfunded": map_bucket("UNFUNDED"),
        "reverting": map_bucket("REVERTING"),
        "waiting": map_bucket("WAITING"),
        "other": map_bucket("OTHER"),
        "onSchedule": on_schedule,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(due, indent=2) + "\n", encoding="utf-8")

    print("\n=== SUMMARY ===", file=sys.stderr)
    print(f"lastRound {due['lastRound']}", file=sys.stderr)
    print(
        f"unfunded {len(due['unfunded'])} {[x['id'] for x in due['unfunded']]}",
        file=sys.stderr,
    )
    print(
        f"reverting {len(due['reverting'])} {[x['id'] for x in due['reverting']]}",
        file=sys.stderr,
    )
    print(
        f"waiting {len(due['waiting'])} {[x['id'] for x in due['waiting']]}",
        file=sys.stderr,
    )
    print(f"other {len(due['other'])} {[x['id'] for x in due['other']]}", file=sys.stderr)
    print(f"onSchedule {len(due['onSchedule'])} {due['onSchedule']}", file=sys.stderr)
    print(f"skipped {due['skipped']}", file=sys.stderr)
    print(f"wrote {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
