# arcron-status-page

Live TestNet board that asks algod why an overdue Arcron upkeep is overdue: unfunded or reverting.

Read-only GitHub Pages. No wallet, no indexer, no backend. Keeper app [`769891898`](https://testnet.explorer.perawallet.app/application/769891898) is live and **not frozen** (`frozen=0`). Arcron is unaudited. This is a corvid-agent first-party demo, not the Arcron console.

Live: <https://corvid-agent.github.io/arcron-status-page/>

## Live proof

At TestNet last-round **66924998** (probed 2026-09-02T22:04:18.942Z UTC / 2026-09-02 16:04 America/Denver), unsigned `execute` simulate (allow-empty-signatures) against app `769891898` split overdue upkeeps as:

- **unfunded** 12 — ids 98–109 (escrow cannot pay effective fee; balance < fee; simulate quote `logic eval error: assert failed pc=1181`)
- **reverting** 0
- **waiting** 0
- **other** 2 — ids 118, 120: 118 (account LOYG5I5UHSW6RL7OQ4X6IGS2NTFGO5ZLWEW2LLQKJBI6XVTZSUFMAAC3WY bal); 120 (logic eval error: group fee 0.0A too small (needs 1mA more) []transact)
- **on schedule** 21 — ids 19–22, 82, 84–86, 89, 92–94, 110–117, 119
- **skipped** 1 — id 81 (Vigil; CoS does not top up or simulate)

Snapshot also ships as [`docs/due.json`](docs/due.json) so Pages paints immediately, then the live algod probe overwrites. Refresh offline with `python3 scripts/refresh_due.py` (stdlib urllib; same overdue split as `docs/app.js`; skips 81, does not poke 87). Keeper `769891898` is **not frozen** (`frozen=0`). Algod-only, unsigned simulate, no indexer, no wallet.

Public names only: keeper `769891898`, pulse `769891902`, rain hub `770130162`. Rain hub `770130162` is pre-#213 (missing enter-while-locked `prize_locked==0` assert) and immutable; boards listen only. Chain id `81` stays a number. Everything else is numeric.

## How to run

Open the Pages site. It talks to `https://testnet-api.algonode.cloud` from the browser:

1. `GET /v2/status` for last-round
2. `GET /v2/applications/769891898` and `GET /v2/applications/769891898/boxes`
3. `GET /v2/applications/769891898/box?name=b64:…` for each `u||itob(id)` box
4. For each overdue upkeep, `POST /v2/transactions/simulate` of an unsigned `execute(uint64)uint64` (selector `5b49cc5c`) with `allow-empty-signatures` and `allow-unnamed-resources`

Overdue here is `rounds_late > interval_rounds` (more than one whole cycle), matching `registry_health.py`. UNFUNDED is box math (`balance >= effective_fee`), not `pc=1181`.

Local: serve `docs/` as static files. No build server, no env file, no mnemonic.

To refresh the committed snapshot from this checkout:

```bash
python3 scripts/refresh_due.py
```

Writes `docs/due.json` only. TestNet reads + unsigned simulate; never submits.


## Measured cost

Zero to view. Reads public algod. Simulate is unsigned and does not submit. No escrow, no opt-in, no wallet prompt.

## What is broken

- Programs are still replaceable (`frozen=0`).
- Arcron is unaudited.
- TestNet only. MainNet is out of scope.
- Simulate uses a public stand-in sender (the app creator). It is not a live keeper discovered from chain, because that discovery in `registry_health.py` uses the indexer, which this page refuses.
- A 3000 µALGO outer fee matches `registry_health.py` and is short for a target that itself pays an inner transaction (upkeep 82 / pulse).
- Assert strings are not on chain. Unfunded is decided from box math (`balance >= effective_fee`), not from `pc=1181`.

## Honesty

This is not arrivals. Arrivals paints ON TIME / DELAYED / GROUNDED from indexer boxes without simulate, so a funded reverting target looks DELAYED. This page exists to tell those apart.

Do not treat a private roster as source of truth. Chain state is. No mnemonics, no keys, no MainNet.

Apache-2.0. Unaudited. First-party demo.
