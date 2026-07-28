"""U21 / NT weekly-minutes analyzers (ported from bb_fantasy /rosters + /nt-analyzer)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any

from flask import Blueprint, jsonify, render_template_string, request

from bbapi import BBApi
from bb_site import BBSiteClient, NATIONAL_TEAM_LEVELS, GameLogEntry
from minutes_agg import aggregate_game_logs, current_week_for_season, overview_for_games
from u21_training import age_for_season, get_game_week, is_counting_game


minutes_bp = Blueprint("minutes_analyzer", __name__)

LOCAL_NATIONAL_OPTIONS_PATH = Path(__file__).with_name("national_options.json")
DEFAULT_CURRENT_SEASON = int(os.environ.get("CURRENT_SEASON", "72"))
U21_MINUTES_MIN_SEASON = int(os.environ.get("U21_MINUTES_MIN_SEASON", "60"))
POSITION_ORDER = ["PG", "SG", "SF", "PF", "C"]

ANALYZER_HTML = r"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{{ title }}</title>
  <style>
    :root {
      --bg: #f4f1ea;
      --card: #fffdf8;
      --ink: #1f1a17;
      --muted: #6b635c;
      --line: #d9d0c4;
      --accent: #1f6f5b;
      --accent-soft: #d7efe7;
      --warn: #fff4d6;
      --danger: #fde8e8;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Avenir Next", "Segoe UI", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, #efe4d4, transparent 40%),
        linear-gradient(180deg, #f7f3ec, #efe8dc);
      min-height: 100vh;
    }
    .wrap { max-width: 1100px; margin: 0 auto; padding: 24px 16px 64px; }
    .topnav { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 18px; font-size: 14px; }
    .topnav a { color: var(--accent); text-decoration: none; font-weight: 600; }
    h1 { margin: 0 0 8px; font-size: 28px; }
    .lead { color: var(--muted); margin: 0 0 20px; }
    .card {
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 16px;
      margin-bottom: 16px;
      box-shadow: 0 10px 30px rgba(40, 28, 12, 0.05);
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
    }
    label { display: block; font-size: 13px; font-weight: 600; margin-bottom: 4px; }
    input, select, button {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 10px 12px;
      font: inherit;
      background: white;
    }
    button {
      background: var(--accent);
      color: white;
      border: none;
      font-weight: 700;
      cursor: pointer;
    }
    button.ghost { background: white; color: var(--ink); border: 1px solid var(--line); }
    button:disabled { opacity: 0.55; cursor: wait; }
    .hint, .status { color: var(--muted); font-size: 13px; margin-top: 8px; }
    .err { background: var(--danger); border: 1px solid #f3b4b4; padding: 10px 12px; border-radius: 10px; margin-top: 10px; }
    .ok { background: var(--accent-soft); border: 1px solid #9fd4c2; padding: 10px 12px; border-radius: 10px; margin-top: 10px; }
    .suggestions {
      border: 1px solid var(--line);
      border-radius: 10px;
      background: white;
      margin-top: 6px;
      overflow: hidden;
    }
    .suggestions button {
      display: block;
      width: 100%;
      text-align: left;
      background: white;
      color: var(--ink);
      border: none;
      border-bottom: 1px solid var(--line);
      border-radius: 0;
      font-weight: 500;
    }
    .suggestions button:last-child { border-bottom: none; }
    .suggestions span.meta { color: var(--muted); font-size: 12px; margin-left: 8px; }
    table { width: 100%; border-collapse: collapse; font-size: 12px; }
    th, td { border: 1px solid var(--line); padding: 8px; vertical-align: middle; }
    th { background: #f3ece2; position: sticky; top: 0; }
    th button {
      width: auto;
      background: transparent;
      color: inherit;
      border: none;
      padding: 0;
      font-weight: 700;
      display: inline-flex;
      gap: 4px;
      align-items: center;
    }
    tr.clickable { cursor: pointer; }
    tr.clickable:hover, tr.selected { background: #f7fbf9; }
    .minute-hi { background: #dcfce7; font-weight: 700; }
    .minute-mid { background: #fef9c3; font-weight: 700; }
    .minute-lo { background: #ffedd5; font-weight: 700; }
    .injury {
      display: inline-block;
      margin-left: 6px;
      background: #fee2e2;
      color: #b91c1c;
      border-radius: 6px;
      padding: 2px 6px;
      font-size: 10px;
      font-weight: 700;
    }
    .chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
    .chips button {
      width: auto;
      background: white;
      color: var(--ink);
      border: 1px solid var(--line);
      font-weight: 600;
    }
    .chips button.active { background: var(--accent-soft); border-color: var(--accent); color: var(--accent); }
    .player-head { display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap; align-items: start; }
    .meta-row { display: flex; flex-wrap: wrap; gap: 14px; margin-top: 8px; }
    .meta-row div { min-width: 70px; }
    .meta-row span { display: block; color: var(--muted); font-size: 11px; }
    .season-block { border-top: 1px solid var(--line); margin-top: 18px; padding-top: 14px; }
    .bars { display: grid; gap: 8px; }
    .bar-row { display: grid; grid-template-columns: 32px 1fr 56px; gap: 8px; align-items: center; }
    .bar-track { background: #eee7dc; border-radius: 999px; height: 8px; overflow: hidden; }
    .bar-fill { height: 100%; background: var(--accent); }
    .week-chart { display: flex; align-items: end; gap: 6px; min-height: 160px; overflow-x: auto; padding-bottom: 4px; }
    .week-col { width: 34px; flex: 0 0 34px; display: flex; flex-direction: column; justify-content: end; align-items: center; }
    .week-stack { width: 100%; display: flex; flex-direction: column-reverse; border-radius: 6px 6px 0 0; overflow: hidden; min-height: 2px; }
    .week-seg { width: 100%; }
    .week-label { margin-top: 4px; font-size: 10px; color: var(--muted); }
    a.bb { color: var(--accent); font-weight: 700; text-decoration: none; }
    .table-wrap { overflow-x: auto; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="topnav">
      <a href="/">Box Score Tool</a>
      <a href="/u21-minutes">U21 Minutes</a>
      <a href="/nt-minutes">NT Minutes</a>
      <a href="/player-minutes">Player Analyzer</a>
      <a href="/u21-tracker">U21 Tracker</a>
    </div>
    <h1>{{ title }}</h1>
    <p class="lead">{{ subtitle }}</p>

    <div class="card">
      <div class="grid">
        <label>BB Username
          <input id="username" autocomplete="username" />
        </label>
        <label>BBAPI Code
          <input id="bbapiCode" type="password" autocomplete="current-password" />
        </label>
        <label>BB Site Password
          <input id="sitePassword" type="password" autocomplete="current-password" />
        </label>
      </div>
      <div class="hint">Same credentials style as the box-score tool. Site password is used to scrape national-team rosters and game logs. BBAPI code is used for player bio.</div>
    </div>

    <div class="card">
      <label>Search country
        <input id="countrySearch" placeholder="e.g. Israel, Bra, USA…" autocomplete="off" />
      </label>
      <div id="suggestions" class="suggestions" hidden></div>
      <div id="countryStatus" class="status">Select a country to load the {{ level_label }} roster.</div>
      <div id="countryError" class="err" hidden></div>
    </div>

    <div id="teamCard" class="card" hidden>
      <h2 id="teamName" style="margin-top:0"></h2>
      <div id="overviewStatus" class="status"></div>
      <div id="overviewError" class="err" hidden></div>
      <div id="overviewTableWrap" class="table-wrap"></div>
      <div id="playerChips" class="chips"></div>
    </div>

    <div id="playerCard" class="card" hidden></div>
  </div>

  <script>
    const LEVEL = {{ level | tojson }};
    const LEVEL_LABEL = {{ level_label | tojson }};
    const COUNTRIES = {{ countries | tojson }};
    const POSITION_ORDER = ["PG", "SG", "SF", "PF", "C"];
    const POS_COLORS = { PG: "#ef4444", SG: "#f97316", SF: "#eab308", PF: "#22c55e", C: "#3b82f6" };

    const els = {
      username: document.getElementById("username"),
      bbapiCode: document.getElementById("bbapiCode"),
      sitePassword: document.getElementById("sitePassword"),
      countrySearch: document.getElementById("countrySearch"),
      suggestions: document.getElementById("suggestions"),
      countryStatus: document.getElementById("countryStatus"),
      countryError: document.getElementById("countryError"),
      teamCard: document.getElementById("teamCard"),
      teamName: document.getElementById("teamName"),
      overviewStatus: document.getElementById("overviewStatus"),
      overviewError: document.getElementById("overviewError"),
      overviewTableWrap: document.getElementById("overviewTableWrap"),
      playerChips: document.getElementById("playerChips"),
      playerCard: document.getElementById("playerCard"),
    };

    let selectedCountry = null;
    let players = [];
    let overview = null;
    let injuryMap = {};
    let selectedPlayerId = null;
    let sortKey = "seasonTotal";
    let sortDir = "desc";

    function creds() {
      return {
        username: els.username.value.trim(),
        bbapi_code: els.bbapiCode.value,
        site_password: els.sitePassword.value,
        level: LEVEL,
      };
    }

    function requireCreds() {
      const c = creds();
      if (!c.username || !c.site_password) {
        throw new Error("Enter BB username and BB site password first.");
      }
      return c;
    }

    function minuteClass(mins) {
      if (mins >= 42) return "minute-hi";
      if (mins >= 24) return "minute-mid";
      if (mins >= 1) return "minute-lo";
      return "";
    }

    function sortPositions(list) {
      return [...list].sort((a, b) => {
        const ai = POSITION_ORDER.indexOf(a);
        const bi = POSITION_ORDER.indexOf(b);
        return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
      });
    }

    function renderSuggestions() {
      const q = els.countrySearch.value.trim().toLowerCase();
      if (!q) {
        els.suggestions.hidden = true;
        els.suggestions.innerHTML = "";
        return;
      }
      const matches = COUNTRIES.filter(c => c.name.toLowerCase().includes(q)).slice(0, 8);
      if (!matches.length) {
        els.suggestions.hidden = false;
        els.suggestions.innerHTML = `<div style="padding:10px;color:var(--muted)">No countries match “${els.countrySearch.value}”</div>`;
        return;
      }
      els.suggestions.hidden = false;
      els.suggestions.innerHTML = matches.map(c =>
        `<button type="button" data-id="${c.id}" data-name="${c.name}">
          <strong>${c.name}</strong><span class="meta">${LEVEL_LABEL}</span>
        </button>`
      ).join("");
      els.suggestions.querySelectorAll("button").forEach(btn => {
        btn.addEventListener("click", () => selectCountry(btn.dataset.id, btn.dataset.name));
      });
    }

    async function selectCountry(id, name) {
      selectedCountry = { id: Number(id), name };
      els.countrySearch.value = name;
      els.suggestions.hidden = true;
      els.countryError.hidden = true;
      els.playerCard.hidden = true;
      selectedPlayerId = null;
      els.teamCard.hidden = false;
      els.teamName.textContent = "Loading…";
      els.overviewTableWrap.innerHTML = "";
      els.playerChips.innerHTML = "";
      els.overviewStatus.textContent = "Loading roster…";
      try {
        const payload = { ...requireCreds(), country_id: Number(id) };
        const res = await fetch("/api/minutes/roster", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
        players = data.players || [];
        els.teamName.textContent = data.teamName || name;
        els.countryStatus.textContent = `${players.length} players loaded.`;
        renderChips();
        if (players.length) {
          void loadInjuries();
          void loadOverview();
        } else {
          els.overviewStatus.textContent = "No players found for this roster.";
        }
      } catch (err) {
        els.countryError.hidden = false;
        els.countryError.textContent = err.message;
        els.overviewStatus.textContent = "";
      }
    }

    function renderChips() {
      els.playerChips.innerHTML = players.map(p => {
        const injury = injuryMap[p.playerId] ? `<span class="injury">${injuryMap[p.playerId]}d</span>` : "";
        return `<button type="button" data-id="${p.playerId}" class="${selectedPlayerId === p.playerId ? "active" : ""}">${p.name}${injury}</button>`;
      }).join("");
      els.playerChips.querySelectorAll("button").forEach(btn => {
        btn.addEventListener("click", () => loadPlayer(Number(btn.dataset.id), btn.textContent));
      });
    }

    async function loadInjuries() {
      try {
        const res = await fetch("/api/minutes/injuries", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            ...requireCreds(),
            player_ids: players.map(p => p.playerId),
          }),
        });
        const data = await res.json();
        if (!res.ok) return;
        injuryMap = {};
        for (const row of (data.players || [])) {
          if (row.injuryDaysRemaining) injuryMap[row.playerId] = row.injuryDaysRemaining;
        }
        renderChips();
        if (overview) renderOverview();
      } catch (_) {}
    }

    async function loadOverview() {
      els.overviewError.hidden = true;
      els.overviewStatus.textContent = `Loading team stats — fetching ${players.length} players…`;
      try {
        const res = await fetch("/api/minutes/overview", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            ...requireCreds(),
            player_ids: players.map(p => p.playerId),
          }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
        overview = data;
        els.overviewStatus.textContent = `Current week: ${data.currentWeek ?? "off-season"} · Season ${data.currentSeason}`;
        renderOverview();
      } catch (err) {
        els.overviewError.hidden = false;
        els.overviewError.textContent = err.message;
        els.overviewStatus.textContent = "";
      }
    }

    function compareRows(a, b, nameMap) {
      let result = 0;
      if (sortKey === "player") {
        result = (nameMap[a.playerId] || "").localeCompare(nameMap[b.playerId] || "");
      } else if (sortKey === "gameShape") {
        result = (a.gameShape ?? -Infinity) - (b.gameShape ?? -Infinity);
      } else if (sortKey === "dmi") {
        result = (a.dmi ?? -Infinity) - (b.dmi ?? -Infinity);
      } else if (sortKey === "weekTotal") {
        result = a.weekTotal - b.weekTotal;
      } else if (sortKey === "seasonTotal") {
        result = a.seasonTotal - b.seasonTotal;
      } else if (sortKey.startsWith("position:")) {
        const pos = sortKey.slice("position:".length);
        result = (a.weekMinutesByPosition[pos] || 0) - (b.weekMinutesByPosition[pos] || 0);
      }
      if (result === 0) result = a.playerId - b.playerId;
      return sortDir === "asc" ? result : -result;
    }

    function setSort(key) {
      if (sortKey === key) sortDir = sortDir === "asc" ? "desc" : "asc";
      else {
        sortKey = key;
        sortDir = key === "player" ? "asc" : "desc";
      }
      renderOverview();
    }

    function sortMarker(key) {
      if (sortKey !== key) return "↕";
      return sortDir === "asc" ? "▲" : "▼";
    }

    function renderOverview() {
      if (!overview) return;
      const nameMap = Object.fromEntries(players.map(p => [p.playerId, p.name]));
      const allPositions = sortPositions([...new Set(
        overview.players.flatMap(p => [
          ...Object.keys(p.weekMinutesByPosition || {}),
          ...Object.keys(p.seasonMinutesByPosition || {}),
        ])
      )]);
      const rows = [...overview.players].sort((a, b) => compareRows(a, b, nameMap));
      const weekLabel = overview.currentWeek != null ? `W${overview.currentWeek}` : "";

      els.overviewTableWrap.innerHTML = `
        <table>
          <thead>
            <tr>
              <th><button type="button" data-sort="player">Player ${sortMarker("player")}</button></th>
              <th>BB</th>
              <th><button type="button" data-sort="gameShape">GS ${sortMarker("gameShape")}</button></th>
              <th><button type="button" data-sort="dmi">DMI ${sortMarker("dmi")}</button></th>
              ${allPositions.map(pos => `<th><button type="button" data-sort="position:${pos}">${pos}${weekLabel ? `<br><span style="font-weight:500;color:var(--muted)">${weekLabel}</span>` : ""} ${sortMarker("position:"+pos)}</button></th>`).join("")}
              <th><button type="button" data-sort="weekTotal">Week total ${sortMarker("weekTotal")}</button></th>
              <th><button type="button" data-sort="seasonTotal">S${overview.currentSeason} total ${sortMarker("seasonTotal")}</button></th>
            </tr>
          </thead>
          <tbody>
            ${rows.map(pd => {
              const injury = injuryMap[pd.playerId] ? `<span class="injury">${injuryMap[pd.playerId]}d</span>` : "";
              return `<tr class="clickable ${selectedPlayerId === pd.playerId ? "selected" : ""}" data-id="${pd.playerId}" data-name="${nameMap[pd.playerId] || pd.playerId}">
                <td><strong>${nameMap[pd.playerId] || pd.playerId}</strong>${injury}</td>
                <td><a class="bb" href="https://buzzerbeater.com/player/${pd.playerId}/overview.aspx" target="_blank" rel="noopener noreferrer" onclick="event.stopPropagation()">BB ↗</a></td>
                <td>${pd.gameShape ?? "—"}</td>
                <td>${pd.dmi == null ? "—" : Number(pd.dmi).toLocaleString()}</td>
                ${allPositions.map(pos => {
                  const mins = pd.weekMinutesByPosition[pos] || 0;
                  return `<td class="${minuteClass(mins)}">${mins > 0 ? mins : "—"}</td>`;
                }).join("")}
                <td><strong>${pd.weekTotal > 0 ? pd.weekTotal : "—"}</strong></td>
                <td>${pd.seasonTotal > 0 ? pd.seasonTotal : "—"}</td>
              </tr>`;
            }).join("")}
          </tbody>
        </table>
      `;
      els.overviewTableWrap.querySelectorAll("th button").forEach(btn => {
        btn.addEventListener("click", () => setSort(btn.dataset.sort));
      });
      els.overviewTableWrap.querySelectorAll("tr.clickable").forEach(row => {
        row.addEventListener("click", () => loadPlayer(Number(row.dataset.id), row.dataset.name));
      });
      renderChips();
    }

    async function loadPlayer(playerId, name) {
      selectedPlayerId = playerId;
      renderChips();
      if (overview) renderOverview();
      els.playerCard.hidden = false;
      els.playerCard.innerHTML = `<div class="status">Fetching game history for ${name}…</div>`;
      try {
        const res = await fetch("/api/minutes/player", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            ...requireCreds(),
            player_id: playerId,
          }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
        renderPlayer(data, name);
      } catch (err) {
        els.playerCard.innerHTML = `<div class="err">${err.message}</div>`;
      }
    }

    function renderPlayer(data, fallbackName) {
      const info = data.playerInfo || {};
      const name = fallbackName || [info.firstName, info.lastName].filter(Boolean).join(" ") || `Player ${data.playerId}`;
      const seasons = [...(data.seasons || [])].sort((a, b) => b.season - a.season);
      const agg = data.aggregations || {};
      const currentSeason = data.currentSeason;

      els.playerCard.innerHTML = `
        <div class="player-head">
          <div>
            <h2 style="margin:0">${name}</h2>
            ${info.injuryDaysRemaining ? `<span class="injury">Injured — ${info.injuryDaysRemaining} days</span>` : ""}
            <div class="meta-row">
              ${info.age != null ? `<div><span>Age</span><strong>${info.age}</strong></div>` : ""}
              ${info.bestPosition ? `<div><span>Position</span><strong>${info.bestPosition}</strong></div>` : ""}
              ${info.gameShape != null ? `<div><span>GS</span><strong>${info.gameShape}</strong></div>` : ""}
              ${info.dmi != null ? `<div><span>DMI</span><strong>${Number(info.dmi).toLocaleString()}</strong></div>` : ""}
              ${info.salary != null ? `<div><span>Salary</span><strong>$${Number(info.salary).toLocaleString()}</strong></div>` : ""}
            </div>
          </div>
          <a class="bb" href="https://buzzerbeater.com/player/${data.playerId}/overview.aspx" target="_blank" rel="noopener noreferrer">View on BB ↗</a>
        </div>
        ${seasons.length ? seasons.map(s => renderSeason(s, agg, info.age, currentSeason)).join("") : `<p class="hint">No game history found for this player.</p>`}
      `;
    }

    function renderSeason(seasonObj, agg, currentAge, currentSeason) {
      const season = seasonObj.season;
      const games = seasonObj.games || [];
      const counting = games.filter(g => !["BBM", "National Team", "Private"].includes(g.gameType));
      const weekMap = (agg.minutesBySeasonWeekPosition || {})[String(season)] || {};
      const posMap = (agg.minutesBySeasonPosition || {})[String(season)] || {};
      const positions = sortPositions(Object.keys(posMap));
      const weeks = Object.keys(weekMap).map(Number).sort((a, b) => a - b);
      const age = ((LEVEL === "nt" || LEVEL === "player") && currentAge != null)
        ? currentAge - (currentSeason - season)
        : null;
      const maxPos = Math.max(...Object.values(posMap), 0);

      return `<div class="season-block">
        <h3 style="margin:0 0 10px">
          Season ${season}
          <span style="font-weight:500;color:var(--muted);font-size:14px">
            ${counting.length} counting games / ${games.length} total${age != null ? ` · Age: ${age}` : ""}
          </span>
        </h3>
        <div class="grid" style="margin-bottom:14px">
          <div>
            <div class="hint" style="margin-bottom:8px">Minutes per Week</div>
            ${renderWeekChart(weekMap, positions)}
          </div>
          <div>
            <div class="hint" style="margin-bottom:8px">Minutes by Position</div>
            <div class="bars">
              ${positions.map(pos => {
                const mins = posMap[pos] || 0;
                const pct = maxPos ? Math.round((mins / maxPos) * 100) : 0;
                return `<div class="bar-row"><strong>${pos}</strong><div class="bar-track"><div class="bar-fill" style="width:${pct}%;background:${POS_COLORS[pos] || "#a855f7"}"></div></div><span>${mins} min</span></div>`;
              }).join("") || `<div class="hint">No counting games</div>`}
            </div>
          </div>
        </div>
        ${weeks.length ? `<div class="table-wrap"><table>
          <thead>
            <tr>
              <th>Pos</th>
              ${weeks.map(w => `<th>${w === 0 ? "W0*" : "W"+w}</th>`).join("")}
              <th>Total</th>
            </tr>
          </thead>
          <tbody>
            ${positions.map(pos => {
              const rowTotal = weeks.reduce((s, w) => s + ((weekMap[w] || {})[pos] || 0), 0);
              return `<tr>
                <td><strong>${pos}</strong></td>
                ${weeks.map(w => {
                  const mins = (weekMap[w] || {})[pos] || 0;
                  return `<td class="${minuteClass(mins)}">${mins > 0 ? mins : "—"}</td>`;
                }).join("")}
                <td><strong>${rowTotal}</strong></td>
              </tr>`;
            }).join("")}
          </tbody>
        </table></div>` : `<div class="hint">No counting games this season</div>`}
      </div>`;
    }

    function renderWeekChart(weekMap, positions) {
      const hasW0 = Object.prototype.hasOwnProperty.call(weekMap, "0") || Object.prototype.hasOwnProperty.call(weekMap, 0);
      const weeks = [...(hasW0 ? [0] : []), ...Array.from({ length: 14 }, (_, i) => i + 1)];
      const totals = weeks.map(w => positions.reduce((s, p) => s + ((weekMap[w] || weekMap[String(w)] || {})[p] || 0), 0));
      const maxTotal = Math.max(...totals, 1);
      return `<div class="week-chart">
        ${weeks.map((w, i) => {
          const total = totals[i];
          const segs = positions.map(pos => ({ pos, mins: (weekMap[w] || weekMap[String(w)] || {})[pos] || 0 })).filter(s => s.mins > 0);
          const h = total ? Math.max(Math.round((total / maxTotal) * 140), 4) : 0;
          return `<div class="week-col">
            <div class="week-stack" style="height:${h}px">
              ${segs.map(s => `<div class="week-seg" title="${s.pos}: ${s.mins}" style="height:${Math.max(Math.round((s.mins / maxTotal) * 140), 2)}px;background:${POS_COLORS[s.pos] || "#a855f7"}"></div>`).join("")}
            </div>
            <div class="week-label">${w === 0 ? "W0*" : "W"+w}</div>
          </div>`;
        }).join("")}
      </div>`;
    }

    els.countrySearch.addEventListener("input", renderSuggestions);
    els.countrySearch.addEventListener("focus", renderSuggestions);
  </script>
</body>
</html>
"""


