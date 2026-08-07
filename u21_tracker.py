from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests
from flask import Blueprint, jsonify, render_template_string, request


u21_tracker_bp = Blueprint("u21_tracker", __name__)

DEFAULT_CURRENT_SEASON = int(os.environ.get("CURRENT_SEASON", "73"))
DEFAULT_TRACKER_REPO = os.environ.get("U21_TRACKER_GITHUB_REPO", "guygir/bb_fantasy")
DEFAULT_TRACKER_BRANCH = os.environ.get("U21_TRACKER_GITHUB_BRANCH", "main")
LOCAL_TRACKER_ROOT = Path(__file__).with_name("data") / "u21-tracker"


TRACKER_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>U21 Tracker</title>
  <style>
    :root {
      --bg: #f6f8fb;
      --panel: #fff;
      --line: #d9e1ea;
      --ink: #1f2933;
      --muted: #607285;
      --accent: #0d47a1;
      --accent-soft: #e8f1ff;
      --danger: #b42318;
      --shadow: 0 8px 26px rgba(16, 24, 40, 0.08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
      background: radial-gradient(circle at 10% 10%, #eef4ff 0%, transparent 35%), var(--bg);
      color: var(--ink);
      min-height: 100vh;
    }
    .wrap { max-width: 1180px; margin: 0 auto; padding: 24px 16px 56px; }
    .topnav { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 18px; font-size: 14px; }
    .topnav a { color: var(--accent); text-decoration: none; font-weight: 700; }
    h1 { margin: 0 0 8px; font-size: 28px; }
    .lead { color: var(--muted); margin: 0 0 20px; line-height: 1.45; }
    .layout { display: grid; grid-template-columns: 290px 1fr; gap: 16px; align-items: start; }
    .card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      padding: 16px;
    }
    label { display: block; font-size: 13px; font-weight: 700; color: #344054; }
    input, select, button {
      font: inherit;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
    }
    input, select { width: 100%; margin-top: 6px; padding: 9px 10px; }
    button { cursor: pointer; }
    .country-list { display: grid; gap: 6px; max-height: 68vh; overflow: auto; margin-top: 12px; }
    .country-btn {
      width: 100%;
      text-align: left;
      padding: 9px 10px;
      color: var(--ink);
      transition: background 120ms ease, border-color 120ms ease;
    }
    .country-btn:hover { background: #f8fbff; }
    .country-btn.active { border-color: var(--accent); background: var(--accent-soft); color: var(--accent); font-weight: 700; }
    .country-btn span { display: block; color: var(--muted); font-size: 12px; font-weight: 500; margin-top: 2px; }
    .controls { display: flex; flex-wrap: wrap; align-items: end; justify-content: space-between; gap: 12px; margin-bottom: 14px; }
    .control-row { display: flex; flex-wrap: wrap; align-items: end; gap: 8px; }
    .control-row button {
      padding: 8px 11px;
      color: var(--accent);
      border-color: var(--accent);
      font-weight: 700;
    }
    .compare { min-width: 220px; }
    .season { min-width: 130px; }
    .status { color: var(--muted); font-size: 13px; }
    .err { border: 1px solid #f3c7c7; background: #fff1f1; color: var(--danger); border-radius: 8px; padding: 10px 12px; margin-bottom: 12px; }
    .chart-card { overflow-x: auto; border: 1px solid var(--line); border-radius: 8px; background: #fcfbf8; padding: 10px; }
    svg { width: 100%; min-width: 620px; height: auto; display: block; }
    .legend { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
    .chip {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: #fff;
      padding: 4px 8px;
      font-size: 12px;
      font-weight: 700;
    }
    .dot { width: 9px; height: 9px; border-radius: 50%; display: inline-block; }
    .tables { display: grid; grid-template-columns: 1fr; gap: 12px; margin-top: 14px; }
    .tables.compare-active { grid-template-columns: 1fr 1fr; }
    .table-wrap { overflow-x: auto; border: 1px solid var(--line); border-radius: 8px; }
    .table-title { padding: 9px 10px; border-bottom: 1px solid var(--line); background: #f8fbff; font-size: 12px; font-weight: 800; text-transform: uppercase; color: var(--muted); }
    table { width: 100%; border-collapse: collapse; font-size: 12px; }
    th, td { padding: 8px; border-bottom: 1px solid var(--line); text-align: left; white-space: nowrap; }
    th button { border: 0; padding: 0; background: transparent; color: inherit; font-weight: 800; }
    tr.player-row { cursor: pointer; }
    tr.player-row:hover { background: #f8fbff; }
    tr.hidden-player { opacity: 0.42; }
    .empty { color: var(--muted); padding: 24px 0; text-align: center; }
    @media (max-width: 860px) {
      .layout { grid-template-columns: 1fr; }
      .country-list { max-height: 260px; }
      .tables.compare-active { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <main class="wrap">
    <nav class="topnav">
      <a href="/">Box Score Tool</a>
      <a href="/u21-minutes">U21 Minutes</a>
      <a href="/nt-minutes">NT Minutes</a>
      <a href="/player-minutes">Player Analyzer</a>
      <a href="/u21-tracker">U21 Tracker</a>
    </nav>
    <h1>U21 Tracker</h1>
    <p class="lead" id="pageLead">Weekly DMI, game shape, and salary snapshots for U21 Round Robin pool countries.</p>

    <div class="layout">
      <aside class="card">
        <label>Search country
          <input id="countrySearch" placeholder="Israel, Pool H..." autocomplete="off" />
        </label>
        <div id="countryList" class="country-list"></div>
      </aside>

      <section class="card">
        <div id="errorBox" class="err" hidden></div>
        <div id="status" class="status">Loading tracker data...</div>
        <div id="trackerContent" hidden>
          <div class="controls">
            <div>
              <h2 id="chartTitle" style="margin:0 0 4px;font-size:20px"></h2>
              <div id="chartSub" class="status"></div>
            </div>
            <div class="control-row">
              <label class="season">Season
                <select id="seasonSelect">
                  {% for season in available_seasons %}
                  <option value="{{ season }}" {% if season == current_season %}selected{% endif %}>Season {{ season }}</option>
                  {% endfor %}
                </select>
              </label>
              <label class="compare">Compare with
                <select id="compareSelect">
                  <option value="">None</option>
                </select>
              </label>
              <button type="button" id="showAllBtn">Show all</button>
              <button type="button" id="hideAllBtn">Hide all</button>
            </div>
          </div>
          <div class="chart-card">
            <svg id="chart" viewBox="0 0 760 420" role="img" aria-label="U21 tracker DMI chart"></svg>
            <div id="legend" class="legend"></div>
            <div class="status" style="margin-top:8px">X = season week. Y = DMI. Color = player position. Number above each point = game shape. Dashed lines = compare team.</div>
          </div>
          <div id="tables" class="tables"></div>
        </div>
      </section>
    </div>
  </main>

  <script>
    const SEASON = {{ current_season }};
    const POSITION_COLORS = {
      PG: "#2563eb",
      SG: "#dc2626",
      SF: "#16a34a",
      PF: "#d97706",
      C: "#7c3aed",
      UNK: "#64748b",
    };
    const DMI_STEP = 50000;
    const DEFAULT_VISIBLE_PER_TEAM = 3;

    const state = {
      meta: null,
      selectedCountryId: null,
      compareCountryId: null,
      primaryData: null,
      compareData: null,
      hiddenPlayers: new Set(),
      sort: { key: "dmi", dir: "desc" },
    };

    const els = {
      lead: document.getElementById("pageLead"),
      search: document.getElementById("countrySearch"),
      list: document.getElementById("countryList"),
      status: document.getElementById("status"),
      error: document.getElementById("errorBox"),
      content: document.getElementById("trackerContent"),
      title: document.getElementById("chartTitle"),
      sub: document.getElementById("chartSub"),
      compare: document.getElementById("compareSelect"),
      chart: document.getElementById("chart"),
      legend: document.getElementById("legend"),
      tables: document.getElementById("tables"),
      season: document.getElementById("seasonSelect"),
      showAll: document.getElementById("showAllBtn"),
      hideAll: document.getElementById("hideAllBtn"),
    };

    function latestPoint(player) {
      if (!player.points?.length) return null;
      return [...player.points].sort((a, b) => b.week - a.week)[0];
    }

    function normalizedPosition(player) {
      const latest = latestPoint(player);
      const value = String(latest?.position || player.position || "").toUpperCase();
      return ["PG", "SG", "SF", "PF", "C"].includes(value) ? value : "UNK";
    }

    function positionLabel(player) {
      const position = normalizedPosition(player);
      return position === "UNK" ? "?" : position;
    }

    function colorFor(player) {
      return POSITION_COLORS[normalizedPosition(player)] || POSITION_COLORS.UNK;
    }

    function shortPlayerName(name) {
      const parts = String(name || "").trim().split(/\s+/).filter(Boolean);
      if (parts.length <= 1) return (parts[0] || "").slice(0, 12);
      return `${parts[0][0]}. ${parts[parts.length - 1]}`.slice(0, 16);
    }

    function formatDmiTick(value) {
      if (value >= 1000000) {
        const millions = value / 1000000;
        return `${Number.isInteger(millions) ? millions.toFixed(0) : millions.toFixed(2)}M`;
      }
      if (value >= 1000) return `${Math.round(value / 1000)}k`;
      return String(value);
    }

    function formatMoney(value) {
      if (value == null) return "-";
      return `$${Number(value).toLocaleString()}`;
    }

    function setError(message) {
      els.error.hidden = !message;
      els.error.textContent = message || "";
    }

    async function loadJson(url) {
      const res = await fetch(url);
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || `HTTP ${res.status}`);
      return json;
    }

    function filteredCountries() {
      const q = els.search.value.trim().toLowerCase();
      const list = state.meta?.countries || [];
      if (!q) return list;
      return list.filter((country) =>
        country.name.toLowerCase().includes(q) || country.pool.toLowerCase().includes(q)
      );
    }

    function renderCountries() {
      const rows = filteredCountries();
      els.list.innerHTML = rows.map((country) => `
        <button type="button" class="country-btn ${country.countryId === state.selectedCountryId ? "active" : ""}" data-country-id="${country.countryId}">
          ${country.name}
          <span>${country.pool}</span>
        </button>
      `).join("") || `<div class="empty">No countries match.</div>`;
    }

    function renderCompareOptions() {
      const countries = state.meta?.countries || [];
      els.compare.innerHTML = `<option value="">None</option>` + countries
        .filter((country) => country.countryId !== state.selectedCountryId)
        .map((country) => `<option value="${country.countryId}" ${country.countryId === state.compareCountryId ? "selected" : ""}>${country.name} (${country.pool})</option>`)
        .join("");
    }

    async function selectCountry(countryId) {
      state.selectedCountryId = Number(countryId);
      if (state.compareCountryId === state.selectedCountryId) state.compareCountryId = null;
      state.primaryData = null;
      setError("");
      els.status.hidden = false;
      els.status.textContent = "Loading country series...";
      els.content.hidden = true;
      renderCountries();
      renderCompareOptions();
      try {
        state.primaryData = await loadJson(`/api/u21-tracker?season=${SEASON}&countryId=${state.selectedCountryId}`);
        await refreshCompare();
        resetVisiblePlayers();
        renderTracker();
      } catch (err) {
        setError(err.message);
        els.status.textContent = "Could not load this country.";
      }
    }

    async function refreshCompare() {
      state.compareData = null;
      if (!state.compareCountryId) return;
      state.compareData = await loadJson(`/api/u21-tracker?season=${SEASON}&countryId=${state.compareCountryId}`);
    }

    function decoratePlayers(data, teamKey) {
      const countryName = data?.country?.name || (teamKey === "primary" ? "Team A" : "Team B");
      return (data?.players || []).map((player) => ({
        ...player,
        teamKey,
        teamName: countryName,
      }));
    }

    function topIdsByDmi(players, n) {
      return new Set([...players]
        .sort((a, b) => (latestPoint(b)?.dmi ?? -Infinity) - (latestPoint(a)?.dmi ?? -Infinity))
        .slice(0, n)
        .map((player) => player.playerId));
    }

    function resetVisiblePlayers() {
      const hidden = new Set();
      for (const players of [decoratePlayers(state.primaryData, "primary"), decoratePlayers(state.compareData, "compare")]) {
        const keep = topIdsByDmi(players, DEFAULT_VISIBLE_PER_TEAM);
        for (const player of players) {
          if (!keep.has(player.playerId)) hidden.add(player.playerId);
        }
      }
      state.hiddenPlayers = hidden;
    }

    function allPlayers() {
      return [
        ...decoratePlayers(state.primaryData, "primary"),
        ...decoratePlayers(state.compareData, "compare"),
      ];
    }

    function allWeeks() {
      const weeks = new Set([...(state.primaryData?.weeks || []), ...(state.compareData?.weeks || [])]);
      return [...weeks].sort((a, b) => a - b);
    }

    function floorStrictMultiple(value, step) {
      const floored = Math.floor(value / step) * step;
      return Math.max(0, floored < value ? floored : floored - step);
    }

    function ceilStrictMultiple(value, step) {
      const ceiled = Math.ceil(value / step) * step;
      return ceiled > value ? ceiled : ceiled + step;
    }

    function renderChart(players, weeks) {
      const width = 760;
      const height = 420;
      const pad = { top: 28, right: 108, bottom: 40, left: 58 };
      const innerW = width - pad.left - pad.right;
      const innerH = height - pad.top - pad.bottom;
      const dmiValues = players.flatMap((player) => (player.points || []).map((point) => point.dmi).filter((value) => value != null));
      const minDmi = dmiValues.length ? Math.min(...dmiValues) : 0;
      const maxDmi = dmiValues.length ? Math.max(...dmiValues) : DMI_STEP;
      const yMin = dmiValues.length ? floorStrictMultiple(minDmi, DMI_STEP) : 0;
      const yMax = dmiValues.length ? ceilStrictMultiple(maxDmi, DMI_STEP) : DMI_STEP;
      const xWeeks = weeks.length ? weeks : [0];
      const xPos = (week) => {
        if (xWeeks.length === 1) return pad.left + innerW / 2;
        return pad.left + ((week - xWeeks[0]) / (xWeeks[xWeeks.length - 1] - xWeeks[0] || 1)) * innerW;
      };
      const yPos = (dmi) => pad.top + ((yMax - dmi) / (yMax - yMin || 1)) * innerH;
      const range = Math.max(yMax - yMin, DMI_STEP);
      const tickStep = Math.max(DMI_STEP, Math.ceil((range / 6) / DMI_STEP) * DMI_STEP);
      const tickVals = [];
      for (let value = yMin; value <= yMax + 1; value += tickStep) tickVals.push(value);
      if (tickVals[tickVals.length - 1] !== yMax) tickVals.push(yMax);

      const visible = players.filter((player) => !state.hiddenPlayers.has(player.playerId));
      let svg = `<rect x="${pad.left}" y="${pad.top}" width="${innerW}" height="${innerH}" fill="#fffdf8" stroke="#e7e0d4" />`;
      for (const val of tickVals) {
        const y = yPos(val);
        svg += `<line x1="${pad.left}" x2="${pad.left + innerW}" y1="${y}" y2="${y}" stroke="#e7e0d4" stroke-dasharray="4 4" />`;
        svg += `<text x="${pad.left - 8}" y="${y + 4}" text-anchor="end" font-size="11" fill="#6b7280">${formatDmiTick(val)}</text>`;
      }
      for (const week of xWeeks) {
        svg += `<text x="${xPos(week)}" y="${height - 12}" text-anchor="middle" font-size="11" fill="#6b7280">W${week}</text>`;
      }
      svg += `<text x="16" y="${pad.top + innerH / 2}" transform="rotate(-90 16 ${pad.top + innerH / 2})" text-anchor="middle" font-size="12" fill="#4b5563">DMI</text>`;

      for (const player of visible) {
        const color = colorFor(player);
        const pts = (player.points || []).filter((point) => point.dmi != null);
        if (!pts.length) continue;
        const path = pts.map((point, index) => `${index === 0 ? "M" : "L"} ${xPos(point.week)} ${yPos(point.dmi)}`).join(" ");
        const last = [...pts].sort((a, b) => a.week - b.week)[pts.length - 1];
        svg += `<path d="${path}" fill="none" stroke="${color}" stroke-width="2" opacity="0.86" ${player.teamKey === "compare" ? 'stroke-dasharray="5 4"' : ""} />`;
        for (const point of pts) {
          svg += `<circle cx="${xPos(point.week)}" cy="${yPos(point.dmi)}" r="4.5" fill="${color}" />`;
          svg += `<text x="${xPos(point.week)}" y="${yPos(point.dmi) - 8}" text-anchor="middle" font-size="11" font-weight="700" fill="${color}">${point.gameShape ?? "-"}</text>`;
        }
        svg += `<text x="${xPos(last.week) + 8}" y="${yPos(last.dmi) + 3}" font-size="10" font-weight="700" fill="${color}">${shortPlayerName(player.name)}</text>`;
      }
      if (!visible.length) {
        svg += `<text x="${width / 2}" y="${height / 2}" text-anchor="middle" font-size="14" fill="#9ca3af">No players visible</text>`;
      }
      els.chart.innerHTML = svg;
      els.legend.innerHTML = visible.map((player) => `
        <span class="chip" style="color:${colorFor(player)}">
          <span class="dot" style="background:${colorFor(player)}"></span>
          ${positionLabel(player)} - ${shortPlayerName(player.name)}
        </span>
      `).join("");
    }

    function sortablePlayers(players) {
      const rows = players.map((player) => {
        const latest = latestPoint(player);
        return {
          player,
          name: player.name,
          position: normalizedPosition(player),
          gameShape: latest?.gameShape ?? null,
          dmi: latest?.dmi ?? null,
          salary: latest?.salary ?? null,
        };
      });
      rows.sort((a, b) => {
        let result = 0;
        if (state.sort.key === "name") result = a.name.localeCompare(b.name);
        else if (state.sort.key === "position") result = a.position.localeCompare(b.position);
        else result = (a[state.sort.key] ?? -Infinity) - (b[state.sort.key] ?? -Infinity);
        if (result === 0) result = a.player.playerId - b.player.playerId;
        return state.sort.dir === "asc" ? result : -result;
      });
      return rows;
    }

    function sortMarker(key) {
      if (state.sort.key !== key) return "";
      return state.sort.dir === "asc" ? " ^" : " v";
    }

    function renderTable(title, players) {
      const rows = sortablePlayers(players);
      return `
        <div class="table-wrap">
          <div class="table-title">${title}</div>
          <table>
            <thead>
              <tr>
                <th><button type="button" data-sort="name">Player${sortMarker("name")}</button></th>
                <th><button type="button" data-sort="position">Pos${sortMarker("position")}</button></th>
                <th><button type="button" data-sort="gameShape">GS${sortMarker("gameShape")}</button></th>
                <th><button type="button" data-sort="dmi">DMI${sortMarker("dmi")}</button></th>
                <th><button type="button" data-sort="salary">Salary${sortMarker("salary")}</button></th>
              </tr>
            </thead>
            <tbody>
              ${rows.map(({ player, gameShape, dmi, salary }) => `
                <tr class="player-row ${state.hiddenPlayers.has(player.playerId) ? "hidden-player" : ""}" data-player-id="${player.playerId}">
                  <td><span class="dot" style="background:${colorFor(player)}"></span> ${player.name}</td>
                  <td>${positionLabel(player)}</td>
                  <td>${gameShape ?? "-"}</td>
                  <td>${dmi == null ? "-" : Number(dmi).toLocaleString()}</td>
                  <td>${formatMoney(salary)}</td>
                </tr>
              `).join("")}
            </tbody>
          </table>
        </div>
      `;
    }

    function renderTracker() {
      const selected = state.primaryData?.country;
      const compared = state.compareData?.country;
      const players = allPlayers();
      els.status.hidden = true;
      els.content.hidden = false;
      els.title.textContent = selected ? `${selected.name}${compared ? ` vs ${compared.name}` : ""}` : "U21 Tracker";
      els.sub.textContent = [selected?.pool, compared?.pool].filter(Boolean).join(" - ");
      els.tables.classList.toggle("compare-active", Boolean(compared));
      renderCompareOptions();
      renderChart(players, allWeeks());
      els.tables.innerHTML = renderTable(selected?.name || "Primary team", decoratePlayers(state.primaryData, "primary"))
        + (compared ? renderTable(compared.name, decoratePlayers(state.compareData, "compare")) : "");
    }

    els.search.addEventListener("input", renderCountries);
    els.season.addEventListener("change", () => {
      const url = new URL(window.location.href);
      url.searchParams.set("season", els.season.value);
      window.location.assign(url.toString());
    });
    els.list.addEventListener("click", (ev) => {
      const btn = ev.target.closest("[data-country-id]");
      if (btn) selectCountry(btn.dataset.countryId);
    });
    els.compare.addEventListener("change", async () => {
      state.compareCountryId = els.compare.value ? Number(els.compare.value) : null;
      try {
        await refreshCompare();
        resetVisiblePlayers();
        renderTracker();
      } catch (err) {
        setError(err.message);
      }
    });
    els.showAll.addEventListener("click", () => {
      state.hiddenPlayers = new Set();
      renderTracker();
    });
    els.hideAll.addEventListener("click", () => {
      state.hiddenPlayers = new Set(allPlayers().map((player) => player.playerId));
      renderTracker();
    });
    els.tables.addEventListener("click", (ev) => {
      const row = ev.target.closest("[data-player-id]");
      const sort = ev.target.closest("[data-sort]");
      if (sort) {
        const key = sort.dataset.sort;
        if (state.sort.key === key) state.sort.dir = state.sort.dir === "asc" ? "desc" : "asc";
        else {
          state.sort.key = key;
          state.sort.dir = ["name", "position"].includes(key) ? "asc" : "desc";
        }
        renderTracker();
      } else if (row) {
        const id = Number(row.dataset.playerId);
        if (state.hiddenPlayers.has(id)) state.hiddenPlayers.delete(id);
        else state.hiddenPlayers.add(id);
        renderTracker();
      }
    });

    (async () => {
      try {
        state.meta = await loadJson(`/api/u21-tracker?season=${SEASON}`);
        els.lead.textContent = `Weekly DMI, game shape, and salary snapshots for U21 Round Robin pool countries. Season ${state.meta.season}. Weeks on file: ${(state.meta.weeks || []).join(", ") || "none"}.`;
        renderCountries();
        const israel = (state.meta.countries || []).find((country) => country.name.toLowerCase() === "israel");
        const first = israel || (state.meta.countries || [])[0];
        if (first) await selectCountry(first.countryId);
        else els.status.textContent = "No countries are available in this tracker snapshot.";
      } catch (err) {
        els.status.textContent = "Tracker data is not available.";
        setError(err.message);
      }
    })();
  </script>
</body>
</html>
"""


def _season_dir(season: int) -> Path:
    return LOCAL_TRACKER_ROOT / f"s{season}"


def _remote_url(season: int, filename: str) -> str:
    repo = os.environ.get("U21_TRACKER_GITHUB_REPO", DEFAULT_TRACKER_REPO)
    branch = os.environ.get("U21_TRACKER_GITHUB_BRANCH", DEFAULT_TRACKER_BRANCH)
    return f"https://raw.githubusercontent.com/{repo}/{branch}/data/u21-tracker/s{season}/{filename}"


def _read_json_local(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _read_json_remote(season: int, filename: str) -> dict[str, Any] | None:
    try:
        response = requests.get(_remote_url(season, filename), timeout=12)
        if response.status_code != 200:
            return None
        return response.json()
    except (requests.RequestException, ValueError):
        return None


def load_tracker_meta(season: int) -> dict[str, Any] | None:
    local = _read_json_local(_season_dir(season) / "meta.json")
    if local is not None:
        return local
    return _read_json_remote(season, "meta.json")


def load_tracker_week(season: int, week: int) -> dict[str, Any] | None:
    filename = f"w{week}.json"
    local = _read_json_local(_season_dir(season) / filename)
    if local is not None:
        return local
    return _read_json_remote(season, filename)


def list_local_weeks(season: int) -> list[int]:
    directory = _season_dir(season)
    if not directory.exists():
        return []
    weeks: list[int] = []
    for path in directory.glob("w*.json"):
        try:
            weeks.append(int(path.stem[1:]))
        except ValueError:
            continue
    return sorted(weeks)


def available_tracker_seasons() -> list[int]:
    seasons = {DEFAULT_CURRENT_SEASON}
    if LOCAL_TRACKER_ROOT.exists():
        for directory in LOCAL_TRACKER_ROOT.iterdir():
            if directory.is_dir() and directory.name.startswith("s"):
                try:
                    seasons.add(int(directory.name[1:]))
                except ValueError:
                    continue
    return sorted(seasons, reverse=True)


def load_country_series(season: int, country_id: int) -> dict[str, Any]:
    meta = load_tracker_meta(season)
    weeks = sorted(int(week) for week in (meta or {}).get("weeks", []) if str(week).isdigit())
    if not weeks:
        weeks = list_local_weeks(season)

    week_files: list[tuple[int, dict[str, Any]]] = []
    for week in weeks:
        week_file = load_tracker_week(season, week)
        if week_file is not None:
            week_files.append((week, week_file))

    country = None
    for item in (meta or {}).get("countries", []):
        if int(item.get("countryId", 0)) == country_id:
            country = {
                "countryId": int(item["countryId"]),
                "name": item.get("name", f"Country {country_id}"),
                "pool": item.get("pool", ""),
            }
            break

    by_player: dict[int, dict[str, Any]] = {}
    for week, week_file in week_files:
        country_file = next(
            (
                item
                for item in week_file.get("countries", [])
                if int(item.get("countryId", 0)) == country_id
            ),
            None,
        )
        if country_file is None:
            continue
        if country is None:
            country = {
                "countryId": int(country_file.get("countryId", country_id)),
                "name": country_file.get("name", f"Country {country_id}"),
                "pool": country_file.get("pool", ""),
            }
        for player in country_file.get("players", []):
            player_id = int(player.get("playerId", 0))
            if player_id <= 0:
                continue
            series = by_player.setdefault(
                player_id,
                {
                    "playerId": player_id,
                    "name": player.get("name", f"Player {player_id}"),
                    "position": player.get("position"),
                    "points": [],
                },
            )
            if player.get("name"):
                series["name"] = player["name"]
            series["points"].append(
                {
                    "week": week,
                    "position": player.get("position"),
                    "dmi": player.get("dmi"),
                    "gameShape": player.get("gameShape"),
                    "salary": player.get("salary"),
                    "scrapedAt": week_file.get("scrapedAt", ""),
                }
            )

    players = []
    for player in by_player.values():
        player["points"] = sorted(player["points"], key=lambda point: point["week"])
        player["position"] = player["points"][-1].get("position") if player["points"] else None
        players.append(player)
    players.sort(key=lambda player: str(player["name"]).casefold())

    return {
        "meta": meta,
        "country": country,
        "weeks": sorted(week for week, _ in week_files),
        "players": players,
    }


def _parse_positive_int(value: str | None, label: str) -> int:
    try:
        number = int(value or "")
    except ValueError as exc:
        raise ValueError(f"Invalid {label}") from exc
    if number < 1:
        raise ValueError(f"Invalid {label}")
    return number


@u21_tracker_bp.get("/u21-tracker")
def u21_tracker_page() -> str:
    try:
        selected_season = _parse_positive_int(request.args.get("season") or str(DEFAULT_CURRENT_SEASON), "season")
    except ValueError:
        selected_season = DEFAULT_CURRENT_SEASON
    seasons = available_tracker_seasons()
    if selected_season not in seasons:
        seasons.append(selected_season)
        seasons.sort(reverse=True)
    return render_template_string(
        TRACKER_HTML,
        current_season=selected_season,
        available_seasons=seasons,
    )


@u21_tracker_bp.get("/api/u21-tracker")
def api_u21_tracker() -> tuple[Any, int] | Any:
    try:
        season = _parse_positive_int(request.args.get("season") or str(DEFAULT_CURRENT_SEASON), "season")
        country_id_param = request.args.get("countryId") or request.args.get("country_id")
        if country_id_param is None:
            meta = load_tracker_meta(season)
            if not meta:
                return jsonify({"error": f"No U21 tracker data for season {season} yet"}), 404
            return jsonify(meta)

        country_id = _parse_positive_int(country_id_param, "countryId")
        series = load_country_series(season, country_id)
        if not series["country"] and not series["players"]:
            return jsonify({"error": f"No tracker data for country {country_id} in season {season}"}), 404
        return jsonify({"season": season, **series})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400
