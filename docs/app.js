/* Algod-only Arcron overdue split. No indexer. No wallet. Unsigned execute. */
(() => {
  const ALGOD = "https://testnet-api.algonode.cloud";
  const KEEPER = 769891898;
  const CHAIN = 81;
  const FEE = 3000;
  const HEAD = 130;
  const SELECTOR = new Uint8Array([0x5b, 0x49, 0xcc, 0x5c]);
  const NAMES = {
    769891898: "keeper",
    769891902: "pulse",
    770130162: "rain",
  };

  const $ = (id) => document.getElementById(id);

  function b64(bytes) {
    let s = "";
    for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
    return btoa(s);
  }

  function b64dec(str) {
    const bin = atob(str);
    const out = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
  }

  function u64(view, off) {
    return view.getBigUint64(off);
  }

  function itob(n) {
    const out = new Uint8Array(8);
    new DataView(out.buffer).setBigUint64(0, BigInt(n));
    return out;
  }

  function boxName(id) {
    const out = new Uint8Array(9);
    out[0] = 0x75;
    out.set(itob(id), 1);
    return out;
  }

  function appName(id) {
    const n = Number(id);
    return NAMES[n] ? `${NAMES[n]} ${n}` : String(n);
  }

  function quoteFail(msg) {
    if (!msg) return "";
    const stripped = msg.replace(/^transaction [A-Z2-7]{52}: /, "");
    return stripped.split(". Details")[0].slice(0, 120);
  }

  function effectiveFee(u, round) {
    const base = u.feePerExecution;
    const cap = u.feeCap;
    if (cap <= base || u.nextExecutionRound <= u.lastServicedRound) return base;
    const interval = u.intervalRounds > 0n ? u.intervalRounds : 1n;
    const lateness = round > u.lastServicedRound ? round - u.lastServicedRound : 0n;
    let excess = lateness > interval ? lateness - interval : 0n;
    if (excess > interval) excess = interval;
    const fee = base + ((cap - base) * excess) / interval;
    return u.balance < fee ? base : fee;
  }

  function decodeUpkeep(id, raw) {
    if (raw.length < HEAD + 2) throw new Error(`box ${id} too short (${raw.length})`);
    const view = new DataView(raw.buffer, raw.byteOffset, raw.byteLength);
    const tail = view.getUint16(40);
    if (tail !== HEAD) throw new Error(`box ${id} tail ${tail} ≠ ${HEAD}`);
    return {
      id,
      targetApp: u64(view, 32),
      intervalRounds: u64(view, 42),
      nextExecutionRound: u64(view, 50),
      feePerExecution: u64(view, 58),
      balance: u64(view, 66),
      timesExecuted: u64(view, 74),
      policy: u64(view, 82),
      feeCap: u64(view, 90),
      lastServicedRound: u64(view, 98),
      feeAsset: u64(view, 106),
      assetFee: u64(view, 114),
      assetBalance: u64(view, 122),
    };
  }

  async function getJson(path) {
    const res = await fetch(ALGOD + path);
    if (!res.ok) throw new Error(`${path} ${res.status}`);
    return res.json();
  }

  async function listBoxes() {
    const names = [];
    let next = "";
    for (;;) {
      const q = next ? `?next=${encodeURIComponent(next)}` : "";
      const page = await getJson(`/v2/applications/${KEEPER}/boxes${q}`);
      for (const box of page.boxes || []) names.push(box.name);
      next = page["next-token"] || "";
      if (!next) return names;
    }
  }

  function classify(u, failure) {
    if (!u.canPay) return "UNFUNDED";
    const msg = failure || "";
    if (msg.includes("inner tx") && msg.includes("failed")) return "REVERTING";
    if (!msg) return "WAITING";
    return "OTHER";
  }

  function rowHtml(u) {
    const late = u.roundsLate;
    const note = u.note ? `<span class="note">${escapeHtml(u.note)}</span>` : "";
    return `<li>
      <span class="id">#${u.id}</span>
      target ${escapeHtml(appName(u.targetApp))}
      <span class="late">late ${late.toLocaleString()} r · escrow ${u.balance} / fee ${u.effFee}</span>
      ${note}
    </li>`;
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  async function simulate(u, creator, params, round) {
    const fv = Number(params["last-round"] || round);
    const body = {
      "allow-empty-signatures": true,
      "allow-unnamed-resources": true,
      "txn-groups": [
        {
          txns: [
            {
              txn: {
                type: "appl",
                snd: creator,
                fee: FEE,
                fv,
                lv: fv + 1000,
                gh: params["genesis-hash"],
                gen: params["genesis-id"],
                apid: KEEPER,
                apan: 0,
                apaa: [b64(SELECTOR), b64(itob(u.id))],
                apbx: [{ n: b64(boxName(u.id)) }],
                apfa: [Number(u.targetApp)],
              },
            },
          ],
        },
      ],
    };
    const res = await fetch(ALGOD + "/v2/transactions/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const json = await res.json();
    if (!res.ok) {
      return json.message || `simulate HTTP ${res.status}`;
    }
    const group = (json["txn-groups"] || [])[0] || {};
    return (group["failure-message"] || "").replace(/\n/g, " ");
  }

  async function probe() {
    const btn = $("probe");
    btn.disabled = true;
    $("status").textContent = "GET /v2/status …";
    try {
      const status = await getJson("/v2/status");
      const round = BigInt(status["last-round"]);
      $("last-round").textContent = String(round);
      $("status").textContent = `GET /v2/applications/${KEEPER} …`;

      const [app, params] = await Promise.all([
        getJson(`/v2/applications/${KEEPER}`),
        getJson("/v2/transactions/params"),
      ]);
      const gs = {};
      for (const entry of app.params["global-state"] || []) {
        gs[atob(entry.key)] = entry.value;
      }
      const frozen = Number((gs.frozen && gs.frozen.uint) || 0);
      $("frozen").textContent = String(frozen);
      const creator = app.params.creator;
      $("sender").textContent = creator;
      $("keeper").textContent = `keeper ${KEEPER}`;

      $("status").textContent = "GET boxes …";
      const boxNames = await listBoxes();
      const upkeeps = [];
      for (const nameB64 of boxNames) {
        const name = b64dec(nameB64);
        if (name.length < 9 || name[0] !== 0x75) continue;
        const id = new DataView(name.buffer, name.byteOffset, name.byteLength).getBigUint64(1);
        const box = await getJson(
          `/v2/applications/${KEEPER}/box?name=b64:${encodeURIComponent(nameB64)}`
        );
        const raw = b64dec(box.value);
        const u = decodeUpkeep(id, raw);
        const eff = effectiveFee(u, round);
        const late = round > u.nextExecutionRound ? round - u.nextExecutionRound : 0n;
        u.effFee = eff;
        u.canPay = u.balance >= eff;
        u.roundsLate = late;
        u.overdue = late > u.intervalRounds;
        upkeeps.push(u);
      }
      upkeeps.sort((a, b) => (a.id < b.id ? -1 : 1));

      const buckets = { UNFUNDED: [], REVERTING: [], WAITING: [], OTHER: [] };
      const ok = [];
      let simmed = 0;
      for (const u of upkeeps) {
        if (!u.overdue) {
          ok.push(u.id);
          continue;
        }
        $("status").textContent = `simulate execute #${u.id} (${++simmed}) …`;
        let failure = "";
        try {
          failure = await simulate(u, creator, params, round);
        } catch (err) {
          failure = `simulate unavailable (${err && err.message ? err.message : err})`;
        }
        u.failure = failure;
        u.kind = classify(u, failure);
        if (u.kind === "UNFUNDED") u.note = quoteFail(failure) || "balance < effective fee";
        else if (u.kind === "REVERTING") u.note = quoteFail(failure);
        else if (u.kind === "WAITING") u.note = "would succeed";
        else u.note = quoteFail(failure);
        buckets[u.kind].push(u);
      }

      const paint = (kind, elList, elN) => {
        elN.textContent = String(buckets[kind].length);
        elList.innerHTML = buckets[kind].map(rowHtml).join("") || "<li class='note'>none</li>";
      };
      paint("UNFUNDED", $("list-unfunded"), $("n-unfunded"));
      paint("REVERTING", $("list-reverting"), $("n-reverting"));
      paint("WAITING", $("list-waiting"), $("n-waiting"));
      $("n-other").textContent = String(buckets.OTHER.length);
      $("list-other").innerHTML = buckets.OTHER.map(rowHtml).join("");
      $("sec-other").hidden = buckets.OTHER.length === 0;
      $("n-ok").textContent = String(ok.length);
      $("list-ok").textContent = ok.map((id) => `#${id}`).join("  ") || "none";

      $("status").textContent =
        `round ${round} · chain ${CHAIN} · frozen=${frozen} · overdue ${simmed} simulated · unsigned execute`;
    } catch (err) {
      $("status").textContent = `probe failed: ${err && err.message ? err.message : err}`;
    } finally {
      btn.disabled = false;
    }
  }

  $("probe").addEventListener("click", probe);
  probe();
})();