def _load_countries() -> list[dict[str, str]]:
    try:
        import json

        payload = json.loads(LOCAL_NATIONAL_OPTIONS_PATH.read_text(encoding="utf-8"))
        countries = payload.get("countries") or []
        return sorted(
            [
                {"id": str(item["id"]), "name": str(item["name"])}
                for item in countries
                if item.get("id") and item.get("name")
            ],
            key=lambda item: item["name"].casefold(),
        )
    except Exception:
        return []


def _parse_level(value: Any) -> str:
    level = str(value or "u21").strip().lower()
    if level not in NATIONAL_TEAM_LEVELS:
        raise ValueError("level must be either u21 or nt")
    return level


def _parse_player_level(value: Any) -> str:
    level = str(value or "player").strip().lower()
    if level in ("u21", "nt", "player"):
        return level
    raise ValueError("level must be u21, nt, or player")


def _credentials_from_payload(payload: dict[str, Any]) -> tuple[str, str, str]:
    username = str(payload.get("username") or os.environ.get("BBAPI_LOGIN") or "").strip()
    bbapi_code = str(payload.get("bbapi_code") or os.environ.get("BBAPI_CODE") or "").strip()
    site_password = str(
        payload.get("site_password") or os.environ.get("BB_PASSWORD") or ""
    ).strip()
    if not username:
        raise ValueError("Username is required.")
    if not site_password:
        raise ValueError("BB site password is required.")
    return username, bbapi_code, site_password


