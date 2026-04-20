#!/usr/bin/env python3

from __future__ import annotations

from argparse import Namespace
import base64
import contextlib
import io
import json
from pathlib import Path
import re
from typing import Any

from flask import Flask, jsonify, render_template_string, request

from bbapi import BBApi
from game import Game
from main import get_xml_text, parse_xml

app = Flask(__name__)

LOCAL_NATIONAL_OPTIONS_PATH = Path(__file__).with_name("national_options.json")


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
    input,
    select {
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
    input[type="checkbox"],
    input[type="radio"] {
      width: auto;
      margin: 0;
    }
    .mode-switch {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
      margin-bottom: 6px;
    }
    .mode-btn {
      border: 1px solid var(--line);
      background: #f8fbff;
      color: var(--ink);
    }
    .mode-btn.active {
      background: var(--accent);
      color: #fff;
      border-color: var(--accent);
    }
    .mode-panel {
      display: none;
      gap: 12px;
    }
    .mode-panel.active {
      display: grid;
    }
    .matches-list {
      display: grid;
      gap: 10px;
    }
    .multi-source {
      display: grid;
      gap: 10px;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfdff;
    }
    .choice-row,
    .inline-check {
      display: flex;
      gap: 8px;
      align-items: center;
      font-size: 13px;
      font-weight: 600;
      color: #344054;
    }
    .auto-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }
    .source-panel {
      display: none;
      gap: 10px;
    }
    .source-panel.active {
      display: grid;
    }
    .match-row {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 8px;
      align-items: end;
    }
    .ghost {
      background: #fff;
      color: var(--accent);
      border: 1px solid var(--accent);
    }
    .danger-btn {
      background: #fff;
      color: var(--danger);
      border: 1px solid #f3c7c7;
      padding: 10px 12px;
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
        <input type="hidden" name="mode" id="modeInput" value="{{ mode }}" />
        <label>Username
          <input name="username" autocomplete="username" required value="{{ username }}" />
        </label>
        <label>Password
          <input name="password" type="password" autocomplete="current-password" required value="{{ password }}" />
        </label>
        <div class="mode-switch">
          <button type="button" class="mode-btn" data-mode="single">Single Match</button>
          <button type="button" class="mode-btn" data-mode="multi">Multi Match Team Aggregate</button>
          <button type="button" class="mode-btn" data-mode="animation">Animation</button>
        </div>

        <section id="singlePanel" class="mode-panel">
          <div class="small" id="singleModeHint">Generate a full report for one match.</div>
          <label>Match ID
            <input name="matchid" value="{{ matchid }}" />
          </label>
        </section>

        <section id="multiPanel" class="mode-panel">
          <div class="small">Add match IDs manually, or pull them from a national team schedule.</div>
          <input type="hidden" name="multi_source" id="multiSourceInput" value="{{ multi_source }}" />
          <div class="multi-source">
            <label class="choice-row">
              <input type="radio" name="multi_source_choice" value="manual" />
              Manual match IDs
            </label>
            <div id="manualMatchPanel" class="source-panel">
              <div id="matchesList" class="matches-list">
                {% for value in multi_matchids %}
                <div class="match-row">
                  <label>Match ID
                    <input name="matchids" value="{{ value }}" />
                  </label>
                  <button type="button" class="danger-btn remove-match"{% if loop.index <= 2 %} hidden{% endif %}>Remove</button>
                </div>
                {% endfor %}
              </div>
              <button type="button" id="addMatchBtn" class="ghost">Add Match</button>
            </div>
            <label class="choice-row">
              <input type="radio" name="multi_source_choice" value="national" />
              National team schedule
            </label>
            <div id="nationalMatchPanel" class="source-panel">
              <button type="button" id="loadNationalOptionsBtn" class="ghost">Load Teams And Seasons</button>
              <div class="auto-grid">
                <label>Team
                  <select name="national_country_id" id="nationalCountrySelect" data-selected="{{ national_country_id }}">
                    <option value="">Select a team</option>
                  </select>
                </label>
                <label>Team Type
                  <select name="national_team_kind" id="nationalTeamKind">
                    <option value="nt"{% if national_team_kind == "nt" %} selected{% endif %}>National team</option>
                    <option value="u21"{% if national_team_kind == "u21" %} selected{% endif %}>U21 national team</option>
                  </select>
                </label>
                <label>Season
                  <select name="national_season" id="nationalSeasonSelect" data-selected="{{ national_season }}">
                    <option value="">Current season</option>
                  </select>
                </label>
                <label class="inline-check">
                  <input type="checkbox" name="include_friendlies" value="1"{% if include_friendlies %} checked{% endif %} />
                  Include friendlies
                </label>
              </div>
              <div class="hint" id="nationalOptionsStatus">Use the button after entering credentials.</div>
            </div>
          </div>
        </section>

        <button type="submit">Generate Report</button>
      </form>
      <div class="hint">Credentials are only used for this request (server memory only).</div>
    </section>
  </main>
  <template id="matchRowTemplate">
    <div class="match-row">
      <label>Match ID
        <input name="matchids" />
      </label>
      <button type="button" class="danger-btn remove-match">Remove</button>
    </div>
  </template>
  <script>
    const modeInput = document.getElementById("modeInput");
    const singlePanel = document.getElementById("singlePanel");
    const multiPanel = document.getElementById("multiPanel");
    const singleModeHint = document.getElementById("singleModeHint");
    const modeButtons = [...document.querySelectorAll(".mode-btn")];
    const matchesList = document.getElementById("matchesList");
    const addMatchBtn = document.getElementById("addMatchBtn");
    const rowTemplate = document.getElementById("matchRowTemplate");
    const multiSourceInput = document.getElementById("multiSourceInput");
    const sourceChoices = [...document.querySelectorAll("input[name='multi_source_choice']")];
    const manualMatchPanel = document.getElementById("manualMatchPanel");
    const nationalMatchPanel = document.getElementById("nationalMatchPanel");
    const loadNationalOptionsBtn = document.getElementById("loadNationalOptionsBtn");
    const nationalCountrySelect = document.getElementById("nationalCountrySelect");
    const nationalSeasonSelect = document.getElementById("nationalSeasonSelect");
    const nationalOptionsStatus = document.getElementById("nationalOptionsStatus");
    const localNationalOptions = {{ national_options | tojson }};

    function applyMode(mode) {
      modeInput.value = mode;
      singlePanel.classList.toggle("active", mode === "single" || mode === "animation");
      multiPanel.classList.toggle("active", mode === "multi");
      modeButtons.forEach(btn => btn.classList.toggle("active", btn.dataset.mode === mode));
      singleModeHint.textContent = mode === "animation"
        ? "Generate a live animated game view for one match."
        : "Generate a full report for one match.";
    }

    function updateRemoveButtons() {
      const rows = [...matchesList.querySelectorAll(".match-row")];
      rows.forEach((row, index) => {
        const btn = row.querySelector(".remove-match");
        if (btn) btn.hidden = rows.length <= 2 || index < 2;
      });
    }

    modeButtons.forEach(btn => {
      btn.addEventListener("click", () => applyMode(btn.dataset.mode));
    });

    function applyMultiSource(source) {
      multiSourceInput.value = source;
      sourceChoices.forEach(choice => {
        choice.checked = choice.value === source;
      });
      manualMatchPanel.classList.toggle("active", source === "manual");
      nationalMatchPanel.classList.toggle("active", source === "national");
    }

    sourceChoices.forEach(choice => {
      choice.addEventListener("change", () => applyMultiSource(choice.value));
    });

    addMatchBtn?.addEventListener("click", () => {
      const frag = rowTemplate.content.cloneNode(true);
      matchesList.appendChild(frag);
      updateRemoveButtons();
    });

    matchesList.addEventListener("click", (ev) => {
      const btn = ev.target.closest(".remove-match");
      if (!btn) return;
      btn.closest(".match-row")?.remove();
      updateRemoveButtons();
    });

    function fillSelect(select, rows, selectedValue, fallbackLabel) {
      select.textContent = "";
      const fallback = document.createElement("option");
      fallback.value = "";
      fallback.textContent = fallbackLabel;
      select.appendChild(fallback);
      rows.forEach(row => {
        const opt = document.createElement("option");
        opt.value = row.id;
        opt.textContent = row.label || row.name;
        if (String(row.id) === String(selectedValue) || (!selectedValue && row.current)) {
          opt.selected = true;
        }
        select.appendChild(opt);
      });
    }

    function loadOptionsIntoForm(payload, statusText) {
      fillSelect(nationalCountrySelect, payload.countries || [], nationalCountrySelect.dataset.selected, "Select a team");
      fillSelect(nationalSeasonSelect, payload.seasons || [], nationalSeasonSelect.dataset.selected, "Current season");
      nationalOptionsStatus.textContent = statusText;
    }

    loadNationalOptionsBtn?.addEventListener("click", async () => {
      const username = document.querySelector("input[name='username']").value.trim();
      const password = document.querySelector("input[name='password']").value.trim();
      if (!username || !password) {
        nationalOptionsStatus.textContent = "Enter username and password first.";
        return;
      }
      nationalOptionsStatus.textContent = "Loading teams and seasons...";
      loadNationalOptionsBtn.disabled = true;
      try {
        const response = await fetch("/national-options", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username, password }),
        });
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.error || "Could not load national teams.");
        }
        loadOptionsIntoForm(payload, "Loaded from BBAPI and saved locally.");
      } catch (err) {
        nationalOptionsStatus.textContent = err.message;
      } finally {
        loadNationalOptionsBtn.disabled = false;
      }
    });

    updateRemoveButtons();
    loadOptionsIntoForm(localNationalOptions, "Loaded from local file. Use the button to refresh.");
    applyMultiSource({{ multi_source | tojson }});
    applyMode({{ mode | tojson }});
  </script>
</body>
</html>
"""


TEAM_CHOICE_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Select Team</title>
  <style>
    body {
      margin: 0;
      font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
      background: #f6f8fb;
      color: #1f2933;
    }
    .wrap {
      max-width: 760px;
      margin: 48px auto;
      padding: 0 18px;
    }
    .card {
      background: #fff;
      border: 1px solid #d9e1ea;
      border-radius: 14px;
      box-shadow: 0 8px 26px rgba(16, 24, 40, 0.08);
      padding: 22px;
    }
    h1 { margin: 0 0 10px; }
    p { color: #607285; }
    .choices {
      display: grid;
      gap: 10px;
      margin-top: 16px;
    }
    button {
      width: 100%;
      padding: 12px 14px;
      border-radius: 10px;
      border: 1px solid #0d47a1;
      background: #0d47a1;
      color: #fff;
      font-size: 14px;
      font-weight: 700;
      cursor: pointer;
    }
    .back {
      display: inline-block;
      margin-top: 14px;
      color: #0d47a1;
      text-decoration: none;
      font-size: 13px;
      font-weight: 600;
    }
  </style>
</head>
<body>
  <main class="wrap">
    <section class="card">
      <h1>Choose The Team</h1>
      <p>The submitted matches match more than one team equally often. Pick which team you want to aggregate.</p>
      <div class="choices">
        {% for candidate in candidates %}
        <form method="post" action="/report">
          <input type="hidden" name="mode" value="multi" />
          <input type="hidden" name="username" value="{{ username }}" />
          <input type="hidden" name="password" value="{{ password }}" />
          <input type="hidden" name="selected_team_key" value="{{ candidate.key }}" />
          {% for value in matchids %}
          <input type="hidden" name="matchids" value="{{ value }}" />
          {% endfor %}
          <button type="submit">{{ candidate.name }}</button>
        </form>
        {% endfor %}
      </div>
      <a href="/" class="back">Back to report form</a>
    </section>
  </main>
</body>
</html>
"""


