#!/usr/bin/env python3

from __future__ import annotations

from argparse import Namespace
import contextlib
import io
from typing import Any

from flask import Flask, render_template_string, request

from bbapi import BBApi
from game import Game
from main import get_xml_text, parse_xml

app = Flask(__name__)


FORM_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>BBInsider Web Tool</title>
  <style>
    :root {
      --bg: #f6f8fb;
      --panel: #fff;
      --line: #d9e1ea;
      --ink: #1f2933;
      --muted: #607285;
      --accent: #0d47a1;
      --danger: #b42318;
      --shadow: 0 8px 26px rgba(16, 24, 40, 0.08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
      background: radial-gradient(circle at 10% 10%, #eef4ff 0%, transparent 35%), var(--bg);
      color: var(--ink);
    }
    .wrap {
      max-width: 760px;
      margin: 48px auto;
      padding: 0 18px;
    }
    .card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      box-shadow: var(--shadow);
      padding: 22px;
    }
    h1 {
      margin: 0 0 10px;
      font-size: 28px;
    }
    p {
      margin: 0 0 18px;
      color: var(--muted);
    }
    form {
      display: grid;
      gap: 12px;
    }
    label {
      font-size: 13px;
      font-weight: 600;
      color: #344054;
    }
    input {
      width: 100%;
      margin-top: 6px;
      padding: 10px 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      font-size: 14px;
      background: #fff;
    }
    button {
      margin-top: 8px;
      background: var(--accent);
      color: #fff;
      border: 0;
      border-radius: 10px;
      padding: 11px 14px;
      font-size: 14px;
      font-weight: 700;
      cursor: pointer;
    }
    .err {
      margin-bottom: 14px;
      border: 1px solid #f3c7c7;
      background: #fff1f1;
      color: var(--danger);
      border-radius: 10px;
      padding: 10px 12px;
      font-size: 14px;
    }
    .hint {
      margin-top: 10px;
      color: var(--muted);
      font-size: 12px;
    }
  </style>
</head>
<body>
  <main class="wrap">
    <section class="card">
      <h1>BBInsider Match Report</h1>
      <p>Enter your BBAPI credentials and a match ID to generate a full report.</p>
      {% if error %}
      <div class="err">{{ error }}</div>
      {% endif %}
      <form method="post" action="/report">
        <label>Username
          <input name="username" autocomplete="username" required value="{{ username }}" />
        </label>
        <label>Password
          <input name="password" type="password" autocomplete="current-password" required value="{{ password }}" />
        </label>
        <label>Match ID
          <input name="matchid" required value="{{ matchid }}" />
        </label>
        <button type="submit">Generate Report</button>
      </form>
      <div class="hint">Credentials are only used for this request (server memory only).</div>
    </section>
  </main>
</body>
</html>
"""


REPORT_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>BBInsider Match {{ matchid }}</title>
  <style>
    :root {
      --bg: #f7f7f2;
      --panel: #ffffff;
      --ink: #1f2328;
      --muted: #5f6b76;
      --line: #d9dee5;
      --home: #0d3b66;
      --away: #9a031e;
      --shadow: 0 10px 30px rgba(0, 0, 0, 0.08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at 10% 20%, #f0f5ff 0%, transparent 35%),
        radial-gradient(circle at 85% 0%, #fff0f0 0%, transparent 30%),
        var(--bg);
    }
    .wrap {
      max-width: 1200px;
      margin: 0 auto;
      padding: 24px;
    }
    .hero {
      background: linear-gradient(135deg, #ffffff, #f3f9ff);
      border: 1px solid var(--line);
      border-radius: 18px;
      box-shadow: var(--shadow);
      padding: 20px;
      margin-bottom: 18px;
    }
    .scoreboard {
      display: grid;
      grid-template-columns: 1fr auto 1fr;
      align-items: center;
      gap: 16px;
    }
    .team {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 14px;
    }
    .team h2 { margin: 0; font-size: 24px; line-height: 1.2; }
    .team small { color: var(--muted); }
    .team.home { border-left: 6px solid var(--home); }
    .team.away { border-left: 6px solid var(--away); }
    .score {
      text-align: center;
      font-size: 52px;
      font-weight: 900;
      line-height: 1;
      white-space: nowrap;
    }
    .small {
      color: var(--muted);
      font-size: 12px;
    }
    .card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      box-shadow: var(--shadow);
      overflow: hidden;
      margin-bottom: 18px;
    }
    .card h3 {
      margin: 0;
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      background: #fafcff;
      font-size: 15px;
    }
    .table-wrap {
      max-height: 480px;
      overflow: auto;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    th, td {
      border-bottom: 1px solid #eef1f5;
      padding: 8px 10px;
      text-align: right;
      white-space: nowrap;
    }
    th:first-child, td:first-child { text-align: left; }
    th {
      background: #f7f9fc;
      color: #36414b;
      font-weight: 700;
      position: sticky;
      top: 0;
      z-index: 1;
    }
    #offPlayersTable th:first-child,
    #offPlayersTable td:first-child {
      position: sticky;
      left: 0;
      z-index: 4;
      background: #fff;
      box-shadow: 2px 0 0 #eef1f5;
    }
    #offPlayersTable th:first-child {
      background: #f7f9fc;
      z-index: 6;
    }
    #offTeamsTable th:first-child,
    #offTeamsTable td:first-child {
      position: sticky;
      left: 0;
      z-index: 4;
      background: #fff;
      box-shadow: 2px 0 0 #eef1f5;
    }
    #offTeamsTable th:first-child {
      background: #f7f9fc;
      z-index: 6;
    }
    .cards {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
      margin-bottom: 18px;
    }
    .events-head {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 10px;
      padding: 12px;
      border-bottom: 1px solid var(--line);
      background: #fcfdff;
    }
    .events-head input,
    .events-head select {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 7px 9px;
      font-size: 13px;
      background: #fff;
    }
    .filter-block {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .multi-dd {
      position: relative;
      min-width: 220px;
    }
    .multi-dd-btn {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 7px 9px;
      font-size: 13px;
      background: #fff;
      color: var(--ink);
      text-align: left;
      cursor: pointer;
    }
    .multi-dd.open .multi-dd-btn {
      border-color: #9fb4cf;
      box-shadow: 0 0 0 2px rgba(13, 71, 161, 0.08);
    }
    .multi-dd-menu {
      display: none;
      position: absolute;
      top: calc(100% + 6px);
      left: 0;
      width: 100%;
      max-height: 260px;
      overflow: auto;
      background: #fff;
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      z-index: 20;
      padding: 6px;
    }
    .multi-dd.open .multi-dd-menu {
      display: block;
    }
    .multi-dd-item {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 13px;
      color: var(--ink);
      padding: 4px 2px;
    }
    .multi-dd-item.select-all {
      border-bottom: 1px solid #edf1f5;
      margin-bottom: 4px;
      padding-bottom: 6px;
      font-weight: 700;
    }
    .multi-dd-item input {
      margin: 0;
    }
    .off-legend {
      display: flex;
      gap: 14px;
      flex-wrap: wrap;
      padding: 10px 12px 12px;
      border-top: 1px solid var(--line);
      font-size: 12px;
      color: var(--muted);
      background: #fbfdff;
    }
    .off-legend .chip {
      font-weight: 700;
    }
    .off-a { color: #111827; }
    .off-m { color: #067647; }
    .off-mi { color: #b42318; }
    .off-b { color: #b54708; }
    .range-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
      padding: 12px;
    }
    .range-panel {
      border: 1px solid var(--line);
      border-radius: 10px;
      overflow: hidden;
      background: #fff;
    }
    .range-body {
      display: grid;
      grid-template-columns: 150px 1fr;
      gap: 12px;
      padding: 12px;
      align-items: center;
    }
    .pie-ring {
      width: 140px;
      height: 140px;
      border-radius: 50%;
      position: relative;
      margin: 0 auto;
    }
    .pie-hole {
      position: absolute;
      inset: 22px;
      border-radius: 50%;
      background: #fff;
      border: 1px solid #e7ebf0;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-direction: column;
      font-size: 12px;
      color: var(--muted);
      text-align: center;
      line-height: 1.2;
    }
    .pie-total {
      font-size: 20px;
      color: var(--ink);
      font-weight: 800;
    }
    .range-legend {
      display: grid;
      gap: 6px;
      font-size: 13px;
    }
    .range-legend .row {
      display: flex;
      align-items: center;
      gap: 8px;
      color: var(--ink);
    }
    .dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      flex: 0 0 10px;
    }
    .dot.three { background: #2563eb; }
    .dot.jump { background: #16a34a; }
    .dot.paint { background: #f97316; }
    .summary-grid {
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 8px;
      padding: 12px;
      border-bottom: 1px solid var(--line);
      background: #f8fbff;
    }
    .summary-card {
      background: #fff;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px;
    }
    .summary-card .k {
      font-size: 11px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    .summary-card .v {
      font-size: 18px;
      font-weight: 800;
      margin-top: 2px;
    }
    .events-feed {
      max-height: 520px;
      overflow: auto;
      padding: 10px;
      display: grid;
      gap: 8px;
    }
    .ev {
      border: 1px solid var(--line);
      border-left: 5px solid #1d5d9b;
      border-radius: 10px;
      padding: 8px 10px;
      background: #fff;
    }
    .ev.home { border-left-color: var(--home); }
    .ev.away { border-left-color: var(--away); }
    .meta {
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 4px;
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }
    .comment { margin: 0; font-size: 14px; line-height: 1.45; }
    .topbar {
      margin-bottom: 12px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
    }
    .topbar a {
      text-decoration: none;
      color: #0d47a1;
      font-size: 13px;
      font-weight: 600;
    }
    @media (max-width: 940px) {
      .scoreboard { grid-template-columns: 1fr; }
      .score { order: -1; font-size: 42px; }
      .cards { grid-template-columns: 1fr; }
      .range-grid { grid-template-columns: 1fr; }
      .range-body { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <main class="wrap">
    <div class="topbar">
      <div class="small">Match {{ matchid }} | BBAPI user: {{ username }}</div>
      <a href="/">Run another report</a>
    </div>

    <section class="hero">
      <div class="scoreboard">
        <article class="team home">
          <small>Home</small>
          <h2 id="homeName"></h2>
        </article>
        <div class="score" id="scoreline"></div>
        <article class="team away">
          <small>Away</small>
          <h2 id="awayName"></h2>
        </article>
      </div>
      <p class="small" id="summaryLine" style="margin: 12px 0 0;"></p>
    </section>

    <section class="cards">
      <article class="card">
        <h3>Team Totals</h3>
        <div class="table-wrap">
          <table id="teamTotalsTable"></table>
        </div>
      </article>
      <article class="card">
        <h3>Top Scorers</h3>
        <div class="table-wrap">
          <table id="topScorersTable"></table>
        </div>
      </article>
    </section>

    <section class="card">
      <h3>Player Box Score (Position Minutes)</h3>
      <div class="table-wrap">
        <table id="playersTable"></table>
      </div>
    </section>

    <section class="card">
      <h3>Offense Shot Profile By Player</h3>
      <div class="events-head">
        <label class="small">Team
          <select id="offTeamFilter">
            <option value="all">All</option>
            <option value="0">Home</option>
            <option value="1">Away</option>
          </select>
        </label>
      </div>
      <div class="table-wrap">
        <table id="offPlayersTable"></table>
      </div>
      <div class="off-legend">
        <span><span class="chip off-a">A</span> Attempts</span>
        <span><span class="chip off-m">M</span> Made</span>
        <span><span class="chip off-mi">MI</span> Missed</span>
        <span><span class="chip off-b">B</span> Blocked</span>
        <span>Cell format: <span class="off-a">A</span>/<span class="off-m">M</span>/<span class="off-mi">MI</span>/<span class="off-b">B</span></span>
      </div>
    </section>

    <section class="card">
      <h3>Team Shot Totals By Type</h3>
      <div class="table-wrap">
        <table id="offTeamsTable"></table>
      </div>
    </section>

    <section class="card">
      <h3>Shot Range Pie Charts</h3>
      <div class="range-grid">
        <article class="range-panel">
          <div class="events-head">
            <label class="small">Player
              <select id="rangePlayerFilter"></select>
            </label>
          </div>
          <div class="range-body">
            <div id="playerRangePie"></div>
            <div id="playerRangeLegend" class="range-legend"></div>
          </div>
        </article>
        <article class="range-panel">
          <div class="events-head">
            <label class="small">Team
              <select id="rangeTeamFilter">
                <option value="0">Home</option>
                <option value="1">Away</option>
              </select>
            </label>
          </div>
          <div class="range-body">
            <div id="teamRangePie"></div>
            <div id="teamRangeLegend" class="range-legend"></div>
          </div>
        </article>
      </div>
    </section>

    <section class="card">
      <h3>Defender Shot Analysis</h3>
      <div class="events-head">
        <div class="small filter-block">
          <span>Defender</span>
          <div id="defenderFilter"></div>
        </div>
        <div class="small filter-block">
          <span>Shot Type</span>
          <div id="defShotTypeFilter"></div>
        </div>
        <div class="small filter-block">
          <span>Result</span>
          <div id="defResultFilter"></div>
        </div>
        <span class="small" id="defShotsCount"></span>
      </div>
      <div class="summary-grid" id="defSummary"></div>
      <div class="table-wrap">
        <table id="defShotsTable"></table>
      </div>
    </section>

    <section class="card">
      <h3>Team Strengths & Weaknesses By Shot Type</h3>
      <div class="table-wrap">
        <table id="teamStrengthsTable"></table>
      </div>
    </section>

    <section class="card">
      <h3>Event Feed</h3>
      <div class="events-head">
        <label class="small">Team
          <select id="teamFilter">
            <option value="all">All</option>
            <option value="home">Home</option>
            <option value="away">Away</option>
          </select>
        </label>
        <label class="small">Contains text
          <input id="textFilter" type="text" placeholder="shot, foul, rebound..." />
        </label>
        <span class="small" id="eventCount"></span>
      </div>
      <div class="events-feed" id="eventsFeed"></div>
    </section>
  </main>

  <script>
    const data = {{ report_json | tojson }};

    const home = data.teamHome;
    const away = data.teamAway;
    const homeT = home.stats.total;
    const awayT = away.stats.total;

    document.getElementById("homeName").textContent = home.name;
    document.getElementById("awayName").textContent = away.name;
    document.getElementById("scoreline").textContent = `${homeT.pts} : ${awayT.pts}`;

    const winner = homeT.pts === awayT.pts
      ? "Draw"
      : (homeT.pts > awayT.pts ? `${home.name} won` : `${away.name} won`);

    document.getElementById("summaryLine").textContent =
      `${winner} by ${Math.abs(homeT.pts - awayT.pts)} points. ${data.events.length} tracked events.`;

    const pct = (made, att) => att ? `${((made / att) * 100).toFixed(1)}%` : "0.0%";
    const fmtFg = (t) => `${t.fgm}/${t.fga} (${pct(t.fgm, t.fga)})`;
    const fmtTp = (t) => `${t.tpm}/${t.tpa} (${pct(t.tpm, t.tpa)})`;
    const fmtFt = (t) => `${t.ftm}/${t.fta} (${pct(t.ftm, t.fta)})`;
    const secsToMin = (secs) => `${Math.floor((secs || 0) / 60)}:${String((secs || 0) % 60).padStart(2, "0")}`;
    const shotTypeLabel = {
      "100": "3PT Default",
      "101": "3PT Top Key",
      "102": "3PT Wing",
      "103": "3PT Corner",
      "104": "3PT Long",
      "105": "3PT Halfcourt",
      "200": "2PT Default",
      "201": "2PT Elbow",
      "202": "2PT Wing",
      "203": "2PT Baseline",
      "204": "2PT Top Key",
      "401": "Dunk",
      "402": "Layup",
      "403": "Post Move",
      "404": "Fade Away",
      "405": "Hook",
      "406": "Off Dribble J",
      "407": "Putback Dunk",
      "408": "Tip-in",
      "409": "Rebound Shot",
      "410": "Dunk",
      "411": "Driving Layup"
    };
    const shotResultLabel = {
      "0": "Missed",
      "1": "Scored",
      "2": "Goaltend",
      "3": "Blocked",
      "4": "Missed + Foul",
      "5": "Scored + Foul"
    };
    const madeResults = new Set(["1", "2", "5"]);
    const missedResults = new Set(["0", "4"]);
    const blockedResults = new Set(["3"]);

    function renderTeamTotals() {
      const rows = [
        ["Points", homeT.pts, awayT.pts],
        ["Field Goals", fmtFg(homeT), fmtFg(awayT)],
        ["3PT", fmtTp(homeT), fmtTp(awayT)],
        ["Free Throws", fmtFt(homeT), fmtFt(awayT)],
        ["Rebounds", homeT.tr, awayT.tr],
        ["Off Rebounds", homeT.or, awayT.or],
        ["Def Rebounds", homeT.dr, awayT.dr],
        ["Assists", homeT.ast, awayT.ast],
        ["Turnovers", homeT.to, awayT.to],
        ["Steals", homeT.stl, awayT.stl],
        ["Blocks", homeT.blk, awayT.blk],
        ["Fouls", homeT.pf, awayT.pf]
      ];

      document.getElementById("teamTotalsTable").innerHTML = `
        <thead>
          <tr>
            <th>Stat</th><th>${home.name}</th><th>${away.name}</th>
          </tr>
        </thead>
        <tbody>
          ${rows.map(r => `<tr><td>${r[0]}</td><td>${r[1]}</td><td>${r[2]}</td></tr>`).join("")}
        </tbody>
      `;
    }

    function playerRows(team) {
      return team.players.map(p => {
        const t = p.stats.total;
        return {
          team: team.name,
          name: p.name,
          starter: !!p.starter,
          mins: t.mins,
          pg: secsToMin(t.secs_pg),
          sg: secsToMin(t.secs_sg),
          sf: secsToMin(t.secs_sf),
          pf_pos: secsToMin(t.secs_pf),
          c: secsToMin(t.secs_c),
          pts: t.pts,
          fg: `${t.fgm}/${t.fga}`,
          tp: `${t.tpm}/${t.tpa}`,
          ft: `${t.ftm}/${t.fta}`,
          tr: t.tr,
          ast: t.ast,
          to: t.to,
          stl: t.stl,
          blk: t.blk,
          fls: t.pf,
          pm: t["+/-"]
        };
      });
    }

    const allPlayers = [...playerRows(home), ...playerRows(away)];
    const shotEvents = data.events.filter(ev => ev.event_type === "shot");
    const offTeamFilter = document.getElementById("offTeamFilter");
    const rangePlayerFilter = document.getElementById("rangePlayerFilter");
    const rangeTeamFilter = document.getElementById("rangeTeamFilter");

    function renderTopScorers() {
      const top = [...allPlayers].sort((a, b) => b.pts - a.pts || b.ast - a.ast).slice(0, 12);
      document.getElementById("topScorersTable").innerHTML = `
        <thead>
          <tr>
            <th>Player</th><th>Team</th><th>PTS</th><th>FG</th><th>3PT</th><th>FT</th>
          </tr>
        </thead>
        <tbody>
          ${top.map(p => `<tr>
            <td>${p.name}${p.starter ? " *" : ""}</td>
            <td>${p.team}</td>
            <td>${p.pts}</td>
            <td>${p.fg}</td>
            <td>${p.tp}</td>
            <td>${p.ft}</td>
          </tr>`).join("")}
        </tbody>
      `;
    }

    function renderPlayersTable() {
      const sorted = [...allPlayers].sort((a, b) => b.pts - a.pts || b.tr - a.tr || b.ast - a.ast);
      document.getElementById("playersTable").innerHTML = `
        <thead>
          <tr>
            <th>Player</th><th>Team</th><th>MIN</th><th>PG</th><th>SG</th><th>SF</th><th>PF</th><th>C</th>
            <th>PTS</th><th>FG</th><th>3PT</th><th>FT</th><th>REB</th><th>AST</th><th>TO</th><th>STL</th><th>BLK</th><th>FLS</th><th>+/-</th>
          </tr>
        </thead>
        <tbody>
          ${sorted.map(p => `<tr>
            <td>${p.name}${p.starter ? " *" : ""}</td>
            <td>${p.team}</td>
            <td>${p.mins}</td>
            <td>${p.pg}</td>
            <td>${p.sg}</td>
            <td>${p.sf}</td>
            <td>${p.pf_pos}</td>
            <td>${p.c}</td>
            <td>${p.pts}</td>
            <td>${p.fg}</td>
            <td>${p.tp}</td>
            <td>${p.ft}</td>
            <td>${p.tr}</td>
            <td>${p.ast}</td>
            <td>${p.to}</td>
            <td>${p.stl}</td>
            <td>${p.blk}</td>
            <td>${p.fls}</td>
            <td>${p.pm}</td>
          </tr>`).join("")}
        </tbody>
      `;
    }

    function periodFromClock(gameclock) {
      if (typeof gameclock !== "number") return "?";
      if (gameclock < 0) return "End";
      if (gameclock < 720) return "Q1";
      if (gameclock < 1440) return "Q2";
      if (gameclock < 2160) return "Q3";
      if (gameclock < 2880) return "Q4";
      return "OT";
    }

    function eventSide(teamId) {
      return teamId === 0 ? "home" : "away";
    }

    function formatComments(comments) {
      if (!Array.isArray(comments) || comments.length === 0) return "(no commentary)";
      return comments.join(" ");
    }

    function zeroOffCell() {
      return { a: 0, m: 0, mi: 0, b: 0 };
    }

    function addOffStat(cell, resultCode) {
      const rc = String(resultCode);
      cell.a += 1;
      if (madeResults.has(rc)) cell.m += 1;
      else if (blockedResults.has(rc)) cell.b += 1;
      else if (missedResults.has(rc)) cell.mi += 1;
      else cell.mi += 1;
    }

    function offCellHtml(cell) {
      return `<span class="off-a">${cell.a}</span>/<span class="off-m">${cell.m}</span>/<span class="off-mi">${cell.mi}</span>/<span class="off-b">${cell.b}</span>`;
    }

    function sumOffCells(cellsByType, typeCodes) {
      const out = zeroOffCell();
      typeCodes.forEach(code => {
        out.a += cellsByType[code].a;
        out.m += cellsByType[code].m;
        out.mi += cellsByType[code].mi;
        out.b += cellsByType[code].b;
      });
      return out;
    }

    function renderOffenseShotProfile() {
      const typeCodes = [...new Set(shotEvents.map(ev => String(ev.shot_type)).filter(Boolean))]
        .sort((a, b) => Number(a) - Number(b));
      const teamFilterVal = offTeamFilter.value;

      const playerRowsData = [];
      const teamCounts = {
        0: Object.fromEntries(typeCodes.map(code => [code, zeroOffCell()])),
        1: Object.fromEntries(typeCodes.map(code => [code, zeroOffCell()]))
      };

      [home, away].forEach((teamObj, side) => {
        teamObj.players.forEach((player, playerIdx) => {
          const counts = Object.fromEntries(typeCodes.map(code => [code, zeroOffCell()]));

          shotEvents.forEach(ev => {
            if (Number(ev.attacking_team) !== side) return;
            const idx = normalizeSlot(ev.attacker, teamObj.players.length);
            if (idx !== playerIdx) return;
            const code = String(ev.shot_type);
            if (!(code in counts)) return;
            addOffStat(counts[code], ev.shot_result);
          });

          typeCodes.forEach(code => {
            teamCounts[side][code].a += counts[code].a;
            teamCounts[side][code].m += counts[code].m;
            teamCounts[side][code].mi += counts[code].mi;
            teamCounts[side][code].b += counts[code].b;
          });

          const total = sumOffCells(counts, typeCodes);
          playerRowsData.push({
            side,
            name: player.name,
            team: teamObj.name,
            counts,
            total
          });
        });
      });

      const visiblePlayers = playerRowsData
        .filter(row => teamFilterVal === "all" || Number(teamFilterVal) === row.side)
        .sort((a, b) => b.total.a - a.total.a || a.name.localeCompare(b.name));

      const offPlayersTable = document.getElementById("offPlayersTable");
      offPlayersTable.innerHTML = `
        <thead>
          <tr>
            <th>Player</th>
            <th>Team</th>
            ${typeCodes.map(code => `<th>${shotTypeLabel[code] || code}</th>`).join("")}
            <th>Total</th>
          </tr>
        </thead>
        <tbody>
          ${visiblePlayers.map(row => `
            <tr>
              <td>${row.name}</td>
              <td>${row.team}</td>
              ${typeCodes.map(code => `<td>${offCellHtml(row.counts[code])}</td>`).join("")}
              <td><strong>${offCellHtml(row.total)}</strong></td>
            </tr>
          `).join("")}
        </tbody>
      `;

      const combined = Object.fromEntries(typeCodes.map(code => [code, {
        a: teamCounts[0][code].a + teamCounts[1][code].a,
        m: teamCounts[0][code].m + teamCounts[1][code].m,
        mi: teamCounts[0][code].mi + teamCounts[1][code].mi,
        b: teamCounts[0][code].b + teamCounts[1][code].b
      }]));
      const homeTotal = sumOffCells(teamCounts[0], typeCodes);
      const awayTotal = sumOffCells(teamCounts[1], typeCodes);
      const gameTotal = {
        a: homeTotal.a + awayTotal.a,
        m: homeTotal.m + awayTotal.m,
        mi: homeTotal.mi + awayTotal.mi,
        b: homeTotal.b + awayTotal.b
      };

      const offTeamsTable = document.getElementById("offTeamsTable");
      offTeamsTable.innerHTML = `
        <thead>
          <tr>
            <th>Team</th>
            ${typeCodes.map(code => `<th>${shotTypeLabel[code] || code}</th>`).join("")}
            <th>Total</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>${home.name}</td>
            ${typeCodes.map(code => `<td>${offCellHtml(teamCounts[0][code])}</td>`).join("")}
            <td><strong>${offCellHtml(homeTotal)}</strong></td>
          </tr>
          <tr>
            <td>${away.name}</td>
            ${typeCodes.map(code => `<td>${offCellHtml(teamCounts[1][code])}</td>`).join("")}
            <td><strong>${offCellHtml(awayTotal)}</strong></td>
          </tr>
          <tr>
            <td><strong>Game Total</strong></td>
            ${typeCodes.map(code => `<td><strong>${offCellHtml(combined[code])}</strong></td>`).join("")}
            <td><strong>${offCellHtml(gameTotal)}</strong></td>
          </tr>
        </tbody>
      `;
    }

    function getShotRange(code) {
      const label = shotTypeLabel[String(code)] || String(code);
      if (label.includes("3PT")) return "three";
      if (label.includes("2PT")) return "jump";
      return "paint";
    }

    function emptyRangeCounts() {
      return { three: 0, jump: 0, paint: 0 };
    }

    function sumRangeCounts(counts) {
      return counts.three + counts.jump + counts.paint;
    }

    function pctRange(v, total) {
      return total ? `${((v / total) * 100).toFixed(1)}%` : "0.0%";
    }

    function renderPie(targetId, legendId, title, counts) {
      const total = sumRangeCounts(counts);
      const pThree = total ? (counts.three / total) * 100 : 0;
      const pJump = total ? (counts.jump / total) * 100 : 0;
      const cut1 = pThree;
      const cut2 = pThree + pJump;
      const bg = total === 0
        ? "conic-gradient(#e5e7eb 0 100%)"
        : `conic-gradient(#2563eb 0 ${cut1}%, #16a34a ${cut1}% ${cut2}%, #f97316 ${cut2}% 100%)`;

      document.getElementById(targetId).innerHTML = `
        <div class="pie-ring" style="background: ${bg};">
          <div class="pie-hole">
            <div class="pie-total">${total}</div>
            <div>${title}</div>
          </div>
        </div>
      `;

      document.getElementById(legendId).innerHTML = `
        <div class="row"><span class="dot three"></span>Three: <strong>${counts.three}</strong> (${pctRange(counts.three, total)})</div>
        <div class="row"><span class="dot jump"></span>Jump: <strong>${counts.jump}</strong> (${pctRange(counts.jump, total)})</div>
        <div class="row"><span class="dot paint"></span>Paint: <strong>${counts.paint}</strong> (${pctRange(counts.paint, total)})</div>
      `;
    }

    function populateRangeFilters() {
      rangePlayerFilter.innerHTML = [
        ...home.players.map((p, i) => `<option value="0:${i}">${p.name} (${home.name})</option>`),
        ...away.players.map((p, i) => `<option value="1:${i}">${p.name} (${away.name})</option>`)
      ].join("");
    }

    function renderRangeCharts() {
      const [psideRaw, pslotRaw] = rangePlayerFilter.value.split(":");
      const pside = Number(psideRaw);
      const pslot = Number(pslotRaw);
      const pTeam = getTeamBySide(pside);
      const playerCounts = emptyRangeCounts();

      shotEvents.forEach(ev => {
        if (Number(ev.attacking_team) !== pside) return;
        const idx = normalizeSlot(ev.attacker, pTeam.players.length);
        if (idx !== pslot) return;
        playerCounts[getShotRange(ev.shot_type)] += 1;
      });

      renderPie("playerRangePie", "playerRangeLegend", "player shots", playerCounts);

      const tside = Number(rangeTeamFilter.value);
      const teamCounts = emptyRangeCounts();
      shotEvents.forEach(ev => {
        if (Number(ev.attacking_team) !== tside) return;
        teamCounts[getShotRange(ev.shot_type)] += 1;
      });

      renderPie("teamRangePie", "teamRangeLegend", "team shots", teamCounts);
    }

    function getTeamBySide(side) {
      return side === 0 ? home : away;
    }

    function normalizeSlot(rawSlot, playersLen) {
      const n = Number(rawSlot);
      if (!Number.isFinite(n)) return null;
      if (n >= 1 && n <= playersLen) return n - 1;
      if (n === 0) return null;
      return null;
    }

    function resolvePlayerName(teamObj, rawSlot, fallback) {
      if (!teamObj || !Array.isArray(teamObj.players)) return fallback;
      const idx = normalizeSlot(rawSlot, teamObj.players.length);
      if (idx === null) return fallback;
      return teamObj.players[idx]?.name || fallback;
    }

    const defenderFilter = document.getElementById("defenderFilter");
    const defShotTypeFilter = document.getElementById("defShotTypeFilter");
    const defResultFilter = document.getElementById("defResultFilter");
    const defSummary = document.getElementById("defSummary");
    const defShotsTable = document.getElementById("defShotsTable");
    const defShotsCount = document.getElementById("defShotsCount");
    const teamStrengthsTable = document.getElementById("teamStrengthsTable");
    const defenderFilterState = { options: [] };
    const shotTypeFilterState = { options: [] };
    const resultFilterState = { options: [] };

    function selectedValues(filterRoot) {
      return new Set(
        [...filterRoot.querySelectorAll("input[data-role='item']:checked")]
          .map(node => node.value)
      );
    }

    function updateFilterButtonLabel(filterRoot, options) {
      const button = filterRoot.querySelector(".multi-dd-btn");
      const selected = selectedValues(filterRoot);
      const total = options.length;
      if (selected.size === 0) {
        button.textContent = "None selected";
        return;
      }
      if (selected.size === total) {
        button.textContent = "All selected";
        return;
      }
      if (selected.size === 1) {
        const selectedVal = [...selected][0];
        const found = options.find(o => o.value === selectedVal);
        button.textContent = found ? found.label : "1 selected";
        return;
      }
      button.textContent = `${selected.size} selected`;
    }

    function syncSelectAllCheckbox(filterRoot) {
      const allBox = filterRoot.querySelector("input[data-role='all']");
      const allItems = [...filterRoot.querySelectorAll("input[data-role='item']")];
      const checkedCount = allItems.filter(node => node.checked).length;
      allBox.checked = checkedCount === allItems.length;
      allBox.indeterminate = checkedCount > 0 && checkedCount < allItems.length;
    }

    function initMultiDropdown(filterRoot, options, onChange) {
      filterRoot.className = "multi-dd";
      filterRoot.innerHTML = "";
      const button = document.createElement("button");
      button.type = "button";
      button.className = "multi-dd-btn";
      button.textContent = "All selected";
      const menu = document.createElement("div");
      menu.className = "multi-dd-menu";

      const allRow = document.createElement("label");
      allRow.className = "multi-dd-item select-all";
      const allBox = document.createElement("input");
      allBox.type = "checkbox";
      allBox.checked = true;
      allBox.dataset.role = "all";
      const allText = document.createElement("span");
      allText.textContent = "Select all";
      allRow.appendChild(allBox);
      allRow.appendChild(allText);
      menu.appendChild(allRow);

      options.forEach(opt => {
        const row = document.createElement("label");
        row.className = "multi-dd-item";
        const cb = document.createElement("input");
        cb.type = "checkbox";
        cb.checked = true;
        cb.value = opt.value;
        cb.dataset.role = "item";
        const text = document.createElement("span");
        text.textContent = opt.label;
        row.appendChild(cb);
        row.appendChild(text);
        menu.appendChild(row);
      });

      filterRoot.appendChild(button);
      filterRoot.appendChild(menu);

      button.addEventListener("click", (ev) => {
        ev.stopPropagation();
        document.querySelectorAll(".multi-dd.open").forEach(node => {
          if (node !== filterRoot) node.classList.remove("open");
        });
        filterRoot.classList.toggle("open");
      });

      menu.addEventListener("click", (ev) => ev.stopPropagation());

      allBox.addEventListener("change", () => {
        const allItems = filterRoot.querySelectorAll("input[data-role='item']");
        allItems.forEach(node => { node.checked = allBox.checked; });
        syncSelectAllCheckbox(filterRoot);
        updateFilterButtonLabel(filterRoot, options);
        onChange();
      });

      menu.querySelectorAll("input[data-role='item']").forEach(node => {
        node.addEventListener("change", () => {
          syncSelectAllCheckbox(filterRoot);
          updateFilterButtonLabel(filterRoot, options);
          onChange();
        });
      });

      syncSelectAllCheckbox(filterRoot);
      updateFilterButtonLabel(filterRoot, options);
    }

    function setupDefenderFilters() {
      defenderFilterState.options = [
        ...home.players.map((p, i) => ({ value: `0:${i}`, label: `${p.name} (${home.name})` })),
        ...away.players.map((p, i) => ({ value: `1:${i}`, label: `${p.name} (${away.name})` }))
      ];
      shotTypeFilterState.options = [...new Set(shotEvents.map(ev => String(ev.shot_type)).filter(Boolean))]
        .sort((a, b) => Number(a) - Number(b))
        .map(code => ({ value: code, label: shotTypeLabel[code] || code }));
      resultFilterState.options = Object.entries(shotResultLabel).map(([k, v]) => ({ value: k, label: v }));

      initMultiDropdown(defenderFilter, defenderFilterState.options, renderDefenderShotPanel);
      initMultiDropdown(defShotTypeFilter, shotTypeFilterState.options, renderDefenderShotPanel);
      initMultiDropdown(defResultFilter, resultFilterState.options, renderDefenderShotPanel);
    }

    function renderDefenderShotPanel() {
      const selectedDefenders = selectedValues(defenderFilter);
      const selectedShotTypes = selectedValues(defShotTypeFilter);
      const selectedResults = selectedValues(defResultFilter);

      const defenderShots = shotEvents.filter(ev => {
        const side = Number(ev.defending_team);
        const defTeam = getTeamBySide(side);
        const idx = normalizeSlot(ev.defender, defTeam.players.length);
        if (idx === null) return false;
        if (selectedDefenders.size === 0) return true;
        return selectedDefenders.has(`${side}:${idx}`);
      });

      const filtered = defenderShots.filter(ev => {
        if (selectedShotTypes.size > 0 && !selectedShotTypes.has(String(ev.shot_type))) return false;
        if (selectedResults.size > 0 && !selectedResults.has(String(ev.shot_result))) return false;
        return true;
      });

      const madeCount = filtered.filter(ev => ["1", "2", "5"].includes(String(ev.shot_result))).length;
      const missedCount = filtered.filter(ev => ["0", "3", "4"].includes(String(ev.shot_result))).length;
      const blockedCount = filtered.filter(ev => String(ev.shot_result) === "3").length;
      const foulCount = filtered.filter(ev => ["4", "5"].includes(String(ev.shot_result))).length;
      const fgPct = filtered.length ? ((madeCount / filtered.length) * 100).toFixed(1) + "%" : "0.0%";

      defSummary.innerHTML = `
        <div class="summary-card"><div class="k">Total Shots Defended</div><div class="v">${filtered.length}</div></div>
        <div class="summary-card"><div class="k">Made Against</div><div class="v">${madeCount}</div></div>
        <div class="summary-card"><div class="k">Missed Against</div><div class="v">${missedCount}</div></div>
        <div class="summary-card"><div class="k">Blocked</div><div class="v">${blockedCount}</div></div>
        <div class="summary-card"><div class="k">With Foul</div><div class="v">${foulCount}</div></div>
        <div class="summary-card"><div class="k">FG% Allowed</div><div class="v">${fgPct}</div></div>
      `;

      defShotsCount.textContent = `${filtered.length} shown (${defenderShots.length} total across selected defenders)`;

      defShotsTable.innerHTML = `
        <thead>
          <tr>
            <th>#</th><th>Q</th><th>GameClock</th><th>Shooter</th><th>Team</th><th>Shot Type</th><th>Result</th><th>Comment</th>
          </tr>
        </thead>
        <tbody>
          ${filtered.slice().reverse().map((ev, idx) => {
            const attTeam = getTeamBySide(Number(ev.attacking_team));
            const shooter = resolvePlayerName(attTeam, ev.attacker, `#${ev.attacker}`);
            const sideName = attTeam.name;
            const typeLabel = shotTypeLabel[String(ev.shot_type)] || String(ev.shot_type);
            const resultLabel = shotResultLabel[String(ev.shot_result)] || String(ev.shot_result);
            return `<tr>
              <td>${filtered.length - idx}</td>
              <td>${periodFromClock(ev.gameclock)}</td>
              <td>${ev.gameclock}</td>
              <td>${shooter}</td>
              <td>${sideName}</td>
              <td>${typeLabel}</td>
              <td>${resultLabel}</td>
              <td>${formatComments(ev.comments)}</td>
            </tr>`;
          }).join("")}
        </tbody>
      `;
    }

    function rangeLabel(rangeKey) {
      if (rangeKey === "three") return "Three";
      if (rangeKey === "jump") return "Jump";
      return "Paint";
    }

    function buildOffenseByRange(teamSide) {
      const teamObj = getTeamBySide(teamSide);
      const out = {};
      ["three", "jump", "paint"].forEach(range => {
        out[range] = teamObj.players.map(player => ({
          name: player.name,
          a: 0,
          m: 0
        }));
      });

      shotEvents.forEach(ev => {
        if (Number(ev.attacking_team) !== teamSide) return;
        const idx = normalizeSlot(ev.attacker, teamObj.players.length);
        if (idx === null) return;
        const range = getShotRange(ev.shot_type);
        if (!(range in out)) return;
        out[range][idx].a += 1;
        if (madeResults.has(String(ev.shot_result))) out[range][idx].m += 1;
      });

      return out;
    }

    function buildDefenseByRange(teamSide) {
      const teamObj = getTeamBySide(teamSide);
      const out = {};
      ["three", "jump", "paint"].forEach(range => {
        out[range] = teamObj.players.map(player => ({
          name: player.name,
          a: 0,
          m: 0
        }));
      });

      shotEvents.forEach(ev => {
        if (Number(ev.defending_team) !== teamSide) return;
        const idx = normalizeSlot(ev.defender, teamObj.players.length);
        if (idx === null) return;
        const range = getShotRange(ev.shot_type);
        if (!(range in out)) return;
        out[range][idx].a += 1;
        if (madeResults.has(String(ev.shot_result))) out[range][idx].m += 1;
      });

      return out;
    }

    function pickByFg(entries, preferLow) {
      const withAttempts = entries.filter(e => e.a > 0);
      if (withAttempts.length === 0) return null;

      const ranked = withAttempts
        .map(e => ({
          ...e,
          pct: (e.m / e.a) * 100
        }))
        .sort((a, b) => {
          if (preferLow) {
            if (a.pct !== b.pct) return a.pct - b.pct;
            return b.a - a.a;
          }
          if (a.pct !== b.pct) return b.pct - a.pct;
          return b.a - a.a;
        });

      return ranked[0];
    }

    function formatFgCell(item, mode) {
      if (!item) return "N/A";
      const pctVal = item.a ? ((item.m / item.a) * 100).toFixed(1) : "0.0";
      const suffix = mode === "def" ? " allowed" : "";
      return `${item.name} - ${pctVal}%${suffix} (${item.m}/${item.a})`;
    }

    function renderStrengthWeaknessView() {
      const ranges = ["three", "jump", "paint"];
      const rows = [];

      [0, 1].forEach(side => {
        const teamObj = getTeamBySide(side);
        const offByRange = buildOffenseByRange(side);
        const defByRange = buildDefenseByRange(side);

        ranges.forEach(range => {
          const offStrength = pickByFg(offByRange[range], false);
          const offWeakness = pickByFg(offByRange[range], true);
          const defStrength = pickByFg(defByRange[range], true);
          const defWeakness = pickByFg(defByRange[range], false);

          rows.push({
            team: teamObj.name,
            shotType: rangeLabel(range),
            offStrength,
            offWeakness,
            defStrength,
            defWeakness
          });
        });
      });

      teamStrengthsTable.innerHTML = `
        <thead>
          <tr>
            <th>Team</th>
            <th>Shot Range</th>
            <th>Offensive Strength (High FG%)</th>
            <th>Offensive Weakness (Low FG%)</th>
            <th>Defensive Strength (Low FG% Allowed)</th>
            <th>Defensive Weakness (High FG% Allowed)</th>
          </tr>
        </thead>
        <tbody>
          ${rows.map(row => `
            <tr>
              <td>${row.team}</td>
              <td>${row.shotType}</td>
              <td>${formatFgCell(row.offStrength, "off")}</td>
              <td>${formatFgCell(row.offWeakness, "off")}</td>
              <td>${formatFgCell(row.defStrength, "def")}</td>
              <td>${formatFgCell(row.defWeakness, "def")}</td>
            </tr>
          `).join("")}
        </tbody>
      `;
    }

    const eventsFeed = document.getElementById("eventsFeed");
    const teamFilter = document.getElementById("teamFilter");
    const textFilter = document.getElementById("textFilter");
    const eventCount = document.getElementById("eventCount");

    function renderEvents() {
      const teamVal = teamFilter.value;
      const textVal = textFilter.value.trim().toLowerCase();
      const filtered = data.events.filter(ev => {
        const side = eventSide(ev.attacking_team);
        if (teamVal !== "all" && side !== teamVal) return false;
        if (!textVal) return true;
        const text = `${formatComments(ev.comments)} ${ev.event_type}`.toLowerCase();
        return text.includes(textVal);
      });

      eventCount.textContent = `${filtered.length} shown`;

      eventsFeed.innerHTML = filtered.slice().reverse().map((ev, idx) => {
        const side = eventSide(ev.attacking_team);
        const teamName = side === "home" ? home.name : away.name;
        return `
          <article class="ev ${side}">
            <div class="meta">
              <span>#${filtered.length - idx}</span>
              <span>${periodFromClock(ev.gameclock)}</span>
              <span>GameClock: ${ev.gameclock}</span>
              <span>ShotClock: ${ev.shotclock}</span>
              <span>Team: ${teamName}</span>
              <span>Type: ${ev.event_type}</span>
            </div>
            <p class="comment">${formatComments(ev.comments)}</p>
          </article>
        `;
      }).join("");
    }

    teamFilter.addEventListener("change", renderEvents);
    textFilter.addEventListener("input", renderEvents);
    offTeamFilter.addEventListener("change", renderOffenseShotProfile);
    rangePlayerFilter.addEventListener("change", renderRangeCharts);
    rangeTeamFilter.addEventListener("change", renderRangeCharts);
    document.addEventListener("click", () => {
      document.querySelectorAll(".multi-dd.open").forEach(node => node.classList.remove("open"));
    });

    renderTeamTotals();
    renderTopScorers();
    renderPlayersTable();
    renderOffenseShotProfile();
    populateRangeFilters();
    renderRangeCharts();
    setupDefenderFilters();
    renderDefenderShotPanel();
    renderStrengthWeaknessView();
    renderEvents();
  </script>
</body>
</html>
"""


def serialize_game(game: Game) -> dict[str, Any]:
    teams: list[dict[str, Any]] = []
    for team in game.teams:
        players = []
        for player in team.players:
            stats: dict[str, Any] = {}
            for qtr, stat in enumerate(player.stats.qtr, start=1):
                stats[f"q{qtr}"] = stat.player_stats()
            stats["total"] = player.stats.full.player_stats()

            players.append(
                {
                    "id": player.id,
                    "name": player.name,
                    "starter": player.starter,
                    "stats": stats,
                }
            )

        team_stats: dict[str, Any] = {}
        for qtr, stat in enumerate(team.stats.qtr, start=1):
            team_stats[f"q{qtr}"] = stat.team_stats()
        team_stats["total"] = team.stats.full.team_stats()

        teams.append(
            {"id": team.id, "name": team.name, "players": players, "stats": team_stats}
        )

    events = [event.to_json() for event in game.baseevents]
    return {"teamHome": teams[0], "teamAway": teams[1], "events": events}


def generate_report(matchid: str, username: str, password: str) -> dict[str, Any]:
    api = BBApi(username, password)
    if not getattr(api, "logged_in", False):
        raise ValueError("BBAPI login failed. Check username/password.")

    # Ensure at least one authenticated BBAPI call succeeds.
    api.boxscore(matchid=int(matchid))

    # Silence verbose debug prints from parsing/game simulation in web mode.
    with contextlib.redirect_stdout(io.StringIO()):
        text = get_xml_text(matchid)
        events, home_team, away_team = parse_xml(text)

        args = Namespace(
            matchid=matchid,
            username=username,
            password=password,
            print_events=False,
            print_stats=False,
            save_charts=False,
            verify=False,
        )
        game = Game(matchid, events, home_team, away_team, args, [])
        game.play()
    return serialize_game(game)


@app.get("/")
def form() -> str:
    return render_template_string(
        FORM_HTML, error="", username="", password="", matchid="138595249"
    )


@app.post("/report")
def report() -> tuple[str, int] | str:
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()
    matchid = request.form.get("matchid", "").strip()

    if not username or not password or not matchid:
        return (
            render_template_string(
                FORM_HTML,
                error="All fields are required.",
                username=username,
                password=password,
                matchid=matchid,
            ),
            400,
        )

    if not matchid.isdigit():
        return (
            render_template_string(
                FORM_HTML,
                error="Match ID must be numeric.",
                username=username,
                password=password,
                matchid=matchid,
            ),
            400,
        )

    try:
        report_json = generate_report(matchid, username, password)
    except Exception as exc:
        return (
            render_template_string(
                FORM_HTML,
                error=f"Failed to generate report: {exc}",
                username=username,
                password="",
                matchid=matchid,
            ),
            500,
        )

    return render_template_string(
        REPORT_HTML, report_json=report_json, matchid=matchid, username=username
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