def _site_client(username: str, site_password: str) -> BBSiteClient:
    client = BBSiteClient(username, site_password)
    client.login()
    return client


def _serialize_game(game: GameLogEntry) -> dict[str, Any]:
    return {
        "date": game.date,
        "position": game.position,
        "minutes": game.minutes,
        "gameType": game.game_type,
    }


def _default_u21_seasons(current_season: int) -> list[int]:
    start = min(U21_MINUTES_MIN_SEASON, current_season)
    return list(range(start, current_season + 1))


@minutes_bp.get("/u21-minutes")
def u21_minutes_page() -> str:
    return render_template_string(
        ANALYZER_HTML,
        title="U21 Minutes Analyzer",
        subtitle="Weekly and season minutes by position for U21 national-team rosters.",
        level="u21",
        level_label=NATIONAL_TEAM_LEVELS["u21"]["label"],
        countries=_load_countries(),
    )


@minutes_bp.get("/nt-minutes")
def nt_minutes_page() -> str:
    return render_template_string(
        ANALYZER_HTML,
        title="NT Minutes Analyzer",
        subtitle="Weekly and season minutes by position for senior national-team rosters.",
        level="nt",
        level_label=NATIONAL_TEAM_LEVELS["nt"]["label"],
        countries=_load_countries(),
    )


