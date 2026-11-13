// Player shot charts for the multi-match report.
// Clicking a player name in "Offense Shot Profile By Player" opens that player's
// shooting chart; clicking a name in "Player Defense Overview" opens the chart of
// shots that player defended. Reads the report's global `data` object.
(function () {
  "use strict";

  const TABLES = { offPlayersTable: "offense", playerDefenseTable: "defense" };
  const W = 500, H = 470, BX = 250, BY = 52, R = 241, CORNER_X = 30;
  const YC = BY + Math.sqrt(R * R - (BX - CORNER_X) ** 2);
  const RAD = Math.PI / 180;
  const IN_ARC = `M${CORNER_X},0 L${CORNER_X},${YC.toFixed(1)} A${R},${R} 0 0 0 ${W - CORNER_X},${YC.toFixed(1)} L${W - CORNER_X},0 Z`;

  // BuzzerBeater shot codes: 10x threes, 20x two-point jumpers, 4xx close shots.
  const ZONE_OF_CODE = {
    "101": "t3", "102": "w3", "103": "c3", "104": "l3", "105": "h3",
    "201": "e2", "202": "w2", "203": "b2", "204": "t2"
  };
  // Same grouping as the report's getShotRange(); non-numeric codes are unknown.
  function rangeOf(code) {
    const value = String(code);
    if (!/^\d+$/.test(value)) return null;
    return value.startsWith("10") ? "three" : value.startsWith("20") ? "mid" : "inside";
  }
  const zoneOf = code => ZONE_OF_CODE[String(code)] || (rangeOf(code) === "inside" ? "rim" : null);

  function pt(r, a) {
    return [(BX + r * Math.sin(a * RAD)).toFixed(1), (BY + r * Math.cos(a * RAD)).toFixed(1)];
  }
  // Annular sector; angle 0 points toward halfcourt, +/-90 toward the sidelines.
  function sector(r0, r1, a0, a1) {
    const large = a1 - a0 > 180 ? 1 : 0;
    const [x1, y1] = pt(r1, a0), [x2, y2] = pt(r1, a1);
    if (!r0) return `M${BX},${BY} L${x1},${y1} A${r1},${r1} 0 ${large} 0 ${x2},${y2} Z`;
    const [x3, y3] = pt(r0, a1), [x4, y4] = pt(r0, a0);
    return `M${x1},${y1} A${r1},${r1} 0 ${large} 0 ${x2},${y2} L${x3},${y3} A${r0},${r0} 0 ${large} 1 ${x4},${y4} Z`;
  }
  const mirrored = (r0, r1, a0, a1) => [sector(r0, r1, a0, a1), sector(r0, r1, -a1, -a0)];
  const PAINT = "M180,0 H320 V190 H180 Z";

  // Typical FG% per zone, used only to decide how dark a zone is shaded.
  const ZONES = [
    { key: "w3", label: "3PT wing", clip: "out", paths: mirrored(R, 700, 22, 110), at: [62, 250], avg: 0.33, both: true },
    { key: "t3", label: "3PT top key", clip: "out", paths: [sector(R, 330, -22, 22)], at: [250, 340], avg: 0.33 },
    { key: "l3", label: "3PT long", clip: "out", paths: [sector(330, 400, -22, 22)], at: [250, 412], avg: 0.2 },
    { key: "h3", label: "3PT halfcourt", paths: ["M0,440 H500 V470 H0 Z"], at: [250, 457], avg: 0.05, small: true },
    { key: "c3", label: "3PT corner", paths: [`M0,0 H${CORNER_X} V${YC.toFixed(1)} H0 Z`, `M${W - CORNER_X},0 H${W} V${YC.toFixed(1)} H${W - CORNER_X} Z`], at: [15, 85], avg: 0.36, both: true, rotate: true },
    { key: "b2", label: "2PT baseline", clip: "in", paths: mirrored(0, R, 68, 180), at: [100, 100], avg: 0.4, both: true },
    { key: "w2", label: "2PT wing", clip: "in", paths: mirrored(0, R, 40, 68), at: [112, 158], avg: 0.4, both: true },
    { key: "e2", label: "2PT elbow", clip: "in", paths: mirrored(0, R, 18, 40), at: [160, 240], avg: 0.4, both: true },
    { key: "t2", label: "2PT top key", clip: "in", paths: [sector(0, R, -18, 18)], at: [250, 252], avg: 0.4 },
    { key: "rim", label: "Close (dunks, layups, post, tip-ins)", paths: [PAINT], at: [250, 140], avg: 0.6 }
  ];
  const RAMP = [["#f7ece6", "#4a1b0c"], ["#f0cdb9", "#4a1b0c"], ["#e3a07f", "#4a1b0c"], ["#c8693f", "#fff7f2"], ["#933b1c", "#fff7f2"]];

  function shade(made, att, avg) {
    if (!att) return null;
    const d = made / att - avg;
    return RAMP[d < -0.15 ? 0 : d < -0.05 ? 1 : d < 0.05 ? 2 : d < 0.15 ? 3 : 4];
  }
  // Share of the player's placed shots that came from a zone.
  function volumeShade(att, total) {
    if (!att || !total) return null;
    const s = att / total;
    return RAMP[s < 0.04 ? 0 : s < 0.08 ? 1 : s < 0.14 ? 2 : s < 0.22 ? 3 : 4];
  }
  const MODES = {
    volume: { button: "Most shots", colder: "Fewer shots", hotter: "More shots" },
    efficiency: { button: "Hot / cold", colder: "Colder", hotter: "Hotter" }
  };
  let colorMode = "volume";
  const esc = v => String(v ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const pct = (m, a) => a ? (100 * m / a).toFixed(1) + "%" : "–";

  // ---- data -------------------------------------------------------------

  function emptyTotals() {
    const zones = {};
    ZONES.forEach(z => { zones[z.key] = { m: 0, a: 0 }; });
    return { zones, ranges: { inside: { m: 0, a: 0 }, mid: { m: 0, a: 0 }, three: { m: 0, a: 0 } }, unplaced: 0, unknown: 0 };
  }
  function addShot(t, code, made, att) {
    const zone = zoneOf(code), range = rangeOf(code);
    if (!range) { t.unknown += att; return; }
    t.ranges[range].a += att; t.ranges[range].m += made;
    if (zone) { t.zones[zone].a += att; t.zones[zone].m += made; } else t.unplaced += att;
  }

  function isMade(ev) {
    if (typeof ev.made === "boolean") return ev.made;
    return ["1", "2", "5"].includes(String(ev.shot_result));
  }

  // Old-site single-match report: both tables are built in the page from
  // data.events, using 1-based player slots per side (0 = home, 1 = away).
  const isSingleMatch = () => !!(data.teamHome && data.teamAway && Array.isArray(data.events));
  function singleMatchPlayer(player) {
    const teams = [data.teamHome, data.teamAway];
    const byTeam = teams.findIndex(t => t.name === player.team);
    for (const side of byTeam >= 0 ? [byTeam] : [0, 1]) {
      const idx = (teams[side].players || []).findIndex(p => p.name === player.name);
      if (idx >= 0) return { side, idx, count: teams[side].players.length };
    }
    return null;
  }
  function slotIndex(raw, count) {
    const n = Number(raw);
    return Number.isFinite(n) && n >= 1 && n <= count ? n - 1 : null;
  }
  function singleMatchShots(player, role) {
    const p = singleMatchPlayer(player);
    if (!p) return null;
    const sideKey = role === "offense" ? "attacking_team" : "defending_team";
    const slotKey = role === "offense" ? "attacker" : "defender";
    return data.events.filter(ev => ev.event_type === "shot" && Number(ev[sideKey]) === p.side &&
      slotIndex(ev[slotKey], p.count) === p.idx && String(ev.shot_type));
  }

  function offenseTotals(player) {
    const t = emptyTotals();
    if (isSingleMatch()) {
      const shots = singleMatchShots(player, "offense");
      if (!shots) return null;
      shots.forEach(ev => addShot(t, ev.shot_type, isMade(ev) ? 1 : 0, 1));
      return t;
    }
    const row = ((data.offense || {}).players || []).find(r => r.name === player.name);
    if (!row) return null;
    Object.entries(row.counts || {}).forEach(([code, cell]) => { if (cell && cell.a) addShot(t, code, cell.m || 0, cell.a); });
    return t;
  }

  // Defense counts stops (defended shots the opponent missed), matching the
  // success-rate figures in the Player Defense Overview table.
  function defenseTotals(player) {
    const t = emptyTotals();
    t.defense = true;
    if (isSingleMatch()) {
      const shots = singleMatchShots(player, "defense");
      if (!shots) return null;
      shots.forEach(ev => addShot(t, ev.shot_type, isMade(ev) ? 0 : 1, 1));
      return t;
    }
    ((data.defended_shots || {}).events || []).forEach(ev => {
      if (ev.defender !== player.name || ev.attempt === false) return;
      addShot(t, ev.shot_type, isMade(ev) ? 0 : 1, 1);
    });
    const row = (data.defense || []).find(r => r.name === player.name);
    t.tableTotal = row && row.defendedTotal ? row.defendedTotal.a : null;
    return t;
  }

  // ---- rendering --------------------------------------------------------

  function courtSvg(t) {
    let zones = "", labels = "";
    const placed = ZONES.reduce((sum, z) => sum + t.zones[z.key].a, 0);
    ZONES.forEach(z => {
      const { m, a } = t.zones[z.key];
      const c = colorMode === "volume" ? volumeShade(a, placed) : shade(m, a, t.defense ? 1 - z.avg : z.avg);
      const share = placed ? Math.round(100 * a / placed) + "%" : "–";
      const detail = t.defense ? `${m}/${a} stopped · ${pct(m, a)} success` : `${m}/${a} · FG ${pct(m, a)}`;
      const tip = `${z.label}${z.both ? " (both sides)" : ""}: ${a ? `${detail} · ${share} of shots` : "no attempts"}`;
      zones += `<g${z.clip ? ` clip-path="url(#psc-${z.clip})"` : ""}><title>${esc(tip)}</title>` +
        z.paths.map(d => `<path d="${d}" fill="${c ? c[0] : "#fbf8f5"}" stroke="#933b1c" stroke-opacity="0.3"/>`).join("") + "</g>";
      const [x, y] = z.at, fill = c ? c[1] : "#8a7d75";
      if (z.small || z.rotate || !a) {
        labels += `<text x="${x}" y="${y}" class="psc-num${z.small ? " small" : ""}" fill="${fill}"` +
          `${z.rotate ? ` transform="rotate(-90 ${x} ${y})"` : ""}>${a ? `${m}/${a}` : "–"}</text>`;
      } else {
        labels += `<text x="${x}" y="${y - 9}" class="psc-num" fill="${fill}">${m}/${a}</text>` +
          `<text x="${x}" y="${y + 14}" class="psc-sub-num" fill="${fill}">${share} · ${Math.round(100 * m / a)}%</text>`;
      }
    });
    return `<svg viewBox="0 0 ${W} ${H}" class="psc-court" role="img" aria-label="Half-court shot chart by zone">
      <defs><clipPath id="psc-in"><path d="${IN_ARC}"/></clipPath>
      <clipPath id="psc-out"><path clip-rule="evenodd" d="M0,0 H${W} V${H} H0 Z ${IN_ARC}"/></clipPath></defs>
      ${zones}
      <g class="psc-lines"><rect x="0.75" y="0.75" width="${W - 1.5}" height="${H - 1.5}"/>
      <path d="M${CORNER_X},0 L${CORNER_X},${YC.toFixed(1)} A${R},${R} 0 0 0 ${W - CORNER_X},${YC.toFixed(1)} L${W - CORNER_X},0"/>
      <rect x="180" y="0" width="140" height="190"/><circle cx="${BX}" cy="${BY}" r="9"/><line x1="222" y1="36" x2="278" y2="36"/></g>
      ${labels}</svg>`;
  }

  function rangeTable(t) {
    const total = t.ranges.inside.a + t.ranges.mid.a + t.ranges.three.a;
    const rows = [["Inside", "inside", 2], ["Mid-range", "mid", 2], ["Three-point", "three", 3]].map(([label, key, pts]) => {
      const { m, a } = t.ranges[key], scored = t.defense ? a - m : m;
      return `<tr><td>${label}</td><td>${m}–${a}</td><td>${total ? (100 * a / total).toFixed(1) + "%" : "–"}</td>` +
        `<td>${pct(m, a)}</td><td class="psc-strong">${a ? (pts * scored / a).toFixed(2) : "–"}</td></tr>`;
    }).join("");
    const head = t.defense ? ["Stops", "Share", "Success", "Opp pts/shot"] : ["FG", "Share", "FG%", "Pts/shot"];
    return `<table class="psc-table"><thead><tr><th>Zone</th>${head.map(h => `<th>${h}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table>`;
  }

  function sums(t) {
    const r = t.ranges, a = r.inside.a + r.mid.a + r.three.a, m = r.inside.m + r.mid.m + r.three.m;
    return { a, m, three: r.three.m };
  }

  function chartBody(kind, player) {
    const t = kind === "offense" ? offenseTotals(player) : defenseTotals(player);
    if (!t) return { title: "Shooting", headline: "", body: `<p class="psc-empty">No shooting data for this player.</p>` };
    const s = sums(t);
    let headline, notes = [];
    if (kind === "offense") {
      headline = s.a ? `FG% ${pct(s.m, s.a).replace("%", "")} · eFG% ${(100 * (s.m + 0.5 * s.three) / s.a).toFixed(1)}` : "";
    } else {
      headline = s.a ? `Success ${s.m}/${s.a} ${pct(s.m, s.a)} · Opp FG% ${pct(s.a - s.m, s.a).replace("%", "")}` : "";
      if (t.tableTotal != null && t.tableTotal !== s.a) {
        notes.push(`The chart uses ${s.a} logged defended shots with a shot type; the table's total of ${t.tableTotal} also counts saved totals without one.`);
      }
    }
    if (t.unplaced) notes.push(`${t.unplaced} shot${t.unplaced === 1 ? "" : "s"} had no specific zone; they count in the table below but not on the court.`);
    if (t.unknown) notes.push(`${t.unknown} shot${t.unknown === 1 ? " has" : "s have"} an unknown shot type and ${t.unknown === 1 ? "isn't" : "aren't"} included here.`);
    if (!s.a) {
      return { headline: "", body: `<p class="psc-empty">${kind === "offense" ? "No field-goal attempts" : "No logged defended shots"} for this player in ${isSingleMatch() ? "this match" : "the selected matches"}.</p>` };
    }
    const mode = MODES[colorMode];
    const meaning = colorMode === "volume"
      ? `Darker = more of ${kind === "offense" ? "the player's shots" : "the shots they defended"} came from that zone`
      : `Darker = ${kind === "offense" ? "shot better" : "stopped more shots"} than usual for that zone`;
    const reading = kind === "offense" ? "made/attempted, then its share of shots · FG%" : "stops/defended, then its share of shots · success rate";
    const body = `${courtSvg(t)}
      <div class="psc-legend"><span>${mode.colder}</span>${RAMP.map(c => `<i style="background:${c[0]}"></i>`).join("")}<span>${mode.hotter}</span>
      <span class="psc-legend-note">${meaning}. Each zone shows ${reading}. Left and right share one number: BuzzerBeater doesn't record the side.</span></div>
      ${rangeTable(t)}
      ${notes.map(n => `<p class="psc-note">${esc(n)}</p>`).join("")}`;
    return { headline, body };
  }

  // ---- modal ------------------------------------------------------------

  let modal, lastFocus;
  function ensureModal() {
    if (modal) return modal;
    modal = document.createElement("div");
    modal.className = "psc-backdrop";
    modal.hidden = true;
    modal.innerHTML = `<div class="psc-modal" role="dialog" aria-modal="true" aria-labelledby="psc-title">
      <div class="psc-head"><div><div id="psc-title" class="psc-title"></div><div class="psc-sub"></div></div>
      <button type="button" class="psc-close" aria-label="Close shot chart">✕</button></div>
      <div class="psc-kicker"><span class="psc-kind"></span><span class="psc-headline"></span></div>
      <div class="psc-modes" role="group" aria-label="Shade zones by">${Object.entries(MODES).map(([key, m]) =>
        `<button type="button" class="ghost" data-mode="${key}">${m.button}</button>`).join("")}</div>
      <div class="psc-body"></div></div>`;
    document.body.appendChild(modal);
    modal.querySelectorAll(".psc-modes button").forEach(button => button.addEventListener("click", () => {
      colorMode = button.dataset.mode;
      if (current) render(current.kind, current.player);
    }));
    modal.addEventListener("click", e => { if (e.target === modal) close(); });
    modal.querySelector(".psc-close").addEventListener("click", close);
    document.addEventListener("keydown", e => { if (e.key === "Escape" && !modal.hidden) close(); });
    return modal;
  }
  let current = null;
  function subtitle(player) {
    if (isSingleMatch()) {
      const home = data.teamHome.name, away = data.teamAway.name;
      if (player.team === home) return `${home} · vs ${away}`;
      if (player.team === away) return `${away} · vs ${home}`;
      return `${home} vs ${away}`;
    }
    const games = data.used_matches || (data.matches || []).length;
    return `${games ? `${games} game${games === 1 ? "" : "s"} · ` : ""}all selected matches`;
  }
  function render(kind, player) {
    const m = ensureModal(), { headline, body } = chartBody(kind, player);
    current = { kind, player };
    m.querySelector(".psc-title").textContent = player.name;
    m.querySelector(".psc-sub").textContent = subtitle(player);
    m.querySelector(".psc-kind").textContent = kind === "offense" ? "Shooting" : "Shots defended";
    m.querySelector(".psc-kind").dataset.kind = kind;
    m.querySelector(".psc-headline").textContent = headline;
    m.querySelector(".psc-body").innerHTML = body;
    m.querySelectorAll(".psc-modes button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.mode === colorMode)));
  }
  function open(kind, player) {
    const m = ensureModal();
    render(kind, player);
    lastFocus = document.activeElement;
    m.hidden = false;
    document.body.classList.add("psc-open");
    m.querySelector(".psc-close").focus();
  }
  function close() {
    if (!modal) return;
    modal.hidden = true;
    document.body.classList.remove("psc-open");
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }

  // ---- table wiring -----------------------------------------------------

  function nameCell(target, table) {
    const cell = target.closest("td");
    if (!cell || cell.cellIndex !== 0 || cell.classList.contains("empty") || !table.tBodies[0] || !table.tBodies[0].contains(cell)) return null;
    return cell;
  }
  function decorate(table, kind) {
    table.querySelectorAll("tbody tr > td:first-child:not(.empty)").forEach(cell => {
      if (cell.dataset.pscReady) return;
      cell.dataset.pscReady = "1";
      cell.classList.add("psc-player");
      cell.tabIndex = 0;
      cell.setAttribute("role", "button");
      cell.title = kind === "offense" ? "Show shot chart" : "Show defended shot chart";
    });
  }
  function wire(id, kind) {
    const table = document.getElementById(id);
    if (!table) return;
    // The name is the cell's first text; single-match rows may append badges
    // (DEF+, FG-) after it and carry the team in the second column.
    const activate = cell => {
      const first = [...cell.childNodes].find(n => n.nodeType === Node.TEXT_NODE && n.textContent.trim());
      const name = (first ? first.textContent : cell.textContent).trim();
      const team = isSingleMatch() && cell.nextElementSibling ? cell.nextElementSibling.textContent.trim() : null;
      open(kind, { name, team });
    };
    table.addEventListener("click", e => { const cell = nameCell(e.target, table); if (cell) activate(cell); });
    table.addEventListener("keydown", e => {
      if (e.key !== "Enter" && e.key !== " ") return;
      const cell = nameCell(e.target, table);
      if (cell) { e.preventDefault(); activate(cell); }
    });
    decorate(table, kind);
    new MutationObserver(() => decorate(table, kind)).observe(table, { childList: true, subtree: true });
  }

  function init() {
    if (typeof data === "undefined") return;
    Object.entries(TABLES).forEach(([id, kind]) => wire(id, kind));
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