MULTI_REPORT_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>BBInsider Multi Match Aggregate</title>
  <style>
    :root {
      --bg: #f7f7f2;
      --panel: #ffffff;
      --ink: #1f2328;
      --muted: #5f6b76;
      --line: #d9dee5;
      --accent: #0d47a1;
      --shadow: 0 10px 30px rgba(0, 0, 0, 0.08);
      --danger-bg: #fff4f4;
      --danger-line: #f3c7c7;
      --success-bg: #f0fdf4;
      --success-line: #bbf7d0;
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
      max-width: 1280px;
      margin: 0 auto;
      padding: 24px;
    }
    .topbar {
      margin-bottom: 12px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
    }
    .topbar a {
      text-decoration: none;
      color: var(--accent);
      font-size: 13px;
      font-weight: 600;
    }
    .hero, .card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      box-shadow: var(--shadow);
    }
    .hero {
      padding: 20px;
      margin-bottom: 18px;
    }
    .hero h1 {
      margin: 0 0 8px;
      font-size: 30px;
    }
    .hero p {
      margin: 0;
      color: var(--muted);
    }
    .summary-grid {
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 10px;
      margin-top: 16px;
    }
    .summary-card {
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 12px;
      background: #fbfdff;
    }
    .summary-card .k {
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    .summary-card .v {
      font-size: 22px;
      font-weight: 800;
      margin-top: 4px;
    }
    .panel-summary {
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 8px;
      padding: 12px;
      border-bottom: 1px solid var(--line);
      background: #f8fbff;
    }
    .card {
      margin-bottom: 18px;
      overflow: hidden;
    }
    .card h2 {
      margin: 0;
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      background: #fafcff;
      font-size: 15px;
    }
    .card-body {
      padding: 12px;
    }
    .table-wrap {
      overflow: auto;
      max-height: 520px;
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
    #playerMatchupTable th:first-child,
    #playerMatchupTable td:first-child {
      position: sticky;
      left: 0;
      z-index: 4;
      background: #fff;
      box-shadow: 2px 0 0 #eef1f5;
    }
    #playerMatchupTable th:first-child {
      background: #f7f9fc;
      z-index: 6;
    }
    #playerMatchupTable th:nth-child(2),
    #playerMatchupTable td:nth-child(2) {
      background: #f7f8ff;
      border-right: 3px solid #c7d2fe;
    }
    #playerMatchupTable th:nth-child(3),
    #playerMatchupTable td:nth-child(3),
    #playerMatchupTable th:nth-child(4),
    #playerMatchupTable td:nth-child(4),
    #playerMatchupTable th:nth-child(5),
    #playerMatchupTable td:nth-child(5),
    #playerMatchupTable th:nth-child(6),
    #playerMatchupTable td:nth-child(6) {
      background: #f0fdf4;
    }
    #playerMatchupTable th:nth-child(6),
    #playerMatchupTable td:nth-child(6) {
      border-right: 3px solid #86efac;
    }
    #playerMatchupTable th:nth-child(7),
    #playerMatchupTable td:nth-child(7),
    #playerMatchupTable th:nth-child(8),
    #playerMatchupTable td:nth-child(8) {
      background: #fff7ed;
    }
    #playerMatchupTable th:nth-child(8),
    #playerMatchupTable td:nth-child(8) {
      border-right: 3px solid #fdba74;
    }
    #playerMatchupTable th:nth-child(9),
    #playerMatchupTable td:nth-child(9),
    #playerMatchupTable th:nth-child(10),
    #playerMatchupTable td:nth-child(10) {
      background: #fef2f2;
    }
    #playerDefenseTable th:first-child,
    #playerDefenseTable td:first-child {
      position: sticky;
      left: 0;
      z-index: 4;
      background: #fff;
      box-shadow: 2px 0 0 #eef1f5;
    }
    #playerDefenseTable th:first-child {
      background: #f7f9fc;
      z-index: 6;
    }
    #playerDefenseTable th:nth-child(2),
    #playerDefenseTable td:nth-child(2),
    #playerDefenseTable th:nth-child(3),
    #playerDefenseTable td:nth-child(3) {
      background: #eef6ff;
    }
    #playerDefenseTable th:nth-child(3),
    #playerDefenseTable td:nth-child(3) {
      border-right: 3px solid #93c5fd;
    }
    #playerDefenseTable th:nth-child(4),
    #playerDefenseTable td:nth-child(4) {
      background: #f6f3ff;
      border-right: 3px solid #c4b5fd;
    }
    #playerDefenseTable th:nth-child(5),
    #playerDefenseTable td:nth-child(5),
    #playerDefenseTable th:nth-child(6),
    #playerDefenseTable td:nth-child(6),
    #playerDefenseTable th:nth-child(7),
    #playerDefenseTable td:nth-child(7) {
      background: #f0fdf4;
    }
    .warn-list {
      margin: 0;
      padding-left: 18px;
      color: #8a1c1c;
    }
    .empty {
      color: var(--muted);
      font-size: 13px;
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
    .multi-dd.open .multi-dd-menu { display: block; }
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
    .summary-badges {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 14px;
    }
    .badge {
      border-radius: 999px;
      padding: 6px 10px;
      font-size: 12px;
      font-weight: 700;
      border: 1px solid var(--line);
      background: #f9fbff;
    }
    .badge.good {
      background: var(--success-bg);
      border-color: var(--success-line);
    }
    .badge.bad {
      background: var(--danger-bg);
      border-color: var(--danger-line);
    }
    .impact-marks {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      margin-left: 6px;
      vertical-align: middle;
    }
    .impact-mark {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 18px;
      height: 18px;
      padding: 0 6px;
      border-radius: 999px;
      border: 1px solid transparent;
      font-size: 11px;
      font-weight: 800;
      line-height: 1;
      cursor: help;
    }
    .impact-mark.pos {
      color: #166534;
      background: #f0fdf4;
      border-color: #86efac;
    }
    .impact-mark.neg {
      color: #991b1b;
      background: #fef2f2;
      border-color: #fca5a5;
    }
    .insight-note {
      margin: 0;
      padding: 12px;
      color: var(--muted);
      font-size: 13px;
      border-bottom: 1px solid var(--line);
      background: #fcfdff;
    }
    .insight-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      padding: 12px;
      border-bottom: 1px solid var(--line);
    }
    .insight-card {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: #fff;
      box-shadow: 0 6px 18px rgba(13, 39, 65, 0.05);
    }
    .insight-card.good {
      border-color: var(--success-line);
      background: var(--success-bg);
    }
    .insight-card.bad {
      border-color: var(--danger-line);
      background: var(--danger-bg);
    }
    .insight-card h3 {
      margin: 7px 0 6px;
      font-size: 16px;
    }
    .insight-card p {
      margin: 0 0 8px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
    }
    .insight-type {
      display: inline-flex;
      align-items: center;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 3px 8px;
      background: #fff;
      color: var(--muted);
      font-size: 11px;
      font-weight: 800;
      text-transform: uppercase;
    }
    .insight-evidence {
      color: var(--ink);
      font-size: 12px;
      font-weight: 700;
    }
    .insight-list {
      display: grid;
      gap: 8px;
      margin-top: 8px;
    }
    .insight-range {
      border-top: 1px solid rgba(95, 107, 118, 0.22);
      padding-top: 8px;
    }
    .insight-range:first-child {
      border-top: 0;
      padding-top: 0;
    }
    .insight-range-title {
      margin-bottom: 4px;
      color: var(--ink);
      font-size: 12px;
      font-weight: 800;
    }
    .insight-mini {
      margin: 0 0 6px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.4;
    }
    .insight-mini:last-child {
      margin-bottom: 0;
    }
    .sortable-th {
      cursor: pointer;
      user-select: none;
      white-space: nowrap;
    }
    .sortable-th .sort-indicator {
      display: inline-block;
      min-width: 12px;
      margin-left: 4px;
      color: var(--muted);
      font-size: 11px;
    }
    @media (max-width: 960px) {
      .summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .panel-summary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .insight-grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <main class="wrap">
    <div class="topbar">
      <div class="small">Multi-match aggregate | BBAPI user: {{ username }}</div>
      <a href="/">Run another report</a>
    </div>

    <section class="hero">
      <h1 id="teamName"></h1>
      <p id="summaryLine"></p>
      <div class="summary-grid">
        <div class="summary-card"><div class="k">Matches Submitted</div><div class="v" id="submittedCount"></div></div>
        <div class="summary-card"><div class="k">Matches Used</div><div class="v" id="usedCount"></div></div>
        <div class="summary-card"><div class="k">Matches Skipped</div><div class="v" id="skippedCount"></div></div>
        <div class="summary-card"><div class="k">Record</div><div class="v" id="recordLine"></div></div>
        <div class="summary-card"><div class="k">Tracked Players</div><div class="v" id="playerCount"></div></div>
      </div>
      <div class="summary-badges">
        <span class="badge good" id="winsBadge"></span>
        <span class="badge bad" id="lossesBadge"></span>
        <span class="badge" id="warningsBadge"></span>
      </div>
    </section>

    <section class="card">
      <h2>Warnings</h2>
      <div class="card-body">
        <ul id="warningsList" class="warn-list"></ul>
        <div id="warningsEmpty" class="empty">No warnings.</div>
      </div>
    </section>

    <section class="card">
      <h2>Match Summary</h2>
      <div class="table-wrap">
        <table id="matchSummaryTable"></table>
      </div>
    </section>

    <section class="card">
      <h2>Player Summary</h2>
      <div class="table-wrap">
        <table id="playerSummaryTable"></table>
      </div>
    </section>

    <section class="card">
      <h2>Player Matchup Overview</h2>
      <div class="table-wrap">
        <table id="playerMatchupTable"></table>
      </div>
    </section>

    <section class="card">
      <h2>Player Defense Overview</h2>
      <div class="table-wrap">
        <table id="playerDefenseTable"></table>
      </div>
    </section>

    <section class="card">
      <h2>Detections &amp; Suggestions</h2>
      <p class="insight-note">Findings favor large percentage swings with enough relevant attempts. Small samples are filtered out, but the evidence stays visible.</p>
      <div id="detectionsEmpty" class="card-body empty" hidden>Not enough qualified attempts for detection yet.</div>
      <div id="detectionsCards" class="insight-grid"></div>
      <div class="table-wrap">
        <table id="detectionsTable"></table>
      </div>
    </section>

    <section class="card">
      <h2>Offense Shot Profile By Player</h2>
      <div class="table-wrap">
        <table id="offPlayersTable"></table>
      </div>
    </section>

    <section class="card">
      <h2>Defended Shot Log</h2>
      <div class="events-head">
        <div class="multi-dd" id="defenderFilter"></div>
        <div class="multi-dd" id="defShotTypeFilter"></div>
        <div class="multi-dd" id="defResultFilter"></div>
      </div>
      <div id="defSummary" class="panel-summary"></div>
      <div class="table-wrap">
        <table id="defShotsTable"></table>
      </div>
    </section>

    <script>
      const data = {{ report_json | tojson }};
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

      function shotStatHtml(stat) {
        if (!stat || !stat.a) return "";
        const pct = ((stat.m / stat.a) * 100).toFixed(1);
        return `${stat.m}/${stat.a}/${pct}%`;
      }

      function defenseStatHtml(stat) {
        if (!stat || !stat.a) return "";
        const allowed = stat.a - stat.m;
        const pct = ((allowed / stat.a) * 100).toFixed(1);
        return `${allowed}/${stat.a} ${pct}%`;
      }

      function defensePctHtml(stat) {
        if (!stat || !stat.a) return "";
        return `${(((stat.a - stat.m) / stat.a) * 100).toFixed(1)}%`;
      }

      function offCellHtml(cell) {
        return `${cell.a}/${cell.m}/${cell.mi}/${cell.b}`;
      }

      const MIN_DETECTION_ATTEMPTS = 8;
      const detectionColumns = [
        { key: "type", label: "Type", numeric: false },
        { key: "player", label: "Player", numeric: false },
        { key: "finding", label: "Finding", numeric: false },
        { key: "evidence", label: "Evidence", numeric: false },
        { key: "suggestion", label: "Suggestion", numeric: false },
        { key: "score", label: "Score", numeric: true }
      ];
      let detectionRows = [];
      let detectionSort = { key: "score", dir: "desc" };

      function shotStatRatio(stat) {
        return stat && stat.a ? stat.m / stat.a : null;
      }

      function defenseAllowedRatio(stat) {
        return stat && stat.a ? (stat.a - stat.m) / stat.a : null;
      }

      function formatPctRatio(value) {
        return value === null || !Number.isFinite(value) ? "N/A" : `${(value * 100).toFixed(1)}%`;
      }

      function formatSignedPp(value) {
        const prefix = value > 0 ? "+" : "";
        return `${prefix}${value.toFixed(1)}pp`;
      }

      function getShotRange(code) {
        const value = String(code);
        if (value.startsWith("10")) return "three";
        if (value.startsWith("20")) return "jump";
        return "paint";
      }

      function rangeLabel(range) {
        if (range === "three") return "3PT";
        if (range === "jump") return "mid-range";
        return "paint";
      }

      function emptyOffCell() {
        return { a: 0, m: 0, mi: 0, b: 0 };
      }

      function addOffCells(target, source) {
        if (!source) return;
        target.a += source.a || 0;
        target.m += source.m || 0;
        target.mi += source.mi || 0;
        target.b += source.b || 0;
      }

      function groupPlayerOffenseByRange(player) {
        const out = { three: emptyOffCell(), jump: emptyOffCell(), paint: emptyOffCell() };
        Object.entries(player.counts || {}).forEach(([code, cell]) => {
          addOffCells(out[getShotRange(code)], cell);
        });
        return out;
      }

      function offRatio(cell) {
        return cell && cell.a ? cell.m / cell.a : null;
      }

      function pushDetection(rows, item) {
        if (!Number.isFinite(item.score) || item.score <= 0) return;
        rows.push(item);
      }

      function buildDetections() {
        const rows = [];
        const offensePlayers = data.offense.players || [];
        const teamRangeTotals = { three: emptyOffCell(), jump: emptyOffCell(), paint: emptyOffCell() };
        offensePlayers.forEach(player => {
          const ranges = groupPlayerOffenseByRange(player);
          Object.keys(teamRangeTotals).forEach(range => addOffCells(teamRangeTotals[range], ranges[range]));
        });
        const avgTotalAttempts = offensePlayers.length
          ? offensePlayers.reduce((sum, player) => sum + (player.total?.a || 0), 0) / offensePlayers.length
          : 0;
        const avgRangeAttempts = Object.fromEntries(
          Object.entries(teamRangeTotals).map(([range, cell]) => [range, offensePlayers.length ? cell.a / offensePlayers.length : 0])
        );

        (data.matchup || []).forEach(row => {
          const on = shotStatRatio(row.teamOn);
          const off = shotStatRatio(row.teamOff);
          if (on === null || off === null || row.teamOn.a < MIN_DETECTION_ATTEMPTS || row.teamOff.a < MIN_DETECTION_ATTEMPTS) return;
          const diff = (on - off) * 100;
          const score = Math.abs(diff) * Math.log1p(Math.min(row.teamOn.a, row.teamOff.a));
          const better = diff > 0;
          pushDetection(rows, {
            type: "FG On/Off Lift",
            player: row.name,
            finding: `Team FG ${better ? "rises" : "falls"} ${formatSignedPp(diff)} with him on court`,
            evidence: `On ${formatPctRatio(on)} (${row.teamOn.m}/${row.teamOn.a}), off ${formatPctRatio(off)} (${row.teamOff.m}/${row.teamOff.a})`,
            suggestion: better ? "Lean into lineups and actions where he stays involved." : "Check whether his minutes overlap with tougher shots or stagnant possessions.",
            score,
            sentiment: better ? "good" : "bad"
          });
        });

        (data.defense || []).forEach(row => {
          const on = defenseAllowedRatio(row.teamDefOn);
          const off = defenseAllowedRatio(row.teamDefOff);
          if (on === null || off === null || row.teamDefOn.a < MIN_DETECTION_ATTEMPTS || row.teamDefOff.a < MIN_DETECTION_ATTEMPTS) return;
          const lift = (off - on) * 100;
          const score = Math.abs(lift) * Math.log1p(Math.min(row.teamDefOn.a, row.teamDefOff.a));
          const better = lift > 0;
          pushDetection(rows, {
            type: "Defensive On/Off Lift",
            player: row.name,
            finding: `Opponent FG allowed ${better ? "drops" : "rises"} ${formatSignedPp(Math.abs(lift))} when he plays`,
            evidence: `On ${formatPctRatio(on)} allowed (${row.teamDefOn.a - row.teamDefOn.m}/${row.teamDefOn.a}), off ${formatPctRatio(off)} allowed (${row.teamDefOff.a - row.teamDefOff.m}/${row.teamDefOff.a})`,
            suggestion: better ? "Prioritize him in defensive stretches and protect his role fit." : "Review matchup assignments, help coverage, and the lineups around his minutes.",
            score,
            sentiment: better ? "good" : "bad"
          });
        });

        const defendedKeys = [
          { key: "defendedTotal", label: "all defended shots" },
          { key: "defendedClose", label: "close defended shots" },
          { key: "defendedMid", label: "mid-range defended shots" },
          { key: "defendedThree", label: "3PT defended shots" }
        ];
        defendedKeys.forEach(({ key, label }) => {
          const total = (data.defense || []).reduce((acc, row) => {
            addOffCells(acc, { a: row[key]?.a || 0, m: row[key]?.m || 0, mi: 0, b: 0 });
            return acc;
          }, emptyOffCell());
          const teamAllowed = defenseAllowedRatio(total);
          if (teamAllowed === null) return;
          (data.defense || []).forEach(row => {
            const stat = row[key];
            const allowed = defenseAllowedRatio(stat);
            if (allowed === null || stat.a < MIN_DETECTION_ATTEMPTS) return;
            const diff = (teamAllowed - allowed) * 100;
            const score = Math.abs(diff) * Math.log1p(stat.a);
            const better = diff > 0;
            pushDetection(rows, {
              type: "Defended Shot Signal",
              player: row.name,
            finding: `${better ? "Strong" : "Concerning"} result on ${label}`,
            evidence: `${formatPctRatio(allowed)} allowed (${stat.a - stat.m}/${stat.a}) vs team ${formatPctRatio(teamAllowed)}, ${formatSignedPp(diff)}`,
            suggestion: better ? "Use him as a primary contest option in this coverage." : "Review whether these contests need earlier help or a different matchup.",
            score,
            range: label,
            sentiment: better ? "good" : "bad"
          });
          });
        });

        offensePlayers.forEach(player => {
          const totalAttempts = player.total?.a || 0;
          if (totalAttempts >= MIN_DETECTION_ATTEMPTS && totalAttempts >= Math.max(MIN_DETECTION_ATTEMPTS, avgTotalAttempts * 1.35)) {
            pushDetection(rows, {
              type: "High Usage",
              player: player.name,
              finding: "Shot volume is carrying a large share of the offense",
              evidence: `${totalAttempts} attempts, team player average ${avgTotalAttempts.toFixed(1)}`,
              suggestion: "Check whether this is intentional usage or a sign other options are not being created.",
              score: totalAttempts,
              sentiment: "neutral"
            });
          }

          const ranges = groupPlayerOffenseByRange(player);
          Object.entries(ranges).forEach(([range, stat]) => {
            if (stat.a >= MIN_DETECTION_ATTEMPTS && stat.a >= Math.max(MIN_DETECTION_ATTEMPTS, avgRangeAttempts[range] * 1.5)) {
              pushDetection(rows, {
                type: "Shot Diet Concentration",
                player: player.name,
                finding: `Notable ${rangeLabel(range)} volume`,
                evidence: `${stat.a} ${rangeLabel(range)} attempts, player average in this range ${avgRangeAttempts[range].toFixed(1)}`,
                suggestion: "Decide if this range should be fed, diversified, or paired with a counter.",
                score: stat.a * Math.log1p(stat.a),
                range: rangeLabel(range),
                sentiment: "neutral"
              });
            }

            const playerRatio = offRatio(stat);
            const teamRatio = offRatio(teamRangeTotals[range]);
            if (playerRatio === null || teamRatio === null || stat.a < MIN_DETECTION_ATTEMPTS) return;
            const diff = (playerRatio - teamRatio) * 100;
            const score = Math.abs(diff) * Math.log1p(stat.a);
            const better = diff > 0;
            pushDetection(rows, {
              type: "Range Efficiency Outlier",
              player: player.name,
              finding: `${better ? "Hot" : "cold"} from ${rangeLabel(range)}`,
              evidence: `${formatPctRatio(playerRatio)} (${stat.m}/${stat.a}) vs team ${formatPctRatio(teamRatio)}, ${formatSignedPp(diff)}`,
              suggestion: better ? "Look for repeatable actions that create this shot." : "Consider reducing this shot type unless the context explains the miss pattern.",
              score,
              range: rangeLabel(range),
              sentiment: better ? "good" : "bad"
            });
          });
        });

        return rows.sort((a, b) => b.score - a.score || a.player.localeCompare(b.player));
      }

      function cardSentiment(rows) {
        const top = rows[0];
        return top?.sentiment || "neutral";
      }

      function summarizeRowsForCard(rows) {
        const limitedRows = rows.slice(0, 4);
        if (!limitedRows.some(row => row.range)) {
          return `
            <div class="insight-list">
              ${limitedRows.map(row => `
                <p class="insight-mini"><strong>${row.player}</strong>: ${row.finding}. ${row.evidence}</p>
              `).join("")}
            </div>
          `;
        }

        const byRange = new Map();
        limitedRows.forEach(row => {
          const key = row.range || "Other";
          if (!byRange.has(key)) byRange.set(key, []);
          byRange.get(key).push(row);
        });

        return `
          <div class="insight-list">
            ${[...byRange.entries()].map(([range, rangeRows]) => `
              <div class="insight-range">
                <div class="insight-range-title">${range}</div>
                ${rangeRows.map(row => `
                  <p class="insight-mini"><strong>${row.player}</strong>: ${row.finding}. ${row.evidence}</p>
                `).join("")}
              </div>
            `).join("")}
          </div>
        `;
      }

      function renderDetectionCards(rows) {
        const cards = document.getElementById("detectionsCards");
        const byType = new Map();
        rows.forEach(row => {
          if (!byType.has(row.type)) byType.set(row.type, []);
          byType.get(row.type).push(row);
        });
        const groups = [...byType.entries()]
          .map(([type, typeRows]) => ({
            type,
            rows: typeRows.sort((a, b) => b.score - a.score),
            score: Math.max(...typeRows.map(row => row.score))
          }))
          .sort((a, b) => b.score - a.score || a.type.localeCompare(b.type));

        cards.innerHTML = groups.map(group => `
          <article class="insight-card ${cardSentiment(group.rows)}">
            <span class="insight-type">${group.type}</span>
            <h3>${group.rows.length} finding${group.rows.length === 1 ? "" : "s"}</h3>
            <p>${group.rows[0].suggestion}</p>
            ${summarizeRowsForCard(group.rows)}
          </article>
        `).join("");
      }

      function sortDetectionRows(rows) {
        const column = detectionColumns.find(item => item.key === detectionSort.key);
        const dir = detectionSort.dir === "asc" ? 1 : -1;
        return [...rows].sort((a, b) => {
          const av = a[detectionSort.key];
          const bv = b[detectionSort.key];
          if (column?.numeric) return ((Number(av) || 0) - (Number(bv) || 0)) * dir;
          return String(av || "").localeCompare(String(bv || ""), undefined, { sensitivity: "base" }) * dir;
        });
      }

      function renderDetectionsTable() {
        const table = document.getElementById("detectionsTable");
        const sorted = sortDetectionRows(detectionRows);
        table.innerHTML = `
          <thead>
            <tr>
              ${detectionColumns.map(column => `
                <th class="sortable-th" data-sort-key="${column.key}" aria-sort="${detectionSort.key === column.key ? (detectionSort.dir === "asc" ? "ascending" : "descending") : "none"}">
                  ${column.label}<span class="sort-indicator">${detectionSort.key === column.key ? (detectionSort.dir === "asc" ? "^" : "v") : ""}</span>
                </th>
              `).join("")}
            </tr>
          </thead>
          <tbody>
            ${sorted.map(row => `
              <tr>
                <td>${row.type}</td>
                <td>${row.player}</td>
                <td>${row.finding}</td>
                <td>${row.evidence}</td>
                <td>${row.suggestion}</td>
                <td>${row.score.toFixed(1)}</td>
              </tr>
            `).join("")}
          </tbody>
        `;
        table.querySelectorAll("th[data-sort-key]").forEach(th => {
          th.addEventListener("click", () => {
            const key = th.dataset.sortKey;
            detectionSort = {
              key,
              dir: detectionSort.key === key && detectionSort.dir === "desc" ? "asc" : "desc"
            };
            renderDetectionsTable();
          });
        });
      }

      function renderDetections() {
        detectionRows = buildDetections();
        const empty = document.getElementById("detectionsEmpty");
        const cards = document.getElementById("detectionsCards");
        const table = document.getElementById("detectionsTable");
        if (!detectionRows.length) {
          empty.hidden = false;
          cards.innerHTML = "";
          table.innerHTML = "";
          return;
        }
        empty.hidden = true;
        renderDetectionCards(detectionRows);
        renderDetectionsTable();
      }

      function selectedValues(filterRoot) {
        return new Set(
          [...filterRoot.querySelectorAll("input[data-role='item']:checked")]
            .map(node => node.value)
        );
      }

      function updateFilterButtonLabel(filterRoot, options) {
        const button = filterRoot.querySelector(".multi-dd-btn");
        const selected = selectedValues(filterRoot);
        if (selected.size === 0) {
          button.textContent = "None selected";
          return;
        }
        if (selected.size === options.length) {
          button.textContent = "All selected";
          return;
        }
        if (selected.size === 1) {
          const val = [...selected][0];
          const found = options.find(option => option.value === val);
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
        allRow.appendChild(allBox);
        const allText = document.createElement("span");
        allText.textContent = "Select all";
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
          row.appendChild(cb);
          const text = document.createElement("span");
          text.textContent = opt.label;
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
          filterRoot.querySelectorAll("input[data-role='item']").forEach(node => {
            node.checked = allBox.checked;
          });
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

      document.getElementById("teamName").textContent = data.team_name;
      document.getElementById("summaryLine").textContent = `Aggregated full-game totals across ${data.used_matches} selected matches.`;
      document.getElementById("submittedCount").textContent = data.submitted_matches;
      document.getElementById("usedCount").textContent = data.used_matches;
      document.getElementById("skippedCount").textContent = data.skipped_matches;
      document.getElementById("recordLine").textContent = `${data.wins}-${data.losses}`;
      document.getElementById("playerCount").textContent = data.player_summary.length;
      document.getElementById("winsBadge").textContent = `${data.wins} wins`;
      document.getElementById("lossesBadge").textContent = `${data.losses} losses`;
      document.getElementById("warningsBadge").textContent = `${data.warnings.length} warnings`;

      const warningsList = document.getElementById("warningsList");
      const warningsEmpty = document.getElementById("warningsEmpty");
      if (data.warnings.length) {
        warningsList.innerHTML = data.warnings.map(item => `<li>${item}</li>`).join("");
        warningsEmpty.hidden = true;
      } else {
        warningsList.innerHTML = "";
        warningsEmpty.hidden = false;
      }

      document.getElementById("matchSummaryTable").innerHTML = `
        <thead>
          <tr>
            <th>Match ID</th><th>Home Team</th><th>Away Team</th><th>Score</th><th>Detected Team Side</th><th>Result</th><th>Status</th>
          </tr>
        </thead>
        <tbody>
          ${data.matches.map(row => `
            <tr>
              <td>${row.matchid}</td>
              <td>${row.home_team}</td>
              <td>${row.away_team}</td>
              <td>${row.score}</td>
              <td>${row.detected_side}</td>
              <td>${row.result}</td>
              <td>${row.status}</td>
            </tr>
          `).join("")}
        </tbody>
      `;

      const playerSummary = [...data.player_summary].sort((a, b) => b.fga - a.fga || b.pts - a.pts || a.name.localeCompare(b.name));
      document.getElementById("playerSummaryTable").innerHTML = `
        <thead>
          <tr>
            <th>Player</th><th>GP</th><th>MIN</th><th>PTS</th><th>FG</th><th>3PT</th><th>FT</th><th>REB</th><th>AST</th><th>TO</th><th>STL</th><th>BLK</th><th>PF</th><th>+/-</th>
          </tr>
        </thead>
        <tbody>
          ${playerSummary.map(row => `
            <tr>
              <td>${row.name}</td>
              <td>${row.gp}</td>
              <td>${row.mins}</td>
              <td>${row.pts}</td>
              <td>${row.fgm}/${row.fga}</td>
              <td>${row.tpm}/${row.tpa}</td>
              <td>${row.ftm}/${row.fta}</td>
              <td>${row.tr}</td>
              <td>${row.ast}</td>
              <td>${row.to}</td>
              <td>${row.stl}</td>
              <td>${row.blk}</td>
              <td>${row.pf}</td>
              <td>${row.pm}</td>
            </tr>
          `).join("")}
        </tbody>
      `;

      const matchupRows = [...data.matchup].sort((a, b) => b.total_attempts - a.total_attempts || a.name.localeCompare(b.name));
      document.getElementById("playerMatchupTable").innerHTML = `
        <thead>
          <tr>
            <th>Player</th><th>With Defense</th><th>Open Close</th><th>Open Mid</th><th>Open 3PT</th><th>Open Total</th><th>Team FG On</th><th>Team FG Off</th><th>Pass Received</th><th>No Pass</th>
          </tr>
        </thead>
        <tbody>
          ${matchupRows.map(row => `
            <tr>
              <td>${row.name}</td>
              <td>${shotStatHtml(row.defended)}</td>
              <td>${shotStatHtml(row.openClose)}</td>
              <td>${shotStatHtml(row.openMid)}</td>
              <td>${shotStatHtml(row.openThree)}</td>
              <td>${shotStatHtml(row.openTotal)}</td>
              <td>${shotStatHtml(row.teamOn)}</td>
              <td>${shotStatHtml(row.teamOff)}</td>
              <td>${shotStatHtml(row.withPass)}</td>
              <td>${shotStatHtml(row.withoutPass)}</td>
            </tr>
          `).join("")}
        </tbody>
      `;

      const defenseRows = [...data.defense].sort((a, b) => b.total_attempts - a.total_attempts || a.name.localeCompare(b.name));
      document.getElementById("playerDefenseTable").innerHTML = `
        <thead>
          <tr>
            <th>Player</th><th>Team Def On</th><th>Team Def Off</th><th>Defended Total</th><th>Defended Close</th><th>Defended Mid</th><th>Defended 3PT</th>
          </tr>
        </thead>
        <tbody>
          ${defenseRows.map(row => `
            <tr>
              <td>${row.name}</td>
              <td>${defensePctHtml(row.teamDefOn)}</td>
              <td>${defensePctHtml(row.teamDefOff)}</td>
              <td>${defenseStatHtml(row.defendedTotal)}</td>
              <td>${defenseStatHtml(row.defendedClose)}</td>
              <td>${defenseStatHtml(row.defendedMid)}</td>
              <td>${defenseStatHtml(row.defendedThree)}</td>
            </tr>
          `).join("")}
        </tbody>
      `;

      renderDetections();

      document.getElementById("offPlayersTable").innerHTML = `
        <thead>
          <tr>
            <th>Player</th>
            ${data.offense.shot_types.map(code => `<th>${shotTypeLabel[code] || code}</th>`).join("")}
            <th>Total</th>
          </tr>
        </thead>
        <tbody>
          ${[...data.offense.players].sort((a, b) => b.total.a - a.total.a || a.name.localeCompare(b.name)).map(row => `
            <tr>
              <td>${row.name}</td>
              ${data.offense.shot_types.map(code => `<td>${offCellHtml(row.counts[code])}</td>`).join("")}
              <td>${offCellHtml(row.total)}</td>
            </tr>
          `).join("")}
        </tbody>
      `;

      const defenderFilter = document.getElementById("defenderFilter");
      const defShotTypeFilter = document.getElementById("defShotTypeFilter");
      const defResultFilter = document.getElementById("defResultFilter");
      const defSummary = document.getElementById("defSummary");

      initMultiDropdown(defenderFilter, data.defended_shots.players.map(name => ({ value: name, label: name })), renderDefendedShots);
      initMultiDropdown(defShotTypeFilter, data.defended_shots.shot_types.map(code => ({ value: code, label: shotTypeLabel[code] || code })), renderDefendedShots);
      initMultiDropdown(defResultFilter, data.defended_shots.results.map(code => ({ value: code, label: shotResultLabel[code] || code })), renderDefendedShots);

      function renderDefendedShots() {
        const selectedDefenders = selectedValues(defenderFilter);
        const selectedShotTypes = selectedValues(defShotTypeFilter);
        const selectedResults = selectedValues(defResultFilter);
        const filtered = data.defended_shots.events.filter(ev => {
          if (selectedDefenders.size && !selectedDefenders.has(ev.defender)) return false;
          if (selectedShotTypes.size && !selectedShotTypes.has(ev.shot_type)) return false;
          if (selectedResults.size && !selectedResults.has(ev.shot_result)) return false;
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

        document.getElementById("defShotsTable").innerHTML = `
          <thead>
            <tr>
              <th>Match ID</th><th>Defender</th><th>Shooter</th><th>Opponent</th><th>Shot Type</th><th>Result</th><th>Comment</th>
            </tr>
          </thead>
          <tbody>
            ${filtered.map(ev => `
              <tr>
                <td>${ev.matchid}</td>
                <td>${ev.defender}</td>
                <td>${ev.shooter}</td>
                <td>${ev.opponent}</td>
                <td>${shotTypeLabel[ev.shot_type] || ev.shot_type}</td>
                <td>${shotResultLabel[ev.shot_result] || ev.shot_result}</td>
                <td>${ev.comment}</td>
              </tr>
            `).join("")}
          </tbody>
        `;
      }

      document.addEventListener("click", () => {
        document.querySelectorAll(".multi-dd.open").forEach(node => node.classList.remove("open"));
      });

      renderDefendedShots();
    </script>
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
    #playerMatchupTable th:first-child,
    #playerMatchupTable td:first-child {
      position: sticky;
      left: 0;
      z-index: 4;
      background: #fff;
      box-shadow: 2px 0 0 #eef1f5;
    }
    #playerMatchupTable th:first-child {
      background: #f7f9fc;
      z-index: 6;
    }
    #playerMatchupTable th:nth-child(3),
    #playerMatchupTable td:nth-child(3) {
      background: #f7f8ff;
      border-right: 3px solid #c7d2fe;
    }
    #playerMatchupTable th:nth-child(4),
    #playerMatchupTable td:nth-child(4),
    #playerMatchupTable th:nth-child(5),
    #playerMatchupTable td:nth-child(5),
    #playerMatchupTable th:nth-child(6),
    #playerMatchupTable td:nth-child(6),
    #playerMatchupTable th:nth-child(7),
    #playerMatchupTable td:nth-child(7) {
      background: #f0fdf4;
    }
    #playerMatchupTable th:nth-child(7),
    #playerMatchupTable td:nth-child(7) {
      border-right: 3px solid #86efac;
    }
    #playerMatchupTable th:nth-child(8),
    #playerMatchupTable td:nth-child(8),
    #playerMatchupTable th:nth-child(9),
    #playerMatchupTable td:nth-child(9) {
      background: #fff7ed;
    }
    #playerMatchupTable th:nth-child(9),
    #playerMatchupTable td:nth-child(9) {
      border-right: 3px solid #fdba74;
    }
    #playerMatchupTable th:nth-child(10),
    #playerMatchupTable td:nth-child(10),
    #playerMatchupTable th:nth-child(11),
    #playerMatchupTable td:nth-child(11) {
      background: #fef2f2;
    }
    #playerDefenseTable th:first-child,
    #playerDefenseTable td:first-child {
      position: sticky;
      left: 0;
      z-index: 4;
      background: #fff;
      box-shadow: 2px 0 0 #eef1f5;
    }
    #playerDefenseTable th:first-child {
      background: #f7f9fc;
      z-index: 6;
    }
    #playerDefenseTable th:nth-child(3),
    #playerDefenseTable td:nth-child(3),
    #playerDefenseTable th:nth-child(4),
    #playerDefenseTable td:nth-child(4) {
      background: #eef6ff;
    }
    #playerDefenseTable th:nth-child(4),
    #playerDefenseTable td:nth-child(4) {
      border-right: 3px solid #93c5fd;
    }
    #playerDefenseTable th:nth-child(5),
    #playerDefenseTable td:nth-child(5) {
      background: #f6f3ff;
      border-right: 3px solid #c4b5fd;
    }
    #playerDefenseTable th:nth-child(6),
    #playerDefenseTable td:nth-child(6),
    #playerDefenseTable th:nth-child(7),
    #playerDefenseTable td:nth-child(7),
    #playerDefenseTable th:nth-child(8),
    #playerDefenseTable td:nth-child(8) {
      background: #f0fdf4;
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
    .range-panel-player {
      grid-column: 1 / -1;
    }
    .range-body {
      display: grid;
      grid-template-columns: 150px 1fr;
      gap: 12px;
      padding: 12px;
      align-items: center;
    }
    .range-body-player {
      grid-template-columns: 150px minmax(180px, 1fr) 368px;
      align-items: start;
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
      flex-wrap: wrap;
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
    .court-chart {
      width: 368px;
      height: 192px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background-color: #f6f6f6;
      background-position: center;
      background-repeat: no-repeat;
      background-size: cover;
      position: relative;
      overflow: hidden;
    }
    .court-wrap {
      display: grid;
      gap: 6px;
      justify-items: start;
    }
    .court-marker {
      position: absolute;
      transform: translate(-50%, -50%);
      font-size: 11px;
      line-height: 1;
      font-weight: 900;
      text-shadow: 0 0 2px rgba(255, 255, 255, 0.9);
    }
    .court-marker.made { color: #067647; }
    .court-marker.miss { color: #b42318; }
    .court-key {
      position: static;
      padding: 2px 6px;
      border-radius: 6px;
      font-size: 11px;
      background: rgba(255, 255, 255, 0.88);
      border: 1px solid #e6e9ee;
      color: #344054;
    }
    .court-key .made { color: #067647; font-weight: 700; }
    .court-key .miss { color: #b42318; font-weight: 700; }
    .court-empty {
      position: absolute;
      left: 50%;
      top: 50%;
      transform: translate(-50%, -50%);
      font-size: 12px;
      color: var(--muted);
      background: rgba(255, 255, 255, 0.9);
      border: 1px solid #e6e9ee;
      border-radius: 6px;
      padding: 4px 7px;
    }
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
      .range-body-player { grid-template-columns: 1fr; }
      .court-chart { width: 100%; max-width: 368px; }
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
      <h3>Player Matchup Overview</h3>
      <div class="table-wrap">
        <table id="playerMatchupTable"></table>
      </div>
    </section>

    <section class="card">
      <h3>Player Defense Overview</h3>
      <div class="table-wrap">
        <table id="playerDefenseTable"></table>
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
        <article class="range-panel range-panel-player">
          <div class="events-head">
            <label class="small">Player
              <select id="rangePlayerFilter"></select>
            </label>
          </div>
          <div class="range-body range-body-player">
            <div id="playerRangePie"></div>
            <div id="playerRangeLegend" class="range-legend"></div>
            <div class="court-wrap">
              <div id="playerCourtChart" class="court-chart"></div>
              <div class="court-key"><span class="made">O</span> scored | <span class="miss">X</span> missed</div>
            </div>
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
    const courtImageUrl = {{ court_image_url | tojson }};

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

    function emptyShotStat() {
      return { m: 0, a: 0 };
    }

    function addShotStat(stat, made) {
      stat.a += 1;
      if (made) stat.m += 1;
    }

    function shotStatPct(stat) {
      return stat.a ? ((stat.m / stat.a) * 100).toFixed(1) : "0.0";
    }

    function shotStatRatio(stat) {
      return stat.a ? (stat.m / stat.a) : null;
    }

    function shotStatHtml(stat) {
      if (!stat.a) return "";
      return `${stat.m}/${stat.a}/${shotStatPct(stat)}%`;
    }

    function defensePct(stat) {
      return stat.a ? (((stat.a - stat.m) / stat.a) * 100).toFixed(1) : "";
    }

    function defensePctValue(stat) {
      return stat.a ? ((stat.a - stat.m) / stat.a) : null;
    }

    function defensePctHtml(stat) {
      const pct = defensePct(stat);
      return pct ? `${pct}%` : "";
    }

    function defenseStatHtml(stat) {
      const pct = defensePct(stat);
      if (!pct) return "";
      return `${stat.a - stat.m}/${stat.a} ${pct}%`;
    }

    function formatSignedPctPoints(value) {
      const prefix = value > 0 ? "+" : "";
      return `${prefix}${value.toFixed(1)}pp`;
    }

    function impactScore(onValue, offValue, attemptsOn, attemptsOff) {
      if (onValue === null || offValue === null) return null;
      const totalAttempts = attemptsOn + attemptsOff;
      if (!totalAttempts) return null;
      return (onValue - offValue) * Math.log1p(totalAttempts);
    }

    function rankImpactMarks(rows, key) {
      const ranked = rows
        .map((row, idx) => ({ idx, score: row[key] }))
        .filter(item => Number.isFinite(item.score));

      const positive = ranked
        .filter(item => item.score > 0)
        .sort((a, b) => b.score - a.score)
        .slice(0, 2)
        .map(item => item.idx);

      const negative = ranked
        .filter(item => item.score < 0)
        .sort((a, b) => a.score - b.score)
        .slice(0, 2)
        .map(item => item.idx);

      return { positive: new Set(positive), negative: new Set(negative) };
    }

    function impactMarksHtml(marks) {
      if (!marks.length) return "";
      return `<span class="impact-marks">${marks.join("")}</span>`;
    }

    function emptyPlayerMatchupStats() {
      return {
        defended: emptyShotStat(),
        openClose: emptyShotStat(),
        openMid: emptyShotStat(),
        openThree: emptyShotStat(),
        openTotal: emptyShotStat(),
        withPass: emptyShotStat(),
        withoutPass: emptyShotStat(),
        teamOn: emptyShotStat(),
        teamOff: emptyShotStat()
      };
    }

    function isOpenShotEvent(ev, defendingTeamObj) {
      return normalizeSlot(ev.defender, defendingTeamObj.players.length) === null;
    }

    function passReceivedOnShot(ev, attackingTeamObj) {
      return normalizeSlot(ev.assistant, attackingTeamObj.players.length) !== null;
    }

    function createStarterActiveSet(teamObj) {
      const active = new Set();
      teamObj.players.forEach((player, idx) => {
        if (player.starter) active.add(idx);
      });
      return active;
    }

    function applySubEvent(activeSet, ev, teamObj) {
      if (String(ev.sub_type) === "9520") return;
      const playerIn = normalizePlayerIndex(ev.player_in, teamObj.players.length);
      const playerOut = normalizePlayerIndex(ev.player_out, teamObj.players.length);
      if (playerOut !== null) activeSet.delete(playerOut);
      if (playerIn !== null) activeSet.add(playerIn);
    }

    function renderPlayerMatchupOverview() {
      const teamStatsBySide = [
        home.players.map(() => emptyPlayerMatchupStats()),
        away.players.map(() => emptyPlayerMatchupStats())
      ];
      const activeBySide = {
        0: createStarterActiveSet(home),
        1: createStarterActiveSet(away)
      };

      data.events.forEach(ev => {
        if (ev.event_type === "shot") {
          const teamSide = Number(ev.attacking_team);
          const teamObj = getTeamBySide(teamSide);
          const defendingTeamObj = getTeamBySide(Number(ev.defending_team));
          const shooterIdx = normalizeSlot(ev.attacker, teamObj.players.length);
          const made = madeResults.has(String(ev.shot_result));

          teamObj.players.forEach((_, playerIdx) => {
            const target = teamStatsBySide[teamSide][playerIdx];
            addShotStat(activeBySide[teamSide].has(playerIdx) ? target.teamOn : target.teamOff, made);
          });

          if (shooterIdx !== null) {
            const shooterStats = teamStatsBySide[teamSide][shooterIdx];

            if (!isOpenShotEvent(ev, defendingTeamObj)) {
              addShotStat(shooterStats.defended, made);
            }

            if (isOpenShotEvent(ev, defendingTeamObj)) {
              const range = getShotRange(ev.shot_type);
              if (range === "paint") addShotStat(shooterStats.openClose, made);
              else if (range === "jump") addShotStat(shooterStats.openMid, made);
              else if (range === "three") addShotStat(shooterStats.openThree, made);
              addShotStat(shooterStats.openTotal, made);
            }

            if (passReceivedOnShot(ev, teamObj)) addShotStat(shooterStats.withPass, made);
            else addShotStat(shooterStats.withoutPass, made);
          }

          return;
        }

        if (ev.event_type === "sub") {
          const teamSide = Number(ev.team);
          applySubEvent(activeBySide[teamSide], ev, getTeamBySide(teamSide));
        }
      });

      const rows = [home, away].flatMap((teamObj, side) =>
        teamObj.players.map((player, idx) => ({
          team: teamObj.name,
          name: player.name,
          defended: teamStatsBySide[side][idx].defended,
          openClose: teamStatsBySide[side][idx].openClose,
          openMid: teamStatsBySide[side][idx].openMid,
          openThree: teamStatsBySide[side][idx].openThree,
          openTotal: teamStatsBySide[side][idx].openTotal,
          teamOn: teamStatsBySide[side][idx].teamOn,
          teamOff: teamStatsBySide[side][idx].teamOff,
          withPass: teamStatsBySide[side][idx].withPass,
          withoutPass: teamStatsBySide[side][idx].withoutPass,
          fgImpactScore: impactScore(
            shotStatRatio(teamStatsBySide[side][idx].teamOn),
            shotStatRatio(teamStatsBySide[side][idx].teamOff),
            teamStatsBySide[side][idx].teamOn.a,
            teamStatsBySide[side][idx].teamOff.a
          ),
          fgImpactDiff: (() => {
            const onValue = shotStatRatio(teamStatsBySide[side][idx].teamOn);
            const offValue = shotStatRatio(teamStatsBySide[side][idx].teamOff);
            return onValue === null || offValue === null ? null : (onValue - offValue) * 100;
          })()
        }))
      );

      const fgImpactRanks = rankImpactMarks(rows, "fgImpactScore");

      document.getElementById("playerMatchupTable").innerHTML = `
        <thead>
          <tr>
            <th>Player</th>
            <th>Team</th>
            <th>With Defense</th>
            <th>Open Close</th>
            <th>Open Mid</th>
            <th>Open 3PT</th>
            <th>Open Total</th>
            <th>Team FG On</th>
            <th>Team FG Off</th>
            <th>Pass Received</th>
            <th>No Pass</th>
          </tr>
        </thead>
        <tbody>
          ${rows.map((row, idx) => {
            const marks = [];
            if (fgImpactRanks.positive.has(idx)) {
              marks.push(`<span class="impact-mark pos" title="Top positive FG on/off impact. Swing: ${formatSignedPctPoints(row.fgImpactDiff)} | Score: ${row.fgImpactScore.toFixed(3)}">FG+</span>`);
            }
            if (fgImpactRanks.negative.has(idx)) {
              marks.push(`<span class="impact-mark neg" title="Top negative FG on/off impact. Swing: ${formatSignedPctPoints(row.fgImpactDiff)} | Score: ${row.fgImpactScore.toFixed(3)}">FG-</span>`);
            }
            return `
            <tr>
              <td>${row.name}${impactMarksHtml(marks)}</td>
              <td>${row.team}</td>
              <td>${shotStatHtml(row.defended)}</td>
              <td>${shotStatHtml(row.openClose)}</td>
              <td>${shotStatHtml(row.openMid)}</td>
              <td>${shotStatHtml(row.openThree)}</td>
              <td>${shotStatHtml(row.openTotal)}</td>
              <td>${shotStatHtml(row.teamOn)}</td>
              <td>${shotStatHtml(row.teamOff)}</td>
              <td>${shotStatHtml(row.withPass)}</td>
              <td>${shotStatHtml(row.withoutPass)}</td>
            </tr>
          `;
          }).join("")}
        </tbody>
      `;
    }

    function emptyPlayerDefenseStats() {
      return {
        teamDefOn: emptyShotStat(),
        teamDefOff: emptyShotStat(),
        defendedTotal: emptyShotStat(),
        defendedClose: emptyShotStat(),
        defendedMid: emptyShotStat(),
        defendedThree: emptyShotStat()
      };
    }

    function renderPlayerDefenseOverview() {
      const teamStatsBySide = [
        home.players.map(() => emptyPlayerDefenseStats()),
        away.players.map(() => emptyPlayerDefenseStats())
      ];
      const activeBySide = {
        0: createStarterActiveSet(home),
        1: createStarterActiveSet(away)
      };

      data.events.forEach(ev => {
        if (ev.event_type === "shot") {
          const defSide = Number(ev.defending_team);
          const defTeamObj = getTeamBySide(defSide);
          const defenderIdx = normalizeSlot(ev.defender, defTeamObj.players.length);
          const made = madeResults.has(String(ev.shot_result));

          defTeamObj.players.forEach((_, playerIdx) => {
            const target = teamStatsBySide[defSide][playerIdx];
            addShotStat(activeBySide[defSide].has(playerIdx) ? target.teamDefOn : target.teamDefOff, made);
          });

          if (defenderIdx !== null) {
            const defenderStats = teamStatsBySide[defSide][defenderIdx];
            addShotStat(defenderStats.defendedTotal, made);
            const range = getShotRange(ev.shot_type);
            if (range === "paint") addShotStat(defenderStats.defendedClose, made);
            else if (range === "jump") addShotStat(defenderStats.defendedMid, made);
            else if (range === "three") addShotStat(defenderStats.defendedThree, made);
          }

          return;
        }

        if (ev.event_type === "sub") {
          const teamSide = Number(ev.team);
          applySubEvent(activeBySide[teamSide], ev, getTeamBySide(teamSide));
        }
      });

      const rows = [home, away].flatMap((teamObj, side) =>
        teamObj.players.map((player, idx) => ({
          team: teamObj.name,
          name: player.name,
          teamDefOn: teamStatsBySide[side][idx].teamDefOn,
          teamDefOff: teamStatsBySide[side][idx].teamDefOff,
          defendedTotal: teamStatsBySide[side][idx].defendedTotal,
          defendedClose: teamStatsBySide[side][idx].defendedClose,
          defendedMid: teamStatsBySide[side][idx].defendedMid,
          defendedThree: teamStatsBySide[side][idx].defendedThree,
          defImpactScore: impactScore(
            defensePctValue(teamStatsBySide[side][idx].teamDefOn),
            defensePctValue(teamStatsBySide[side][idx].teamDefOff),
            teamStatsBySide[side][idx].teamDefOn.a,
            teamStatsBySide[side][idx].teamDefOff.a
          ),
          defImpactDiff: (() => {
            const onValue = defensePctValue(teamStatsBySide[side][idx].teamDefOn);
            const offValue = defensePctValue(teamStatsBySide[side][idx].teamDefOff);
            return onValue === null || offValue === null ? null : (onValue - offValue) * 100;
          })()
        }))
      );

      const defImpactRanks = rankImpactMarks(rows, "defImpactScore");

      document.getElementById("playerDefenseTable").innerHTML = `
        <thead>
          <tr>
            <th>Player</th>
            <th>Team</th>
            <th>Team Def On</th>
            <th>Team Def Off</th>
            <th>Defended Total</th>
            <th>Defended Close</th>
            <th>Defended Mid</th>
            <th>Defended 3PT</th>
          </tr>
        </thead>
        <tbody>
          ${rows.map((row, idx) => {
            const marks = [];
            if (defImpactRanks.positive.has(idx)) {
              marks.push(`<span class="impact-mark pos" title="Top positive DEF on/off impact. Swing: ${formatSignedPctPoints(row.defImpactDiff)} | Score: ${row.defImpactScore.toFixed(3)}">DEF+</span>`);
            }
            if (defImpactRanks.negative.has(idx)) {
              marks.push(`<span class="impact-mark neg" title="Top negative DEF on/off impact. Swing: ${formatSignedPctPoints(row.defImpactDiff)} | Score: ${row.defImpactScore.toFixed(3)}">DEF-</span>`);
            }
            return `
            <tr>
              <td>${row.name}${impactMarksHtml(marks)}</td>
              <td>${row.team}</td>
              <td>${defensePctHtml(row.teamDefOn)}</td>
              <td>${defensePctHtml(row.teamDefOff)}</td>
              <td>${defenseStatHtml(row.defendedTotal)}</td>
              <td>${defenseStatHtml(row.defendedClose)}</td>
              <td>${defenseStatHtml(row.defendedMid)}</td>
              <td>${defenseStatHtml(row.defendedThree)}</td>
            </tr>
          `;
          }).join("")}
        </tbody>
      `;
    }

    function renderPie(targetId, legendId, title, counts, madeCounts) {
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
        <div class="row"><span class="dot three"></span>Three: <strong>${counts.three}</strong> (made <strong>${madeCounts.three}</strong>)</div>
        <div class="row"><span class="dot jump"></span>Jump: <strong>${counts.jump}</strong> (made <strong>${madeCounts.jump}</strong>)</div>
        <div class="row"><span class="dot paint"></span>Paint: <strong>${counts.paint}</strong> (made <strong>${madeCounts.paint}</strong>)</div>
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
      const playerMadeCounts = emptyRangeCounts();

      shotEvents.forEach(ev => {
        if (Number(ev.attacking_team) !== pside) return;
        const idx = normalizeSlot(ev.attacker, pTeam.players.length);
        if (idx !== pslot) return;
        const range = getShotRange(ev.shot_type);
        playerCounts[range] += 1;
        if (madeResults.has(String(ev.shot_result))) {
          playerMadeCounts[range] += 1;
        }
      });

      renderPie("playerRangePie", "playerRangeLegend", "player shots", playerCounts, playerMadeCounts);
      renderPlayerCourtChart(pside, pslot, pTeam);

      const tside = Number(rangeTeamFilter.value);
      const teamCounts = emptyRangeCounts();
      const teamMadeCounts = emptyRangeCounts();
      shotEvents.forEach(ev => {
        if (Number(ev.attacking_team) !== tside) return;
        const range = getShotRange(ev.shot_type);
        teamCounts[range] += 1;
        if (madeResults.has(String(ev.shot_result))) {
          teamMadeCounts[range] += 1;
        }
      });

      renderPie("teamRangePie", "teamRangeLegend", "team shots", teamCounts, teamMadeCounts);
    }

    function renderPlayerCourtChart(side, slot, teamObj) {
      const courtW = 368;
      const courtH = 192;
      const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
      const chart = document.getElementById("playerCourtChart");
      chart.style.backgroundImage = courtImageUrl ? `url("${courtImageUrl}")` : "none";

      const marks = [];
      shotEvents.forEach(ev => {
        if (Number(ev.attacking_team) !== side) return;
        const idx = normalizeSlot(ev.attacker, teamObj.players.length);
        if (idx !== slot) return;
        const x = Number(ev.shot_pos_x);
        const y = Number(ev.shot_pos_y);
        if (!Number.isFinite(x) || !Number.isFinite(y)) return;
        const made = madeResults.has(String(ev.shot_result));
        marks.push({
          x: clamp(x, 0, courtW),
          y: clamp(y, 0, courtH),
          made
        });
      });

      const markersHtml = marks.map(m => `
        <span class="court-marker ${m.made ? "made" : "miss"}" style="left:${m.x}px;top:${m.y}px;">
          ${m.made ? "O" : "X"}
        </span>
      `).join("");

      const emptyHtml = marks.length === 0 ? `<div class="court-empty">No shot positions</div>` : "";
      chart.innerHTML = `
        ${markersHtml}
        ${emptyHtml}
      `;
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

    function normalizePlayerIndex(rawIndex, playersLen) {
      const n = Number(rawIndex);
      if (!Number.isFinite(n)) return null;
      if (n >= 0 && n < playersLen) return n;
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
    renderPlayerMatchupOverview();
    renderPlayerDefenseOverview();
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


ANIMATION_REPORT_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>BBInsider Animation {{ matchid }}</title>
  <style>
    :root {
      --bg: #f4f7f8;
      --panel: #ffffff;
      --ink: #1f2328;
      --muted: #5f6b76;
      --line: #d9dee5;
      --home: #0d3b66;
      --away: #9a031e;
      --court: #276749;
      --wood: #d7a45f;
      --shadow: 0 10px 30px rgba(0, 0, 0, 0.08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
      background: linear-gradient(180deg, #eef5f7, var(--bg));
      color: var(--ink);
    }
    .wrap {
      width: min(1280px, calc(100% - 28px));
      margin: 22px auto 38px;
    }
    .topbar {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: flex-start;
      margin-bottom: 14px;
      flex-wrap: wrap;
    }
    a { color: #0d47a1; font-weight: 700; text-decoration: none; }
    h1 { margin: 0 0 5px; font-size: 28px; }
    .small { color: var(--muted); font-size: 13px; }
    .scoreboard {
      display: grid;
      grid-template-columns: 1fr auto 1fr;
      align-items: center;
      gap: 12px;
      background: #111827;
      color: #fff;
      border-radius: 8px;
      padding: 12px;
      box-shadow: var(--shadow);
      margin-bottom: 14px;
    }
    .team-score { min-width: 0; }
    .team-score.away { text-align: right; }
    .team-name {
      font-size: 14px;
      font-weight: 800;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .score {
      font-size: 34px;
      line-height: 1;
      font-weight: 900;
      font-variant-numeric: tabular-nums;
      margin-top: 4px;
    }
    .clock {
      text-align: center;
      border: 1px solid rgba(255,255,255,0.18);
      border-radius: 8px;
      padding: 9px 16px;
      min-width: 150px;
    }
    .clock-main {
      font-size: 28px;
      font-weight: 900;
      font-variant-numeric: tabular-nums;
    }
    .grid {
      display: grid;
      grid-template-columns: minmax(260px, 0.58fr) minmax(460px, 1.3fr) minmax(260px, 0.58fr);
      gap: 14px;
      align-items: start;
    }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      overflow: hidden;
    }
    .panel h2 {
      margin: 0;
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      font-size: 16px;
    }
    .court-panel { padding: 12px; }
    .court-stage {
      position: relative;
      width: 100%;
      aspect-ratio: 368 / 192;
      min-height: 300px;
      background-color: var(--wood);
      background-size: 100% 100%;
      background-position: center;
      border: 4px solid #1f2937;
      border-radius: 8px;
      overflow: hidden;
    }
    canvas {
      width: 100%;
      height: 100%;
      display: block;
    }
    .controls {
      display: grid;
      gap: 10px;
      padding: 12px;
      border-top: 1px solid var(--line);
      background: #fbfcfd;
    }
    .control-row {
      display: flex;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
    }
    button, select, input {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 9px 10px;
      font: inherit;
      background: #fff;
      color: var(--ink);
    }
    button {
      background: #0d47a1;
      border-color: #0d47a1;
      color: #fff;
      font-weight: 800;
      cursor: pointer;
    }
    button.secondary {
      background: #fff;
      color: #0d47a1;
    }
    input[type="range"] {
      flex: 1 1 260px;
      padding: 0;
      accent-color: #0d47a1;
    }
    .jump-fields {
      display: grid;
      grid-template-columns: minmax(94px, auto) minmax(80px, auto) minmax(80px, auto) auto;
      gap: 8px;
      align-items: end;
    }
    .jump-fields label {
      display: grid;
      gap: 4px;
      font-size: 12px;
      color: var(--muted);
      font-weight: 700;
    }
    .event-card {
      padding: 12px;
      border-top: 1px solid var(--line);
      background: #fff;
      min-height: 90px;
    }
    .event-title {
      font-size: 12px;
      color: var(--muted);
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0;
    }
    .event-comment {
      margin: 6px 0 0;
      font-size: 15px;
      line-height: 1.4;
    }
    .box-score {
      max-height: 720px;
      overflow: auto;
    }
    .team-box h3 {
      margin: 0;
      padding: 10px 12px;
      font-size: 15px;
      background: #f7f9fc;
      position: sticky;
      top: 0;
      z-index: 1;
    }
    .team-color-chip {
      display: inline-block;
      width: 12px;
      height: 12px;
      border-radius: 50%;
      margin-right: 7px;
      border: 2px solid #fff;
      box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.22);
      vertical-align: -1px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 11px;
    }
    th, td {
      padding: 6px 6px;
      border-bottom: 1px solid #edf1f5;
      white-space: nowrap;
      text-align: right;
      font-variant-numeric: tabular-nums;
    }
    th:first-child, td:first-child {
      text-align: left;
      min-width: 116px;
      position: sticky;
      left: 0;
      background: #fff;
    }
    th {
      color: var(--muted);
      background: #fbfcfd;
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0;
    }
    tr.shot-made td {
      background: #eefaf0;
    }
    tr.shot-missed td {
      background: #fff1f1;
    }
    tr.shot-made td:first-child {
      box-shadow: inset 4px 0 0 #22c55e;
    }
    tr.shot-missed td:first-child {
      box-shadow: inset 4px 0 0 #ef4444;
    }
    .legend {
      display: flex;
      gap: 12px;
      align-items: center;
      flex-wrap: wrap;
      padding: 10px 12px 0;
    }
    .swatch {
      display: inline-block;
      width: 12px;
      height: 12px;
      border-radius: 50%;
      margin-right: 5px;
      vertical-align: -1px;
    }
    .home-dot { background: var(--home); }
    .away-dot { background: var(--away); }
    @media (max-width: 980px) {
      .grid { grid-template-columns: 1fr; }
      .court-wrap { order: 1; }
      .home-box { order: 2; }
      .away-box { order: 3; }
      .court-stage { min-height: 230px; }
      .jump-fields { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .jump-fields button { grid-column: 1 / -1; }
    }
  </style>
</head>
<body>
  <main class="wrap">
    <div class="topbar">
      <div>
        <h1>Game Animation</h1>
        <div class="small">Match {{ matchid }} | BBAPI user: {{ username }}</div>
      </div>
      <a href="/">New report</a>
    </div>

    <section class="scoreboard">
      <div class="team-score">
        <div class="team-name" id="homeName"></div>
        <div class="score" id="homeScore">0</div>
      </div>
      <div class="clock">
        <div class="small" id="periodLabel">Q1</div>
        <div class="clock-main" id="clockLabel">12:00</div>
        <div class="small" id="speedLabel">1x speed</div>
      </div>
      <div class="team-score away">
        <div class="team-name" id="awayName"></div>
        <div class="score" id="awayScore">0</div>
      </div>
    </section>

    <section class="grid">
      <aside class="panel team-box home-box">
        <h2>Live Box Score</h2>
        <div class="box-score" id="homeBoxScore"></div>
      </aside>

      <div class="panel court-wrap">
        <div class="court-panel">
          <div class="court-stage" id="courtStage">
            <canvas id="courtCanvas"></canvas>
          </div>
          <div class="legend">
            <span><span class="swatch home-dot"></span><span id="homeLegend"></span></span>
            <span><span class="swatch away-dot"></span><span id="awayLegend"></span></span>
            <span class="small">Dots move between inferred event positions; shot locations use tracked coordinates.</span>
          </div>
        </div>
        <div class="controls">
          <div class="control-row">
            <button type="button" id="playBtn">Play</button>
            <button type="button" class="secondary" id="restartBtn">Restart</button>
            <button type="button" class="secondary" id="speedBtn">2x speed</button>
            <input type="range" id="timeSlider" min="0" max="2880" step="1" value="0" />
          </div>
          <div class="jump-fields">
            <label>Quarter
              <select id="jumpQuarter"></select>
            </label>
            <label>Minute
              <input id="jumpMinute" type="number" min="0" max="12" value="12" />
            </label>
            <label>Second
              <input id="jumpSecond" type="number" min="0" max="59" value="0" />
            </label>
            <button type="button" id="jumpBtn">Jump</button>
          </div>
        </div>
        <div class="event-card">
          <div class="event-title" id="eventMeta">Opening tip</div>
          <p class="event-comment" id="eventComment">Press play or jump to a game time.</p>
        </div>
      </div>

      <aside class="panel team-box away-box">
        <h2>Live Box Score</h2>
        <div class="box-score" id="awayBoxScore"></div>
      </aside>
    </section>
  </main>

  <script>
    const data = {{ report_json | tojson }};
    const courtImageUrl = {{ court_image_url | tojson }};
    const home = data.teamHome;
    const away = data.teamAway;
    const events = data.events
      .map((ev, idx) => ({ ...ev, feed_index: idx + 1 }))
      .filter(ev => typeof ev.gameclock === "number" && ev.gameclock >= 0)
      .sort((a, b) => a.gameclock - b.gameclock || a.feed_index - b.feed_index);
    const visualEvents = buildVisualEvents(events);
    const maxClock = Math.max(2880, ...events.map(ev => ev.gameclock));
    const madeResults = new Set(["1", "2", "5"]);
    const missedNoFgResults = new Set(["4"]);

    const canvas = document.getElementById("courtCanvas");
    const ctx = canvas.getContext("2d");
    const stage = document.getElementById("courtStage");
    const playBtn = document.getElementById("playBtn");
    const restartBtn = document.getElementById("restartBtn");
    const speedBtn = document.getElementById("speedBtn");
    const slider = document.getElementById("timeSlider");
    const jumpQuarter = document.getElementById("jumpQuarter");
    const jumpMinute = document.getElementById("jumpMinute");
    const jumpSecond = document.getElementById("jumpSecond");

    let currentTime = 0;
    let playing = false;
    let speed = 1;
    const baseGameSecondsPerRealSecond = 9;
    let lastFrame = null;
    let lastRenderedSecond = -1;
    let visualState = createInitialVisualState();
    let latestReplay = replayTo(0);

    stage.style.backgroundImage = courtImageUrl ? `url("${courtImageUrl}")` : "none";
    slider.max = String(maxClock);
    document.getElementById("homeName").textContent = home.name;
    document.getElementById("awayName").textContent = away.name;
    document.getElementById("homeLegend").textContent = home.name;
    document.getElementById("awayLegend").textContent = away.name;

    function periodLength(period) {
      return period <= 4 ? 720 : 420;
    }

    function periodStart(period) {
      return period <= 4 ? (period - 1) * 720 : 2880 + (period - 5) * 420;
    }

    function periodFromClock(clock) {
      if (clock < 720) return 1;
      if (clock < 1440) return 2;
      if (clock < 2160) return 3;
      if (clock < 2880) return 4;
      return 5 + Math.floor((clock - 2880) / 420);
    }

    function periodLabel(period) {
      return period <= 4 ? `Q${period}` : `OT${period - 4}`;
    }

    function clockRemaining(clock) {
      const period = periodFromClock(clock);
      const start = periodStart(period);
      const len = periodLength(period);
      const remaining = Math.max(0, len - Math.floor(clock - start));
      return {
        period,
        minutes: Math.floor(remaining / 60),
        seconds: remaining % 60
      };
    }

    function formatClock(clock) {
      const item = clockRemaining(clock);
      return `${String(item.minutes).padStart(2, "0")}:${String(item.seconds).padStart(2, "0")}`;
    }

    function formatComments(comments) {
      if (!Array.isArray(comments) || comments.length === 0) return "(no commentary)";
      return comments.join(" ");
    }

    function teamBySide(side) {
      return Number(side) === 0 ? home : away;
    }

    function normalizeSlot(rawSlot, playersLen) {
      const n = Number(rawSlot);
      if (!Number.isFinite(n)) return null;
      if (n >= 1 && n <= playersLen) return n - 1;
      return null;
    }

    function playerName(side, slot, fallback = "") {
      const team = teamBySide(side);
      const idx = normalizeSlot(slot, team.players.length);
      return idx === null ? fallback : (team.players[idx]?.name || fallback);
    }

    function playerIndex(rawIndex, playersLen) {
      const n = Number(rawIndex);
      if (!Number.isFinite(n)) return null;
      if (n >= 0 && n < playersLen) return n;
      return null;
    }

    function blankStats() {
      return {
        secs: 0, pts: 0, fgm: 0, fga: 0, tpm: 0, tpa: 0,
        ftm: 0, fta: 0, or: 0, dr: 0, tr: 0,
        ast: 0, to: 0, stl: 0, blk: 0, pf: 0, pm: 0
      };
    }

    function cloneActiveStarters(team) {
      const set = new Set();
      team.players.forEach((player, idx) => {
        if (player.starter) set.add(idx);
      });
      return set;
    }

    function addPlayerStat(stats, side, idx, key, value) {
      if (idx === null || idx < 0 || !stats.players[side]?.[idx]) return;
      stats.players[side][idx][key] += value;
      if (key === "or" || key === "dr") stats.players[side][idx].tr += value;
    }

    function addTeamStat(stats, side, key, value) {
      stats.teams[side][key] += value;
      if (key === "or" || key === "dr") stats.teams[side].tr += value;
    }

    function addStat(stats, side, idx, key, value) {
      addTeamStat(stats, side, key, value);
      addPlayerStat(stats, side, idx, key, value);
    }

    function updateActiveSeconds(stats, side, active, activeSince, toTime) {
      active[side].forEach(idx => {
        const from = activeSince[side][idx] ?? 0;
        const delta = Math.max(0, toTime - from);
        stats.players[side][idx].secs += delta;
        activeSince[side][idx] = toTime;
      });
    }

    function applySub(active, activeSince, stats, ev, time) {
      const side = Number(ev.team);
      if (String(ev.sub_type) === "9520") return;
      updateActiveSeconds(stats, side, active, activeSince, time);
      const team = teamBySide(side);
      const outIdx = playerIndex(ev.player_out, team.players.length);
      const inIdx = playerIndex(ev.player_in, team.players.length);
      if (outIdx !== null) active[side].delete(outIdx);
      if (inIdx !== null) {
        active[side].add(inIdx);
        activeSince[side][inIdx] = time;
      }
    }

    function replayTo(clock) {
      const stats = {
        teams: [blankStats(), blankStats()],
        players: [home.players.map(blankStats), away.players.map(blankStats)]
      };
      const active = [cloneActiveStarters(home), cloneActiveStarters(away)];
      const activeSince = [
        home.players.map(() => 0),
        away.players.map(() => 0)
      ];
      let lastEvent = null;

      for (const ev of events) {
        if (ev.gameclock > clock) break;
        lastEvent = ev;

        if (ev.event_type === "shot") {
          const side = Number(ev.attacking_team);
          const defSide = Number(ev.defending_team);
          const team = teamBySide(side);
          const defTeam = teamBySide(defSide);
          const shooter = normalizeSlot(ev.attacker, team.players.length);
          const defender = normalizeSlot(ev.defender, defTeam.players.length);
          const assistant = normalizeSlot(ev.assistant, team.players.length);
          const result = String(ev.shot_result);
          const isThree = Number(ev.shot_type) >= 100 && Number(ev.shot_type) < 200;
          const made = madeResults.has(result);
          const countFg = !missedNoFgResults.has(result);

          if (countFg) {
            addStat(stats, side, shooter, "fga", 1);
            if (isThree) addStat(stats, side, shooter, "tpa", 1);
          }
          if (made) {
            const pts = isThree ? 3 : 2;
            addStat(stats, side, shooter, "fgm", 1);
            addStat(stats, side, shooter, "pts", pts);
            if (isThree) addStat(stats, side, shooter, "tpm", 1);
            if (assistant !== null) addStat(stats, side, assistant, "ast", 1);
            active[side].forEach(idx => addPlayerStat(stats, side, idx, "pm", pts));
            active[defSide].forEach(idx => addPlayerStat(stats, defSide, idx, "pm", -pts));
            stats.teams[side].pm += pts;
            stats.teams[defSide].pm -= pts;
          }
          if (result === "3" && defender !== null) addStat(stats, defSide, defender, "blk", 1);
        } else if (ev.event_type === "free_throw") {
          const side = Number(ev.attacking_team);
          const defSide = side === 0 ? 1 : 0;
          const team = teamBySide(side);
          const shooter = normalizeSlot(ev.attacker, team.players.length);
          addStat(stats, side, shooter, "fta", 1);
          if (madeResults.has(String(ev.shot_result))) {
            addStat(stats, side, shooter, "ftm", 1);
            addStat(stats, side, shooter, "pts", 1);
            active[side].forEach(idx => addPlayerStat(stats, side, idx, "pm", 1));
            active[defSide].forEach(idx => addPlayerStat(stats, defSide, idx, "pm", -1));
            stats.teams[side].pm += 1;
            stats.teams[defSide].pm -= 1;
          }
        } else if (ev.event_type === "rebound") {
          const off = String(ev.rebound_type) === "9317";
          const side = off ? Number(ev.attacking_team) : Number(ev.defending_team);
          const team = teamBySide(side);
          const idx = normalizeSlot(ev.attacker, team.players.length);
          addStat(stats, side, idx, off ? "or" : "dr", 1);
        } else if (ev.event_type === "interrupt") {
          const side = Number(ev.attacking_team);
          const defSide = Number(ev.defending_team);
          const team = teamBySide(side);
          const defTeam = teamBySide(defSide);
          const attacker = normalizeSlot(ev.attacker, team.players.length);
          const defender = normalizeSlot(ev.defender, defTeam.players.length);
          addStat(stats, side, attacker, "to", 1);
          if (["807", "808"].includes(String(ev.interrupt_type)) && defender !== null) {
            addStat(stats, defSide, defender, "stl", 1);
          }
        } else if (ev.event_type === "foul") {
          const side = Number(ev.attacking_team);
          const defSide = Number(ev.defending_team);
          if (String(ev.foul_type) === "803") {
            const team = teamBySide(side);
            const attacker = normalizeSlot(ev.attacker, team.players.length);
            addStat(stats, side, attacker, "to", 1);
            addStat(stats, side, attacker, "pf", 1);
          } else {
            const defTeam = teamBySide(defSide);
            const defender = normalizeSlot(ev.defender, defTeam.players.length);
            addStat(stats, defSide, defender, "pf", 1);
          }
        } else if (ev.event_type === "sub") {
          applySub(active, activeSince, stats, ev, ev.gameclock);
        }
      }

      [0, 1].forEach(side => updateActiveSeconds(stats, side, active, activeSince, clock));
      return { stats, active, lastEvent };
    }

    function createInitialVisualState() {
      const positions = [[], []];
      [home, away].forEach((team, side) => {
        team.players.forEach((_, idx) => {
          const row = idx % 5;
          const xBase = side === 0 ? 92 : 276;
          positions[side][idx] = {
            x: xBase,
            y: 38 + row * 29,
            targetX: xBase,
            targetY: 38 + row * 29
          };
        });
      });
      return {
        positions,
        visible: [cloneActiveStarters(home), cloneActiveStarters(away)],
        ball: { x: 184, y: 96, targetX: 184, targetY: 96 }
      };
    }

    function clamp(v, lo, hi) {
      return Math.max(lo, Math.min(hi, v));
    }

    function easeInOut(t) {
      const p = clamp(t, 0, 1);
      return p * p * (3 - 2 * p);
    }

    function lerp(a, b, t) {
      return a + (b - a) * t;
    }

    function mixPoint(a, b, t) {
      const p = easeInOut(t);
      return { x: lerp(a.x, b.x, p), y: lerp(a.y, b.y, p) };
    }

    function basketPoint(side) {
      return { x: side === 0 ? 347 : 21, y: 96 };
    }

    function isNormalRebound(ev) {
      return ev?.event_type === "rebound" && ["9317", "9318"].includes(String(ev.rebound_type));
    }

    function buildVisualEvents(feedEvents) {
      const out = [];
      let previousAction = null;
      feedEvents.forEach(ev => {
        if (["interrupt", "sub"].includes(ev.event_type)) return;

        if (ev.event_type === "rebound") {
          if (!isNormalRebound(ev) || previousAction?.event_type !== "shot") return;
          out.push(ev);
          previousAction = ev;
          return;
        }

        out.push(ev);
        if (["shot", "free_throw", "foul", "break"].includes(ev.event_type)) {
          previousAction = ev;
        }
      });
      return out;
    }

    function reboundPossessionSide(ev) {
      if (!isNormalRebound(ev)) return null;
      return String(ev.rebound_type) === "9317" ? Number(ev.attacking_team) : Number(ev.defending_team);
    }

    function eventPairAt(clock) {
      let prev = null;
      let next = null;
      for (const ev of visualEvents) {
        if (ev.gameclock <= clock) {
          prev = ev;
          continue;
        }
        next = ev;
        break;
      }

      const start = prev ? prev.gameclock : 0;
      const end = next ? next.gameclock : Math.max(start + 1, maxClock);
      const span = Math.max(1, end - start);
      return {
        prev,
        next,
        progress: clamp((clock - start) / span, 0, 1)
      };
    }

    function targetForPlayer(side, idx, active, ev) {
      const activeList = [...active[side]];
      const activeIndex = Math.max(0, activeList.indexOf(idx));
      const possessionSide = ev ? Number(ev.attacking_team ?? ev.team ?? side) : 0;
      const attacking = side === possessionSide;
      const basketX = side === 0 ? 347 : 21;
      const centerX = side === 0 ? 246 : 122;
      const defendX = side === 0 ? 112 : 256;
      const lanes = [45, 75, 100, 125, 154];
      let x = attacking ? centerX + (side === 0 ? activeIndex * 12 : -activeIndex * 12) : defendX + (side === 0 ? activeIndex * 10 : -activeIndex * 10);
      let y = lanes[activeIndex] || (42 + activeIndex * 24);

      if (ev?.event_type === "shot") {
        const shotX = Number(ev.shot_pos_x);
        const shotY = Number(ev.shot_pos_y);
        if (side === Number(ev.attacking_team)) {
          const shooter = normalizeSlot(ev.attacker, teamBySide(side).players.length);
          const assistant = normalizeSlot(ev.assistant, teamBySide(side).players.length);
          if (idx === shooter && Number.isFinite(shotX) && Number.isFinite(shotY)) {
            x = shotX;
            y = shotY;
          } else if (idx === assistant) {
            x = (shotX + basketX) / 2;
            y = clamp(shotY + 28, 20, 172);
          }
        } else if (side === Number(ev.defending_team)) {
          const defender = normalizeSlot(ev.defender, teamBySide(side).players.length);
          if (idx === defender && Number.isFinite(shotX) && Number.isFinite(shotY)) {
            x = shotX + (side === 0 ? -16 : 16);
            y = clamp(shotY + 10, 16, 176);
          }
        }
      } else if (ev?.event_type === "rebound") {
        x = side === 0 ? 322 : 46;
        y = lanes[activeIndex] || 96;
      } else if (ev?.event_type === "interrupt") {
        x = attacking ? centerX : defendX;
        y = lanes[activeIndex] || 96;
      }

      return { x: clamp(x, 14, 354), y: clamp(y, 14, 178) };
    }

    function reboundCrashTarget(side, idx, active, shotEvent) {
      const activeList = [...active[side]];
      const activeIndex = Math.max(0, activeList.indexOf(idx));
      const shotSide = Number(shotEvent?.attacking_team ?? side);
      const rim = basketPoint(shotSide);
      const laneOffsets = [-26, -13, 0, 13, 26];
      const depthOffsets = [-16, -5, 8, 19, 29];
      const sideSign = shotSide === 0 ? -1 : 1;
      const attacking = side === shotSide;
      const playerSign = attacking ? 1 : -1;
      const x = rim.x + sideSign * (attacking ? 16 : 27) + laneOffsets[activeIndex] * 0.22;
      const y = rim.y + laneOffsets[activeIndex] + depthOffsets[activeIndex] * playerSign * 0.35;
      return { x: clamp(x, 16, 352), y: clamp(y, 22, 170) };
    }

    function offenseBuildTarget(side, idx, active, possessionSide) {
      const activeList = [...active[side]];
      const activeIndex = Math.max(0, activeList.indexOf(idx));
      const lanes = [96, 55, 136, 76, 116];
      const attacking = side === possessionSide;
      const direction = possessionSide === 0 ? 1 : -1;
      const baseX = possessionSide === 0 ? 246 : 122;
      const defenseX = possessionSide === 0 ? 300 : 68;

      if (attacking) {
        const spacing = [-36, -10, 18, 42, 66][activeIndex] ?? 0;
        return {
          x: clamp(baseX + direction * spacing, 24, 344),
          y: clamp(lanes[activeIndex] ?? 96, 22, 170)
        };
      }

      const defenseSpacing = [-22, -8, 7, 21, 34][activeIndex] ?? 0;
      return {
        x: clamp(defenseX - direction * defenseSpacing, 24, 344),
        y: clamp((lanes[activeIndex] ?? 96) + (activeIndex % 2 ? 5 : -5), 22, 170)
      };
    }

    function blendedPlayerTarget(side, idx, active, pair) {
      const prev = pair.prev;
      const next = pair.next || prev;
      if (prev?.event_type !== "shot") {
        const from = playerEventTarget(side, idx, active, prev);
        const to = playerEventTarget(side, idx, active, next);
        return mixPoint(from, to, pair.progress);
      }

      const shotSpot = playerEventTarget(side, idx, active, prev);
      const crashSpot = reboundCrashTarget(side, idx, active, prev);
      const nextSpot = playerEventTarget(side, idx, active, next);
      const p = pair.progress;

      if (p < 0.58) {
        return mixPoint(shotSpot, crashSpot, p / 0.58);
      }
      return mixPoint(crashSpot, nextSpot, (p - 0.58) / 0.42);
    }

    function reboundBuildPlayerTarget(side, idx, active, pair) {
      const prev = pair.prev;
      const next = pair.next || prev;
      const possessionSide = reboundPossessionSide(prev);
      if (possessionSide === null) return blendedPlayerTarget(side, idx, active, pair);

      const reboundSpot = playerEventTarget(side, idx, active, prev);
      const buildSpot = offenseBuildTarget(side, idx, active, possessionSide);
      const nextSpot = playerEventTarget(side, idx, active, next);
      const p = pair.progress;

      if (p < 0.24) {
        return mixPoint(reboundSpot, reboundCrashTarget(side, idx, active, { attacking_team: possessionSide }), p / 0.24);
      }
      if (p < 0.78) {
        return mixPoint(reboundCrashTarget(side, idx, active, { attacking_team: possessionSide }), buildSpot, (p - 0.24) / 0.54);
      }
      return mixPoint(buildSpot, nextSpot, (p - 0.78) / 0.22);
    }

    function playerEventTarget(side, idx, active, ev) {
      return targetForPlayer(side, idx, active, ev);
    }

    function playerEventPoint(side, rawSlot, active, ev) {
      const team = teamBySide(side);
      const idx = normalizeSlot(rawSlot, team.players.length);
      if (idx === null) return null;
      return playerEventTarget(side, idx, active, ev);
    }

    function nextBallReceiver(ev, active) {
      if (!ev) return null;
      if (ev.event_type === "rebound") {
        const side = String(ev.rebound_type) === "9317" ? Number(ev.attacking_team) : Number(ev.defending_team);
        return playerEventPoint(side, ev.attacker, active, ev);
      }
      if (ev.event_type === "interrupt") {
        const stolen = ["807", "808"].includes(String(ev.interrupt_type));
        const side = stolen ? Number(ev.defending_team) : Number(ev.attacking_team);
        const slot = stolen ? ev.defender : ev.attacker;
        return playerEventPoint(side, slot, active, ev);
      }
      if (ev.event_type === "free_throw") {
        return playerEventPoint(Number(ev.attacking_team), ev.attacker, active, ev);
      }
      if (ev.attacking_team !== undefined) {
        return playerEventPoint(Number(ev.attacking_team), ev.attacker, active, ev);
      }
      return null;
    }

    function ballPointForEvent(ev, active) {
      if (!ev) return { x: 184, y: 96 };
      if (ev.event_type === "shot") {
        const shotX = Number(ev.shot_pos_x);
        const shotY = Number(ev.shot_pos_y);
        if (Number.isFinite(shotX) && Number.isFinite(shotY)) return { x: shotX, y: shotY };
      }
      if (ev.event_type === "rebound") {
        const side = String(ev.rebound_type) === "9317" ? Number(ev.attacking_team) : Number(ev.defending_team);
        return playerEventPoint(side, ev.attacker, active, ev) || basketPoint(Number(ev.attacking_team));
      }
      if (ev.event_type === "interrupt") {
        const stolen = ["807", "808"].includes(String(ev.interrupt_type));
        const side = stolen ? Number(ev.defending_team) : Number(ev.attacking_team);
        const slot = stolen ? ev.defender : ev.attacker;
        return playerEventPoint(side, slot, active, ev) || { x: 184, y: 96 };
      }
      if (ev.attacking_team !== undefined) {
        return playerEventPoint(Number(ev.attacking_team), ev.attacker, active, ev) || { x: 184, y: 96 };
      }
      return { x: 184, y: 96 };
    }

    function shotArcPoint(from, rim, receiver, progress) {
      const p = clamp(progress, 0, 1);
      if (p < 0.62) {
        const t = easeInOut(p / 0.62);
        const lift = Math.sin(t * Math.PI) * 18;
        return { x: lerp(from.x, rim.x, t), y: lerp(from.y, rim.y, t) - lift };
      }
      const t = easeInOut((p - 0.62) / 0.38);
      return { x: lerp(rim.x, receiver.x, t), y: lerp(rim.y, receiver.y, t) };
    }

    function looseBallPoint(from, receiver, progress) {
      const p = easeInOut(progress);
      const wobble = Math.sin(p * Math.PI * 2) * 8;
      return {
        x: lerp(from.x, receiver.x, p),
        y: clamp(lerp(from.y, receiver.y, p) + wobble, 10, 182)
      };
    }

    function activePointByOrder(side, active, order, possessionSide) {
      const activeList = [...active[side]];
      if (!activeList.length) return offenseBuildTarget(side, 0, active, possessionSide);
      const idx = activeList[Math.abs(order) % activeList.length];
      return offenseBuildTarget(side, idx, active, possessionSide);
    }

    function passAroundPoint(from, nextPoint, active, possessionSide, progress) {
      const p = clamp(progress, 0, 1);
      const p1 = activePointByOrder(possessionSide, active, 1, possessionSide);
      const p2 = activePointByOrder(possessionSide, active, 3, possessionSide);
      const p3 = activePointByOrder(possessionSide, active, 0, possessionSide);

      if (p < 0.22) return mixPoint(from, p1, p / 0.22);
      if (p < 0.46) return mixPoint(p1, p2, (p - 0.22) / 0.24);
      if (p < 0.70) return mixPoint(p2, p3, (p - 0.46) / 0.24);
      return mixPoint(p3, nextPoint || p3, (p - 0.70) / 0.30);
    }

    function ballMotionTarget(pair, active) {
      const prev = pair.prev;
      const next = pair.next;
      const p = pair.progress;

      if (!prev) {
        const nextPoint = ballPointForEvent(next, active);
        return mixPoint({ x: 184, y: 96 }, nextPoint, p);
      }

      const prevPoint = ballPointForEvent(prev, active);
      const nextPoint = ballPointForEvent(next, active);

      if (prev.event_type === "shot") {
        const side = Number(prev.attacking_team);
        const rim = basketPoint(side);
        const receiver = nextBallReceiver(next, active) || rim;
        return shotArcPoint(prevPoint, rim, receiver, p);
      }

      if (prev.event_type === "rebound") {
        const possessionSide = reboundPossessionSide(prev);
        if (possessionSide !== null) {
          return passAroundPoint(prevPoint, nextPoint || activePointByOrder(possessionSide, active, 0, possessionSide), active, possessionSide, p);
        }
        return mixPoint(prevPoint, nextPoint || { x: 184, y: 96 }, Math.min(1, p * 0.85));
      }

      if (prev.event_type === "interrupt") {
        return looseBallPoint(prevPoint, nextPoint || { x: 184, y: 96 }, p);
      }

      return mixPoint(prevPoint, nextPoint || prevPoint, p);
    }

    function stabilizeVisiblePlayers(active) {
      [0, 1].forEach(side => {
        const visible = visualState.visible[side];
        active[side].forEach(idx => {
          if (visible.has(idx)) return;
          const teammates = [...visible]
            .filter(otherIdx => active[side].has(otherIdx) && otherIdx !== idx)
            .map(otherIdx => visualState.positions[side][otherIdx]);
          const source = teammates.length
            ? teammates[Math.floor(teammates.length / 2)]
            : { x: side === 0 ? 92 : 276, y: 96, targetX: side === 0 ? 92 : 276, targetY: 96 };
          const p = visualState.positions[side][idx];
          p.x = source.x;
          p.y = source.y;
          p.targetX = source.targetX;
          p.targetY = source.targetY;
          visible.add(idx);
        });
        [...visible].forEach(idx => {
          if (!active[side].has(idx)) visible.delete(idx);
        });
      });
    }

    function updateTargets(replay, clock) {
      const pair = eventPairAt(clock);
      stabilizeVisiblePlayers(replay.active);
      [0, 1].forEach(side => {
        replay.active[side].forEach(idx => {
          const target = pair.prev?.event_type === "rebound"
            ? reboundBuildPlayerTarget(side, idx, replay.active, pair)
            : blendedPlayerTarget(side, idx, replay.active, pair);
          visualState.positions[side][idx].targetX = target.x;
          visualState.positions[side][idx].targetY = target.y;
        });
      });

      const ball = ballMotionTarget(pair, replay.active);
      visualState.ball.targetX = clamp(ball.x, 4, 364);
      visualState.ball.targetY = clamp(ball.y, 4, 188);
    }

    function resizeCanvas() {
      const rect = canvas.getBoundingClientRect();
      const scale = window.devicePixelRatio || 1;
      canvas.width = Math.max(1, Math.round(rect.width * scale));
      canvas.height = Math.max(1, Math.round(rect.height * scale));
      ctx.setTransform(scale, 0, 0, scale, 0, 0);
    }

    function drawCourt() {
      const rect = canvas.getBoundingClientRect();
      const sx = rect.width / 368;
      const sy = rect.height / 192;
      ctx.clearRect(0, 0, rect.width, rect.height);
      ctx.save();
      ctx.scale(sx, sy);
      ctx.lineWidth = 1.5;
      ctx.strokeStyle = "rgba(255,255,255,0.55)";
      ctx.beginPath();
      ctx.moveTo(184, 0);
      ctx.lineTo(184, 192);
      ctx.stroke();

      [0, 1].forEach(side => {
        const active = latestReplay.active[side];
        active.forEach(idx => {
          const p = visualState.positions[side][idx];
          p.x += (p.targetX - p.x) * 0.055;
          p.y += (p.targetY - p.y) * 0.055;
          ctx.beginPath();
          ctx.fillStyle = side === 0 ? "#0d3b66" : "#9a031e";
          ctx.strokeStyle = "#fff";
          ctx.lineWidth = 2;
          ctx.arc(p.x, p.y, 7.5, 0, Math.PI * 2);
          ctx.fill();
          ctx.stroke();
          ctx.fillStyle = "#fff";
          ctx.font = "700 7px Segoe UI";
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillText(String(idx + 1), p.x, p.y + 0.3);
        });
      });

      visualState.ball.x += (visualState.ball.targetX - visualState.ball.x) * 0.22;
      visualState.ball.y += (visualState.ball.targetY - visualState.ball.y) * 0.22;
      ctx.beginPath();
      ctx.fillStyle = "#f97316";
      ctx.strokeStyle = "#7c2d12";
      ctx.lineWidth = 1.5;
      ctx.arc(visualState.ball.x, visualState.ball.y, 4.5, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
      ctx.restore();
    }

    function renderBox(replay) {
      const headers = "<tr><th>Player</th><th>MIN</th><th>PTS</th><th>FG</th><th>3PT</th><th>FT</th><th>REB</th><th>AST</th><th>TO</th><th>STL</th><th>BLK</th><th>PF</th><th>+/-</th></tr>";
      const currentVisualEvent = eventPairAt(currentTime).prev;
      const highlightedShot = currentVisualEvent?.event_type === "shot" ? currentVisualEvent : null;
      const renderTeamBox = (team, side) => {
        const rows = team.players.map((player, idx) => {
          const s = replay.stats.players[side][idx];
          const activeClass = replay.active[side].has(idx) ? " *" : "";
          const shotIdx = highlightedShot && Number(highlightedShot.attacking_team) === side
            ? normalizeSlot(highlightedShot.attacker, team.players.length)
            : null;
          const rowClass = shotIdx === idx
            ? (madeResults.has(String(highlightedShot.shot_result)) ? "shot-made" : "shot-missed")
            : "";
          return `<tr class="${rowClass}">
            <td>${player.name}${activeClass}</td>
            <td>${Math.floor(s.secs / 60)}</td>
            <td>${s.pts}</td>
            <td>${s.fgm}/${s.fga}</td>
            <td>${s.tpm}/${s.tpa}</td>
            <td>${s.ftm}/${s.fta}</td>
            <td>${s.tr}</td>
            <td>${s.ast}</td>
            <td>${s.to}</td>
            <td>${s.stl}</td>
            <td>${s.blk}</td>
            <td>${s.pf}</td>
            <td>${s.pm}</td>
          </tr>`;
        }).join("");
        const t = replay.stats.teams[side];
        const total = `<tr>
          <td><strong>Total</strong></td><td></td><td><strong>${t.pts}</strong></td>
          <td>${t.fgm}/${t.fga}</td><td>${t.tpm}/${t.tpa}</td><td>${t.ftm}/${t.fta}</td>
          <td>${t.tr}</td><td>${t.ast}</td><td>${t.to}</td><td>${t.stl}</td><td>${t.blk}</td><td>${t.pf}</td><td>${t.pm}</td>
        </tr>`;
        const chipClass = side === 0 ? "home-dot" : "away-dot";
        return `<section class="team-box"><h3><span class="team-color-chip ${chipClass}"></span>${team.name}</h3><table><thead>${headers}</thead><tbody>${rows}${total}</tbody></table></section>`;
      };
      document.getElementById("homeBoxScore").innerHTML = renderTeamBox(home, 0);
      document.getElementById("awayBoxScore").innerHTML = renderTeamBox(away, 1);
      document.getElementById("homeScore").textContent = replay.stats.teams[0].pts;
      document.getElementById("awayScore").textContent = replay.stats.teams[1].pts;
    }

    function renderEvent() {
      const ev = eventPairAt(currentTime).prev;
      if (!ev) {
        document.getElementById("eventMeta").textContent = "Opening tip";
        document.getElementById("eventComment").textContent = "Press play or jump to a game time.";
        return;
      }
      const period = clockRemaining(ev.gameclock);
      const side = ev.attacking_team !== undefined ? Number(ev.attacking_team) : Number(ev.team ?? 0);
      const team = teamBySide(side);
      document.getElementById("eventMeta").textContent = `Feed #${ev.feed_index} | ${periodLabel(period.period)} ${formatClock(ev.gameclock)} | ${team.name} | ${ev.event_type}`;
      document.getElementById("eventComment").textContent = formatComments(ev.comments);
    }

    function renderUi(force = false) {
      const whole = Math.floor(currentTime);
      if (!force && whole === lastRenderedSecond) return;
      lastRenderedSecond = whole;
      currentTime = clamp(currentTime, 0, maxClock);
      slider.value = String(Math.floor(currentTime));
      const clock = clockRemaining(currentTime);
      document.getElementById("periodLabel").textContent = periodLabel(clock.period);
      document.getElementById("clockLabel").textContent = formatClock(currentTime);
      document.getElementById("speedLabel").textContent = `${speed}x speed`;
      latestReplay = replayTo(currentTime);
      updateTargets(latestReplay, currentTime);
      renderBox(latestReplay);
      renderEvent();
    }

    function step(timestamp) {
      if (lastFrame === null) lastFrame = timestamp;
      const delta = Math.min(0.08, (timestamp - lastFrame) / 1000);
      lastFrame = timestamp;
      if (playing) {
        currentTime += delta * baseGameSecondsPerRealSecond * speed;
        if (currentTime >= maxClock) {
          currentTime = maxClock;
          playing = false;
          playBtn.textContent = "Play";
        }
        renderUi();
      }
      updateTargets(latestReplay, currentTime);
      drawCourt();
      requestAnimationFrame(step);
    }

    function seekTo(clock) {
      currentTime = clamp(clock, 0, maxClock);
      lastRenderedSecond = -1;
      renderUi(true);
    }

    function initJumpControls() {
      const maxPeriod = periodFromClock(maxClock);
      for (let p = 1; p <= maxPeriod; p += 1) {
        const opt = document.createElement("option");
        opt.value = String(p);
        opt.textContent = periodLabel(p);
        jumpQuarter.appendChild(opt);
      }
      jumpQuarter.addEventListener("change", () => {
        jumpMinute.max = String(Math.floor(periodLength(Number(jumpQuarter.value)) / 60));
      });
      jumpQuarter.dispatchEvent(new Event("change"));
    }

    playBtn.addEventListener("click", () => {
      playing = !playing;
      playBtn.textContent = playing ? "Pause" : "Play";
      lastFrame = null;
    });
    restartBtn.addEventListener("click", () => {
      playing = false;
      playBtn.textContent = "Play";
      visualState = createInitialVisualState();
      seekTo(0);
    });
    speedBtn.addEventListener("click", () => {
      speed = speed === 1 ? 2 : 1;
      speedBtn.textContent = speed === 1 ? "2x speed" : "1x speed";
      renderUi(true);
    });
    slider.addEventListener("input", () => seekTo(Number(slider.value)));
    document.getElementById("jumpBtn").addEventListener("click", () => {
      const period = Number(jumpQuarter.value);
      const len = periodLength(period);
      const mins = clamp(Number(jumpMinute.value) || 0, 0, Math.floor(len / 60));
      const secs = clamp(Number(jumpSecond.value) || 0, 0, 59);
      const remaining = clamp(mins * 60 + secs, 0, len);
      seekTo(periodStart(period) + (len - remaining));
    });

    window.addEventListener("resize", () => {
      resizeCanvas();
      drawCourt();
    });

    initJumpControls();
    resizeCanvas();
    renderUi(true);
    requestAnimationFrame(step);
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


def normalize_team_key(name: str) -> str:
    return " ".join(name.split()).casefold()


def normalize_player_key(name: str) -> str:
    cleaned = re.sub(r"[\W_]+", "", name.casefold())
    return cleaned or normalize_team_key(name)


def secs_to_minutes(total_seconds: int) -> int:
    return round(total_seconds / 60)


def normalize_slot(raw_slot: Any, players_len: int) -> int | None:
    try:
        n = int(raw_slot)
    except (TypeError, ValueError):
        return None
    if 1 <= n <= players_len:
        return n - 1
    return None


def normalize_player_index(raw_index: Any, players_len: int) -> int | None:
    try:
        n = int(raw_index)
    except (TypeError, ValueError):
        return None
    if 0 <= n < players_len:
        return n
    return None


def shot_stat() -> dict[str, int]:
    return {"m": 0, "a": 0}


def off_cell() -> dict[str, int]:
    return {"a": 0, "m": 0, "mi": 0, "b": 0}


def matchup_stats() -> dict[str, dict[str, int]]:
    return {
        "defended": shot_stat(),
        "openClose": shot_stat(),
        "openMid": shot_stat(),
        "openThree": shot_stat(),
        "openTotal": shot_stat(),
        "withPass": shot_stat(),
        "withoutPass": shot_stat(),
        "teamOn": shot_stat(),
        "teamOff": shot_stat(),
    }


def defense_stats() -> dict[str, dict[str, int]]:
    return {
        "teamDefOn": shot_stat(),
        "teamDefOff": shot_stat(),
        "defendedTotal": shot_stat(),
        "defendedClose": shot_stat(),
        "defendedMid": shot_stat(),
        "defendedThree": shot_stat(),
    }


def add_shot_stat(target: dict[str, int], made: bool) -> None:
    target["a"] += 1
    if made:
        target["m"] += 1


def add_off_stat(target: dict[str, int], result_code: Any) -> None:
    rc = str(result_code)
    target["a"] += 1
    if rc in {"1", "2", "5"}:
        target["m"] += 1
    elif rc == "3":
        target["b"] += 1
    else:
        target["mi"] += 1


def shot_range(shot_type: Any) -> str:
    code = str(shot_type)
    if code.startswith("10"):
        return "three"
    if code.startswith("20"):
        return "jump"
    return "paint"


def empty_form_context(
    *,
    error: str = "",
    username: str = "",
    password: str = "",
    matchid: str = "138595249",
    mode: str = "single",
    multi_matchids: list[str] | None = None,
    multi_source: str = "manual",
    national_country_id: str = "",
    national_team_kind: str = "nt",
    national_season: str = "",
    include_friendlies: bool = False,
) -> dict[str, Any]:
    vals = list(multi_matchids or [])
    while len(vals) < 2:
        vals.append("")
    return {
        "error": error,
        "username": username,
        "password": password,
        "matchid": matchid,
        "mode": mode,
        "multi_matchids": vals,
        "multi_source": multi_source,
        "national_country_id": national_country_id,
        "national_team_kind": national_team_kind,
        "national_season": national_season,
        "include_friendlies": include_friendlies,
        "national_options": load_local_national_options(),
    }


def parse_multi_matchids(form_values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in form_values:
        cleaned = value.strip()
        if not cleaned:
            continue
        if cleaned in seen:
            continue
        seen.add(cleaned)
        out.append(cleaned)
    return out


def default_local_seasons() -> list[dict[str, Any]]:
    current = 71
    return [
        {"id": str(season), "label": f"Season {season}", "current": season == current}
        for season in range(current, max(current - 10, 0), -1)
    ]


def load_local_national_options() -> dict[str, Any]:
    fallback = {"countries": [], "seasons": default_local_seasons()}
    if not LOCAL_NATIONAL_OPTIONS_PATH.exists():
        return fallback
    try:
        with LOCAL_NATIONAL_OPTIONS_PATH.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return fallback

    countries = normalize_country_options(payload.get("countries"))
    seasons = payload.get("seasons")
    return {
        "countries": countries or fallback["countries"],
        "seasons": seasons if isinstance(seasons, list) and seasons else fallback["seasons"],
    }


def normalize_country_options(countries: Any) -> list[dict[str, str]]:
    if not isinstance(countries, list):
        return []

    by_id: dict[str, dict[str, str]] = {}
    for country in countries:
        if not isinstance(country, dict):
            continue
        country_id = str(country.get("id", "")).strip()
        name = str(country.get("name", "")).strip()
        if country_id and name:
            by_id[country_id] = {"id": country_id, "name": name}

    return sorted(by_id.values(), key=lambda item: item["name"].casefold())


def merge_country_options(*country_lists: Any) -> list[dict[str, str]]:
    by_id: dict[str, dict[str, str]] = {}
    for countries in country_lists:
        for country in normalize_country_options(countries):
            by_id[country["id"]] = country
    return sorted(by_id.values(), key=lambda item: item["name"].casefold())


def save_local_national_options(payload: dict[str, Any]) -> None:
    try:
        LOCAL_NATIONAL_OPTIONS_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError:
        pass


def load_national_options(username: str, password: str) -> dict[str, Any]:
    api = BBApi(username, password)
    if not getattr(api, "logged_in", False):
        raise ValueError("BBAPI login failed. Check username/password.")
    local_payload = load_local_national_options()
    api_countries = api.countries()
    countries = merge_country_options(local_payload["countries"], api_countries)
    api_seasons = api.seasons()
    payload = {"countries": countries, "seasons": api_seasons or local_payload["seasons"]}
    if not payload["countries"]:
        if local_payload["countries"]:
            return local_payload
    if payload["countries"]:
        save_local_national_options(payload)
    return payload


def current_season_from_options(seasons: list[dict[str, Any]]) -> str:
    for season in seasons:
        if season.get("current"):
            return str(season["id"])
    if not seasons:
        return ""
    return str(max(seasons, key=lambda season: int(str(season["id"])))["id"])


def fetch_national_matchids(
    username: str,
    password: str,
    country_id: str,
    team_kind: str,
    season: str,
    include_friendlies: bool,
) -> list[str]:
    api = BBApi(username, password)
    if not getattr(api, "logged_in", False):
        raise ValueError("BBAPI login failed. Check username/password.")

    selected_season = season
    if not selected_season:
        selected_season = current_season_from_options(api.seasons())
    if not selected_season:
        raise ValueError("Could not detect the current BB season.")

    return api.national_team_schedule(
        country_id=country_id,
        team_kind=team_kind,
        season=selected_season,
        include_friendlies=include_friendlies,
    )


def game_team_entry(game_data: dict[str, Any], selected_team_key: str) -> tuple[int, dict[str, Any]] | None:
    home = game_data["teamHome"]
    away = game_data["teamAway"]
    if normalize_team_key(home["name"]) == selected_team_key:
        return (0, home)
    if normalize_team_key(away["name"]) == selected_team_key:
        return (1, away)
    return None


def canonical_player_names(players: list[dict[str, Any]], warnings: list[str], matchid: str) -> dict[int, tuple[str, str]]:
    base_counts: dict[str, int] = {}
    out: dict[int, tuple[str, str]] = {}
    for idx, player in enumerate(players):
        name = player["name"].strip()
        if not name or name == "Lucky Fan":
            continue
        base_key = normalize_player_key(name)
        base_counts[base_key] = base_counts.get(base_key, 0) + 1
        if base_counts[base_key] > 1:
            label = f"{name} ({base_counts[base_key]})"
            warnings.append(
                f"Match {matchid}: duplicate player name '{name}' detected on the selected team, so separate rows were kept."
            )
            out[idx] = (f"{base_key}__dup{base_counts[base_key]}", label)
            continue
        out[idx] = (base_key, name)
    return out


def format_score(game_data: dict[str, Any]) -> str:
    home = game_data["teamHome"]
    away = game_data["teamAway"]
    return f'{home["stats"]["total"]["pts"]} - {away["stats"]["total"]["pts"]}'


def build_team_candidates(games: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, dict[str, Any]] = {}
    for game_data in games:
        for team in (game_data["teamHome"], game_data["teamAway"]):
            key = normalize_team_key(team["name"])
            entry = counts.setdefault(key, {"key": key, "name": team["name"], "count": 0})
            entry["count"] += 1
    if not counts:
        return []
    top_count = max(entry["count"] for entry in counts.values())
    return [entry for entry in counts.values() if entry["count"] == top_count]


def load_game_report(matchid: str, username: str, password: str) -> dict[str, Any]:
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
    report = serialize_game(game)
    report["matchid"] = str(matchid)
    return report


def generate_report(matchid: str, username: str, password: str) -> dict[str, Any]:
    return load_game_report(matchid, username, password)


def aggregate_multi_match_report(
    matchids: list[str],
    username: str,
    password: str,
    selected_team_key: str | None = None,
) -> tuple[str, dict[str, Any] | list[dict[str, Any]]]:
    loaded_games: list[dict[str, Any]] = []
    initial_rows: list[dict[str, str]] = []
    warnings: list[str] = []

    for matchid in matchids:
        if not matchid.isdigit():
            msg = "Match ID must be numeric."
            warnings.append(f"Match {matchid}: {msg}")
            initial_rows.append(
                {
                    "matchid": matchid,
                    "home_team": "-",
                    "away_team": "-",
                    "score": "-",
                    "detected_side": "-",
                    "result": "-",
                    "status": msg,
                }
            )
            continue
        try:
            game_data = load_game_report(matchid, username, password)
        except Exception as exc:
            msg = f"Skipped: {exc}"
            warnings.append(f"Match {matchid}: {exc}")
            initial_rows.append(
                {
                    "matchid": matchid,
                    "home_team": "-",
                    "away_team": "-",
                    "score": "-",
                    "detected_side": "-",
                    "result": "-",
                    "status": msg,
                }
            )
            continue

        loaded_games.append(game_data)

    if not loaded_games:
        return (
            "error",
            {
                "message": "No valid matches could be loaded.",
                "rows": initial_rows,
                "warnings": warnings,
            },
        )

    candidates = build_team_candidates(loaded_games)
    if not candidates:
        return (
            "error",
            {
                "message": "Could not detect a common team across the submitted matches.",
                "rows": initial_rows,
                "warnings": warnings,
            },
        )

    if not selected_team_key:
        if len(candidates) > 1:
            return ("choose_team", candidates)
        selected_team_key = candidates[0]["key"]

    player_summary_map: dict[str, dict[str, Any]] = {}
    matchup_map: dict[str, dict[str, Any]] = {}
    defense_map: dict[str, dict[str, Any]] = {}
    offense_map: dict[str, dict[str, Any]] = {}
    defended_shot_events: list[dict[str, str]] = []
    match_rows = list(initial_rows)
    team_name = ""
    used_matches = 0
    wins = 0
    losses = 0
    shot_type_codes: set[str] = set()
    defender_names: set[str] = set()
    shot_result_codes: set[str] = set()

    stat_fields = [
        "pts",
        "fgm",
        "fga",
        "tpm",
        "tpa",
        "ftm",
        "fta",
        "+/-",
        "or",
        "dr",
        "tr",
        "ast",
        "to",
        "stl",
        "blk",
        "pf",
    ]

    for game_data in loaded_games:
        matchid = game_data["matchid"]
        found = game_team_entry(game_data, selected_team_key)
        if found is None:
            msg = "Skipped: selected team not present in this match."
            warnings.append(f"Match {matchid}: selected team not present.")
            match_rows.append(
                {
                    "matchid": matchid,
                    "home_team": game_data["teamHome"]["name"],
                    "away_team": game_data["teamAway"]["name"],
                    "score": format_score(game_data),
                    "detected_side": "-",
                    "result": "-",
                    "status": msg,
                }
            )
            continue

        side, team_obj = found
        opp_obj = game_data["teamAway"] if side == 0 else game_data["teamHome"]
        team_name = team_obj["name"]
        used_matches += 1

        team_pts = team_obj["stats"]["total"]["pts"]
        opp_pts = opp_obj["stats"]["total"]["pts"]
        result = "W" if team_pts > opp_pts else "L"
        if result == "W":
            wins += 1
        else:
            losses += 1

        match_rows.append(
            {
                "matchid": matchid,
                "home_team": game_data["teamHome"]["name"],
                "away_team": game_data["teamAway"]["name"],
                "score": format_score(game_data),
                "detected_side": "Home" if side == 0 else "Away",
                "result": result,
                "status": "Used",
            }
        )

        slot_map = canonical_player_names(team_obj["players"], warnings, matchid)

        for idx, player in enumerate(team_obj["players"]):
            if idx not in slot_map:
                continue
            player_key, player_label = slot_map[idx]
            totals = player["stats"]["total"]
            entry = player_summary_map.setdefault(
                player_key,
                {
                    "name": player_label,
                    "gp": 0,
                    "secs_pg": 0,
                    "secs_sg": 0,
                    "secs_sf": 0,
                    "secs_pf": 0,
                    "secs_c": 0,
                    "pts": 0,
                    "fgm": 0,
                    "fga": 0,
                    "tpm": 0,
                    "tpa": 0,
                    "ftm": 0,
                    "fta": 0,
                    "or": 0,
                    "dr": 0,
                    "tr": 0,
                    "ast": 0,
                    "to": 0,
                    "stl": 0,
                    "blk": 0,
                    "pf": 0,
                    "pm": 0,
                },
            )
            entry["gp"] += 1
            entry["secs_pg"] += totals["secs_pg"]
            entry["secs_sg"] += totals["secs_sg"]
            entry["secs_sf"] += totals["secs_sf"]
            entry["secs_pf"] += totals["secs_pf"]
            entry["secs_c"] += totals["secs_c"]
            for field in stat_fields:
                target = "pm" if field == "+/-" else field
                entry[target] += totals[field]

            matchup_map.setdefault(player_key, {"name": player_label, **matchup_stats()})
            defense_map.setdefault(player_key, {"name": player_label, **defense_stats()})
            offense_map.setdefault(player_key, {"name": player_label, "counts": {}})

        active_keys = {
            slot_map[idx][0]
            for idx, player in enumerate(team_obj["players"])
            if idx in slot_map and player.get("starter")
        }

        for ev in game_data["events"]:
            if ev["event_type"] == "shot":
                made = str(ev["shot_result"]) in {"1", "2", "5"}
                shot_type = str(ev["shot_type"])
                shot_result = str(ev["shot_result"])
                shot_type_codes.add(shot_type)
                shot_result_codes.add(shot_result)

                if int(ev["attacking_team"]) == side:
                    for player_key in slot_map.values():
                        add_shot_stat(
                            matchup_map[player_key[0]]["teamOn" if player_key[0] in active_keys else "teamOff"],
                            made,
                        )

                    shooter_idx = normalize_slot(ev["attacker"], len(team_obj["players"]))
                    if shooter_idx is not None and shooter_idx in slot_map:
                        shooter_key, _ = slot_map[shooter_idx]
                        shooter_stats = matchup_map[shooter_key]

                        defender_idx = normalize_slot(ev["defender"], len(opp_obj["players"]))
                        if defender_idx is not None:
                            add_shot_stat(shooter_stats["defended"], made)
                        else:
                            range_key = shot_range(shot_type)
                            if range_key == "paint":
                                add_shot_stat(shooter_stats["openClose"], made)
                            elif range_key == "jump":
                                add_shot_stat(shooter_stats["openMid"], made)
                            else:
                                add_shot_stat(shooter_stats["openThree"], made)
                            add_shot_stat(shooter_stats["openTotal"], made)

                        if normalize_slot(ev["assistant"], len(team_obj["players"])) is not None:
                            add_shot_stat(shooter_stats["withPass"], made)
                        else:
                            add_shot_stat(shooter_stats["withoutPass"], made)

                        counts = offense_map[shooter_key]["counts"].setdefault(shot_type, off_cell())
                        add_off_stat(counts, shot_result)

                if int(ev["defending_team"]) == side:
                    for player_key in slot_map.values():
                        add_shot_stat(
                            defense_map[player_key[0]]["teamDefOn" if player_key[0] in active_keys else "teamDefOff"],
                            made,
                        )

                    defender_idx = normalize_slot(ev["defender"], len(team_obj["players"]))
                    if defender_idx is not None and defender_idx in slot_map:
                        defender_key, defender_label = slot_map[defender_idx]
                        defender_names.add(defender_label)
                        defender_stats = defense_map[defender_key]
                        add_shot_stat(defender_stats["defendedTotal"], made)
                        range_key = shot_range(shot_type)
                        if range_key == "paint":
                            add_shot_stat(defender_stats["defendedClose"], made)
                        elif range_key == "jump":
                            add_shot_stat(defender_stats["defendedMid"], made)
                        else:
                            add_shot_stat(defender_stats["defendedThree"], made)

                        shooter_idx = normalize_slot(ev["attacker"], len(opp_obj["players"]))
                        shooter_name = (
                            opp_obj["players"][shooter_idx]["name"]
                            if shooter_idx is not None and shooter_idx < len(opp_obj["players"])
                            else f'#{ev["attacker"]}'
                        )
                        defended_shot_events.append(
                            {
                                "matchid": matchid,
                                "defender": defender_label,
                                "shooter": shooter_name,
                                "opponent": opp_obj["name"],
                                "shot_type": shot_type,
                                "shot_result": shot_result,
                                "comment": " ".join(ev.get("comments", [])) or "(no commentary)",
                            }
                        )

                continue

            if ev["event_type"] == "sub" and int(ev["team"]) == side:
                if str(ev["sub_type"]) == "9520":
                    continue
                player_in_idx = normalize_player_index(ev["player_in"], len(team_obj["players"]))
                player_out_idx = normalize_player_index(ev["player_out"], len(team_obj["players"]))
                if player_out_idx is not None and player_out_idx in slot_map:
                    active_keys.discard(slot_map[player_out_idx][0])
                if player_in_idx is not None and player_in_idx in slot_map:
                    active_keys.add(slot_map[player_in_idx][0])

    if used_matches == 0:
        return (
            "error",
            {
                "message": "No matches included the selected team after validation.",
                "rows": match_rows,
                "warnings": warnings,
            },
        )

    player_summary = []
    for entry in player_summary_map.values():
        total_secs = (
            entry["secs_pg"]
            + entry["secs_sg"]
            + entry["secs_sf"]
            + entry["secs_pf"]
            + entry["secs_c"]
        )
        player_summary.append(
            {
                "name": entry["name"],
                "gp": entry["gp"],
                "mins": secs_to_minutes(total_secs),
                "pts": entry["pts"],
                "fgm": entry["fgm"],
                "fga": entry["fga"],
                "tpm": entry["tpm"],
                "tpa": entry["tpa"],
                "ftm": entry["ftm"],
                "fta": entry["fta"],
                "tr": entry["tr"],
                "ast": entry["ast"],
                "to": entry["to"],
                "stl": entry["stl"],
                "blk": entry["blk"],
                "pf": entry["pf"],
                "pm": entry["pm"],
            }
        )

    offense_players = []
    for player_key, item in offense_map.items():
        counts = {code: item["counts"].get(code, off_cell()) for code in sorted(shot_type_codes, key=int)}
        total = off_cell()
        for cell in counts.values():
            total["a"] += cell["a"]
            total["m"] += cell["m"]
            total["mi"] += cell["mi"]
            total["b"] += cell["b"]
        offense_players.append({"name": item["name"], "counts": counts, "total": total})

    matchup_rows = []
    for item in matchup_map.values():
        matchup_rows.append(
            {
                "name": item["name"],
                "defended": item["defended"],
                "openClose": item["openClose"],
                "openMid": item["openMid"],
                "openThree": item["openThree"],
                "openTotal": item["openTotal"],
                "teamOn": item["teamOn"],
                "teamOff": item["teamOff"],
                "withPass": item["withPass"],
                "withoutPass": item["withoutPass"],
                "total_attempts": item["defended"]["a"] + item["openTotal"]["a"] + item["withPass"]["a"] + item["withoutPass"]["a"],
            }
        )

    defense_rows = []
    for item in defense_map.values():
        defense_rows.append(
            {
                "name": item["name"],
                "teamDefOn": item["teamDefOn"],
                "teamDefOff": item["teamDefOff"],
                "defendedTotal": item["defendedTotal"],
                "defendedClose": item["defendedClose"],
                "defendedMid": item["defendedMid"],
                "defendedThree": item["defendedThree"],
                "total_attempts": item["defendedTotal"]["a"],
            }
        )

    return (
        "ok",
        {
            "team_name": team_name,
            "submitted_matches": len(matchids),
            "used_matches": used_matches,
            "skipped_matches": len(match_rows) - used_matches,
            "wins": wins,
            "losses": losses,
            "warnings": warnings,
            "matches": match_rows,
            "player_summary": player_summary,
            "matchup": matchup_rows,
            "defense": defense_rows,
            "offense": {
                "shot_types": sorted(shot_type_codes, key=int),
                "players": offense_players,
            },
            "defended_shots": {
                "players": sorted(defender_names),
                "shot_types": sorted(shot_type_codes, key=int),
                "results": sorted(shot_result_codes, key=int),
                "events": defended_shot_events,
            },
        },
    )


def get_court_image_data_url() -> str:
    court_path = Path(__file__).with_name("court.png")
    if not court_path.exists():
        return ""
    data = base64.b64encode(court_path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{data}"


@app.get("/")
def form() -> str:
    return render_template_string(FORM_HTML, **empty_form_context())


@app.post("/national-options")
def national_options() -> tuple[Any, int] | Any:
    payload = request.get_json(silent=True) or {}
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", "")).strip()
    if not username or not password:
        return jsonify({"error": "Username and password are required."}), 400
    try:
        return jsonify(load_national_options(username, password))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


def form_error_response(
    message: str,
    status_code: int,
    *,
    username: str,
    password: str,
    matchid: str,
    mode: str,
    multi_matchids: list[str],
    multi_source: str,
    national_country_id: str,
    national_team_kind: str,
    national_season: str,
    include_friendlies: bool,
) -> tuple[str, int]:
    return (
        render_template_string(
            FORM_HTML,
            **empty_form_context(
                error=message,
                username=username,
                password=password,
                matchid=matchid,
                mode=mode,
                multi_matchids=multi_matchids,
                multi_source=multi_source,
                national_country_id=national_country_id,
                national_team_kind=national_team_kind,
                national_season=national_season,
                include_friendlies=include_friendlies,
            ),
        ),
        status_code,
    )


@app.post("/report")
def report() -> tuple[str, int] | str:
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()
    mode = request.form.get("mode", "single").strip() or "single"
    matchid = request.form.get("matchid", "").strip()
    multi_matchids = parse_multi_matchids(request.form.getlist("matchids"))
    selected_team_key = request.form.get("selected_team_key", "").strip() or None
    multi_source = request.form.get("multi_source", "manual").strip() or "manual"
    national_country_id = request.form.get("national_country_id", "").strip()
    national_team_kind = request.form.get("national_team_kind", "nt").strip() or "nt"
    national_season = request.form.get("national_season", "").strip()
    include_friendlies = request.form.get("include_friendlies") == "1"

    def form_error(message: str, status_code: int, *, keep_password: bool = True) -> tuple[str, int]:
        return form_error_response(
            message,
            status_code,
            username=username,
            password=password if keep_password else "",
            matchid=matchid,
            mode=mode,
            multi_matchids=multi_matchids,
            multi_source=multi_source,
            national_country_id=national_country_id,
            national_team_kind=national_team_kind,
            national_season=national_season,
            include_friendlies=include_friendlies,
        )

    if not username or not password:
        return form_error("Username and password are required.", 400)

    if mode == "multi":
        if multi_source == "national":
            if not national_country_id:
                return form_error("Choose a national team before generating the report.", 400)
            try:
                multi_matchids = fetch_national_matchids(
                    username=username,
                    password=password,
                    country_id=national_country_id,
                    team_kind=national_team_kind,
                    season=national_season,
                    include_friendlies=include_friendlies,
                )
            except Exception as exc:
                return form_error(f"Could not load national team schedule: {exc}", 400, keep_password=False)

        if not multi_matchids:
            if multi_source == "national":
                return form_error("No matches were found for that national team schedule.", 400)
            return form_error("Enter at least one match ID for multi-match mode.", 400)

        status, payload = aggregate_multi_match_report(
            multi_matchids,
            username,
            password,
            selected_team_key=selected_team_key,
        )

        if status == "choose_team":
            return render_template_string(
                TEAM_CHOICE_HTML,
                username=username,
                password=password,
                matchids=multi_matchids,
                candidates=payload,
            )

        if status == "error":
            message = payload["message"]
            extra_warnings = payload.get("warnings", [])
            if extra_warnings:
                message = f'{message} {" | ".join(extra_warnings)}'
            return form_error(message, 400, keep_password=False)

        return render_template_string(
            MULTI_REPORT_HTML,
            report_json=payload,
            username=username,
        )

    if not matchid:
        return form_error("Match ID is required.", 400)

    if not matchid.isdigit():
        return form_error("Match ID must be numeric.", 400)

    try:
        report_json = generate_report(matchid, username, password)
    except Exception as exc:
        return form_error(f"Failed to generate report: {exc}", 500, keep_password=False)

    if mode == "animation":
        return render_template_string(
            ANIMATION_REPORT_HTML,
            report_json=report_json,
            matchid=matchid,
            username=username,
            court_image_url=get_court_image_data_url(),
        )

    return render_template_string(
        REPORT_HTML,
        report_json=report_json,
        matchid=matchid,
        username=username,
        court_image_url=get_court_image_data_url(),
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