PLAYER_ANALYZER_HTML = r"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Player Minutes Analyzer</title>
  <style>
    :root {
      --bg: #f4f1ea;
      --card: #fffdf8;
      --ink: #1f1a17;
      --muted: #6b635c;
      --line: #d9d0c4;
      --accent: #1f6f5b;
      --accent-soft: #d7efe7;
      --danger: #fde8e8;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Avenir Next", "Segoe UI", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, #efe4d4, transparent 40%),
        linear-gradient(180deg, #f7f3ec, #efe8dc);
      min-height: 100vh;
    }
    .wrap { max-width: 1100px; margin: 0 auto; padding: 24px 16px 64px; }
    .topnav { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 18px; font-size: 14px; }
    .topnav a { color: var(--accent); text-decoration: none; font-weight: 600; }
    h1 { margin: 0 0 8px; font-size: 28px; }
    .lead { color: var(--muted); margin: 0 0 20px; }
    .card {
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 16px;
      margin-bottom: 16px;
      box-shadow: 0 10px 30px rgba(40, 28, 12, 0.05);
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
    }
    label { display: block; font-size: 13px; font-weight: 600; margin-bottom: 4px; }
    input, button {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 10px 12px;
      font: inherit;
      background: white;
    }
    button {
      background: var(--accent);
      color: white;
      border: none;
      font-weight: 700;
      cursor: pointer;
    }
    button:disabled { opacity: 0.55; cursor: wait; }
    .hint, .status { color: var(--muted); font-size: 13px; margin-top: 8px; }
    .err { background: var(--danger); border: 1px solid #f3b4b4; padding: 10px 12px; border-radius: 10px; margin-top: 10px; }
    table { width: 100%; border-collapse: collapse; font-size: 12px; }
    th, td { border: 1px solid var(--line); padding: 8px; vertical-align: middle; }
    th { background: #f3ece2; }
    .minute-hi { background: #dcfce7; font-weight: 700; }
    .minute-mid { background: #fef9c3; font-weight: 700; }
    .minute-lo { background: #ffedd5; font-weight: 700; }
    .injury {
      display: inline-block;
      margin-left: 6px;
      background: #fee2e2;
      color: #b91c1c;
      border-radius: 6px;
      padding: 2px 6px;
      font-size: 10px;
      font-weight: 700;
    }
    .player-head { display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap; align-items: start; }
    .meta-row { display: flex; flex-wrap: wrap; gap: 14px; margin-top: 8px; }
    .meta-row div { min-width: 70px; }
    .meta-row span { display: block; color: var(--muted); font-size: 11px; }
    .season-block { border-top: 1px solid var(--line); margin-top: 18px; padding-top: 14px; }
    .bars { display: grid; gap: 8px; }
    .bar-row { display: grid; grid-template-columns: 32px 1fr 56px; gap: 8px; align-items: center; }
    .bar-track { background: #eee7dc; border-radius: 999px; height: 8px; overflow: hidden; }
    .bar-fill { height: 100%; background: var(--accent); }
    .week-chart { display: flex; align-items: end; gap: 6px; min-height: 160px; overflow-x: auto; padding-bottom: 4px; }
    .week-col { width: 34px; flex: 0 0 34px; display: flex; flex-direction: column; justify-content: end; align-items: center; }
    .week-stack { width: 100%; display: flex; flex-direction: column-reverse; border-radius: 6px 6px 0 0; overflow: hidden; min-height: 2px; }
    .week-seg { width: 100%; }
    .week-label { margin-top: 4px; font-size: 10px; color: var(--muted); }
    a.bb { color: var(--accent); font-weight: 700; text-decoration: none; }
    .table-wrap { overflow-x: auto; }
    .actions { display: flex; gap: 10px; align-items: end; }
    .actions button { width: auto; min-width: 140px; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="topnav">
      <a href="/">Box Score Tool</a>
      <a href="/u21-minutes">U21 Minutes</a>
      <a href="/nt-minutes">NT Minutes</a>
      <a href="/player-minutes">Player Analyzer</a>
      <a href="/u21-tracker">U21 Tracker</a>
    </div>
    <h1>Player Minutes Analyzer</h1>
    <p class="lead">Enter a BuzzerBeater player ID to load career weekly minutes by position.</p>

    <div class="card">
      <div class="grid">
        <label>BB Username
          <input id="username" autocomplete="username" />
        </label>
        <label>BBAPI Code
          <input id="bbapiCode" type="password" autocomplete="current-password" />
        </label>
        <label>BB Site Password
          <input id="sitePassword" type="password" autocomplete="current-password" />
        </label>
      </div>
      <div class="hint">Site password scrapes game logs. BBAPI code fills player bio when available.</div>
    </div>

    <div class="card">
      <div class="actions">
        <label style="flex:1">Player ID
          <input id="playerId" inputmode="numeric" placeholder="e.g. 54721516" />
        </label>
        <button id="analyzeBtn" type="button">Analyze</button>
      </div>
      <div id="status" class="status">Enter a player ID and click Analyze.</div>
      <div id="error" class="err" hidden></div>
    </div>

    <div id="playerCard" class="card" hidden></div>
  </div>

  <script>
    const POSITION_ORDER = ["PG", "SG", "SF", "PF", "C"];
    const POS_COLORS = { PG: "#ef4444", SG: "#f97316", SF: "#eab308", PF: "#22c55e", C: "#3b82f6" };
    const els = {
      username: document.getElementById("username"),
      bbapiCode: document.getElementById("bbapiCode"),
      sitePassword: document.getElementById("sitePassword"),
      playerId: document.getElementById("playerId"),
      analyzeBtn: document.getElementById("analyzeBtn"),
      status: document.getElementById("status"),
      error: document.getElementById("error"),
      playerCard: document.getElementById("playerCard"),
    };

    function sortPositions(list) {
      return [...list].sort((a, b) => {
        const ai = POSITION_ORDER.indexOf(a);
        const bi = POSITION_ORDER.indexOf(b);
        return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
      });
    }
    function minuteClass(mins) {
      if (mins >= 42) return "minute-hi";
      if (mins >= 24) return "minute-mid";
      if (mins >= 1) return "minute-lo";
      return "";
    }
    function requireCreds() {
      const username = els.username.value.trim();
      const site_password = els.sitePassword.value;
      if (!username || !site_password) throw new Error("Enter BB username and BB site password first.");
      return {
        username,
        bbapi_code: els.bbapiCode.value,
        site_password,
        level: "player",
      };
    }

    async function analyze() {
      els.error.hidden = true;
      els.playerCard.hidden = true;
      const playerId = Number(String(els.playerId.value || "").trim());
      if (!Number.isInteger(playerId) || playerId < 1) {
        els.error.hidden = false;
        els.error.textContent = "Enter a valid numeric player ID.";
        return;
      }
      els.analyzeBtn.disabled = true;
      els.status.textContent = `Fetching career minutes for player ${playerId}… this can take a while.`;
      try {
        const res = await fetch("/api/minutes/player", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...requireCreds(), player_id: playerId }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
        const info = data.playerInfo || {};
        const name = [info.firstName, info.lastName].filter(Boolean).join(" ") || `Player ${playerId}`;
        els.status.textContent = `Loaded ${ (data.seasons || []).length } seasons for ${name}.`;
        renderPlayer(data, name);
      } catch (err) {
        els.error.hidden = false;
        els.error.textContent = err.message;
        els.status.textContent = "";
      } finally {
        els.analyzeBtn.disabled = false;
      }
    }

    function renderPlayer(data, name) {
      const info = data.playerInfo || {};
      const seasons = [...(data.seasons || [])].sort((a, b) => b.season - a.season);
      const agg = data.aggregations || {};
      const currentSeason = data.currentSeason;
      els.playerCard.hidden = false;
      els.playerCard.innerHTML = `
        <div class="player-head">
          <div>
            <h2 style="margin:0">${name}</h2>
            ${info.injuryDaysRemaining ? `<span class="injury">Injured — ${info.injuryDaysRemaining} days</span>` : ""}
            <div class="meta-row">
              ${info.age != null ? `<div><span>Age</span><strong>${info.age}</strong></div>` : ""}
              ${info.bestPosition ? `<div><span>Position</span><strong>${info.bestPosition}</strong></div>` : ""}
              ${info.gameShape != null ? `<div><span>GS</span><strong>${info.gameShape}</strong></div>` : ""}
              ${info.dmi != null ? `<div><span>DMI</span><strong>${Number(info.dmi).toLocaleString()}</strong></div>` : ""}
              ${info.salary != null ? `<div><span>Salary</span><strong>$${Number(info.salary).toLocaleString()}</strong></div>` : ""}
            </div>
          </div>
          <a class="bb" href="https://buzzerbeater.com/player/${data.playerId}/overview.aspx" target="_blank" rel="noopener noreferrer">View on BB ↗</a>
        </div>
        ${seasons.length ? seasons.map(s => renderSeason(s, agg, info.age, currentSeason)).join("") : `<p class="hint">No game history found for this player.</p>`}
      `;
    }

    function renderSeason(seasonObj, agg, currentAge, currentSeason) {
      const season = seasonObj.season;
      const games = seasonObj.games || [];
      const counting = games.filter(g => !["BBM", "National Team", "Private"].includes(g.gameType));
      const weekMap = (agg.minutesBySeasonWeekPosition || {})[String(season)] || {};
      const posMap = (agg.minutesBySeasonPosition || {})[String(season)] || {};
      const positions = sortPositions(Object.keys(posMap));
      const weeks = Object.keys(weekMap).map(Number).sort((a, b) => a - b);
      const age = currentAge != null ? currentAge - (currentSeason - season) : null;
      const maxPos = Math.max(...Object.values(posMap), 0);
      return `<div class="season-block">
        <h3 style="margin:0 0 10px">
          Season ${season}
          <span style="font-weight:500;color:var(--muted);font-size:14px">
            ${counting.length} counting games / ${games.length} total${age != null ? ` · Age: ${age}` : ""}
          </span>
        </h3>
        <div class="grid" style="margin-bottom:14px">
          <div>
            <div class="hint" style="margin-bottom:8px">Minutes per Week</div>
            ${renderWeekChart(weekMap, positions)}
          </div>
          <div>
            <div class="hint" style="margin-bottom:8px">Minutes by Position</div>
            <div class="bars">
              ${positions.map(pos => {
                const mins = posMap[pos] || 0;
                const pct = maxPos ? Math.round((mins / maxPos) * 100) : 0;
                return `<div class="bar-row"><strong>${pos}</strong><div class="bar-track"><div class="bar-fill" style="width:${pct}%;background:${POS_COLORS[pos] || "#a855f7"}"></div></div><span>${mins} min</span></div>`;
              }).join("") || `<div class="hint">No counting games</div>`}
            </div>
          </div>
        </div>
        ${weeks.length ? `<div class="table-wrap"><table>
          <thead>
            <tr>
              <th>Pos</th>
              ${weeks.map(w => `<th>${w === 0 ? "W0*" : "W"+w}</th>`).join("")}
              <th>Total</th>
            </tr>
          </thead>
          <tbody>
            ${positions.map(pos => {
              const rowTotal = weeks.reduce((s, w) => s + ((weekMap[w] || {})[pos] || 0), 0);
              return `<tr>
                <td><strong>${pos}</strong></td>
                ${weeks.map(w => {
                  const mins = (weekMap[w] || {})[pos] || 0;
                  return `<td class="${minuteClass(mins)}">${mins > 0 ? mins : "—"}</td>`;
                }).join("")}
                <td><strong>${rowTotal}</strong></td>
              </tr>`;
            }).join("")}
          </tbody>
        </table></div>` : `<div class="hint">No counting games this season</div>`}
      </div>`;
    }

    function renderWeekChart(weekMap, positions) {
      const hasW0 = Object.prototype.hasOwnProperty.call(weekMap, "0") || Object.prototype.hasOwnProperty.call(weekMap, 0);
      const weeks = [...(hasW0 ? [0] : []), ...Array.from({ length: 14 }, (_, i) => i + 1)];
      const totals = weeks.map(w => positions.reduce((s, p) => s + ((weekMap[w] || weekMap[String(w)] || {})[p] || 0), 0));
      const maxTotal = Math.max(...totals, 1);
      return `<div class="week-chart">
        ${weeks.map((w, i) => {
          const total = totals[i];
          const segs = positions.map(pos => ({ pos, mins: (weekMap[w] || weekMap[String(w)] || {})[pos] || 0 })).filter(s => s.mins > 0);
          const h = total ? Math.max(Math.round((total / maxTotal) * 140), 4) : 0;
          return `<div class="week-col">
            <div class="week-stack" style="height:${h}px">
              ${segs.map(s => `<div class="week-seg" title="${s.pos}: ${s.mins}" style="height:${Math.max(Math.round((s.mins / maxTotal) * 140), 2)}px;background:${POS_COLORS[s.pos] || "#a855f7"}"></div>`).join("")}
            </div>
            <div class="week-label">${w === 0 ? "W0*" : "W"+w}</div>
          </div>`;
        }).join("")}
      </div>`;
    }

    els.analyzeBtn.addEventListener("click", analyze);
    els.playerId.addEventListener("keydown", (event) => {
      if (event.key === "Enter") analyze();
    });
  </script>
</body>
</html>
"""


@minutes_bp.get("/player-minutes")
def player_minutes_page() -> str:
    return render_template_string(PLAYER_ANALYZER_HTML)


@minutes_bp.post("/api/minutes/roster")
def api_roster() -> tuple[Any, int] | Any:
    payload = request.get_json(silent=True) or {}
    try:
        level = _parse_level(payload.get("level"))
        username, _, site_password = _credentials_from_payload(payload)
        country_id = int(payload.get("country_id"))
        if country_id < 1:
            raise ValueError("Invalid country_id")
        client = _site_client(username, site_password)
        team_name, players = client.fetch_national_roster(country_id, level)
        return jsonify(
            {
                "countryId": country_id,
                "level": level,
                "teamName": team_name,
                "players": [
                    {"playerId": player.player_id, "name": player.name} for player in players
                ],
            }
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@minutes_bp.post("/api/minutes/injuries")
def api_injuries() -> tuple[Any, int] | Any:
    payload = request.get_json(silent=True) or {}
    try:
        username, _, site_password = _credentials_from_payload(payload)
        player_ids = [int(value) for value in (payload.get("player_ids") or []) if int(value) > 0]
        client = _site_client(username, site_password)
        players = []
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {
                pool.submit(client.fetch_player_injury, player_id): player_id
                for player_id in player_ids
            }
            for future in as_completed(futures):
                player_id = futures[future]
                injury = ""
                try:
                    injury = future.result()
                except Exception:
                    injury = ""
                players.append({"playerId": player_id, "injuryDaysRemaining": injury})
        return jsonify({"players": players})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@minutes_bp.post("/api/minutes/overview")
def api_overview() -> tuple[Any, int] | Any:
    payload = request.get_json(silent=True) or {}
    try:
        username, _, site_password = _credentials_from_payload(payload)
        player_ids = [int(value) for value in (payload.get("player_ids") or []) if int(value) > 0]
        if not player_ids:
            raise ValueError("player_ids required")
        season = DEFAULT_CURRENT_SEASON
        current_week = current_week_for_season(season)
        client = _site_client(username, site_password)

        def fetch_one(player_id: int) -> dict[str, Any]:
            try:
                result = client.fetch_player_game_log_detailed(player_id, season)
                overview = overview_for_games(
                    result.games, season=season, current_week=current_week
                )
                info = result.site_player_info
                return {
                    "playerId": player_id,
                    **overview,
                    "dmi": info.dmi if info else None,
                    "gameShape": info.game_shape if info else None,
                    "injuryDaysRemaining": result.injury_days,
                    "error": None,
                }
            except Exception as exc:
                return {
                    "playerId": player_id,
                    "weekMinutesByPosition": {},
                    "seasonMinutesByPosition": {},
                    "weekTotal": 0,
                    "seasonTotal": 0,
                    "dmi": None,
                    "gameShape": None,
                    "injuryDaysRemaining": "",
                    "error": str(exc),
                }

        players: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(fetch_one, player_id) for player_id in player_ids]
            for future in as_completed(futures):
                players.append(future.result())
        players.sort(key=lambda item: player_ids.index(item["playerId"]))
        return jsonify(
            {
                "currentSeason": season,
                "currentWeek": current_week,
                "players": players,
            }
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@minutes_bp.post("/api/minutes/player")
def api_player() -> tuple[Any, int] | Any:
    payload = request.get_json(silent=True) or {}
    try:
        level = _parse_player_level(payload.get("level", "u21"))
        username, bbapi_code, site_password = _credentials_from_payload(payload)
        player_id = int(payload.get("player_id"))
        if player_id < 1:
            raise ValueError("Invalid player_id")

        seasons_param = payload.get("seasons")
        if isinstance(seasons_param, list) and seasons_param:
            seasons = [int(value) for value in seasons_param if int(value) > 0]
        else:
            seasons = None

        client = _site_client(username, site_password)
        if seasons is None:
            if level in ("nt", "player"):
                seasons = client.fetch_player_available_seasons(player_id)
                if not seasons:
                    seasons = _default_u21_seasons(DEFAULT_CURRENT_SEASON)
            else:
                seasons = _default_u21_seasons(DEFAULT_CURRENT_SEASON)

        player_info = None
        if bbapi_code:
            try:
                api = BBApi(username, bbapi_code)
                if getattr(api, "logged_in", False):
                    raw = api.player_info(player_id)
                    player_info = {
                        "playerId": raw.get("player_id", player_id),
                        "firstName": raw.get("first_name") or "",
                        "lastName": raw.get("last_name") or "",
                        "age": raw.get("age"),
                        "height": raw.get("height"),
                        "dmi": raw.get("dmi"),
                        "salary": raw.get("salary"),
                        "bestPosition": raw.get("best_position"),
                        "gameShape": raw.get("game_shape"),
                        "potential": raw.get("potential"),
                        "injuryDaysRemaining": None,
                    }
            except Exception:
                player_info = None

        season_logs: list[dict[str, Any]] = []
        injury_days = ""
        site_player_info = None
        serialized_seasons: list[dict[str, Any]] = []

        for season in seasons:
            try:
                result = client.fetch_player_game_log_detailed(player_id, season)
                if result.injury_days or not injury_days:
                    injury_days = result.injury_days
                if site_player_info is None and result.site_player_info is not None:
                    site_player_info = result.site_player_info
                if result.games:
                    season_logs.append({"season": season, "games": result.games})
                    serialized_seasons.append(
                        {
                            "season": season,
                            "games": [_serialize_game(game) for game in result.games],
                        }
                    )
            except Exception:
                continue

        aggregations = aggregate_game_logs(season_logs)

        if player_info is None and site_player_info is not None:
            player_info = {
                "playerId": site_player_info.player_id,
                "firstName": site_player_info.first_name,
                "lastName": site_player_info.last_name,
                "age": site_player_info.age,
                "height": site_player_info.height,
                "dmi": site_player_info.dmi,
                "salary": site_player_info.salary,
                "bestPosition": site_player_info.best_position,
                "gameShape": site_player_info.game_shape,
                "potential": site_player_info.potential,
                "injuryDaysRemaining": injury_days or None,
            }
        elif player_info is not None:
            player_info["injuryDaysRemaining"] = injury_days or None

        return jsonify(
            {
                "playerId": player_id,
                "level": level,
                "currentSeason": DEFAULT_CURRENT_SEASON,
                "playerInfo": player_info,
                "seasons": serialized_seasons,
                "aggregations": aggregations,
                "ageBySeason": {
                    str(season): age_for_season(
                        (player_info or {}).get("age"),
                        DEFAULT_CURRENT_SEASON,
                        season,
                    )
                    for season in seasons
                },
            }
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400
