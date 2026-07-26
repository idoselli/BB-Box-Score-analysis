#!/usr/bin/env python3

from __future__ import annotations

from argparse import Namespace
import base64
import contextlib
from datetime import datetime
import hmac
import io
import json
import os
from pathlib import Path
import re
from typing import Any
import xml.etree.ElementTree as xml

from flask import Flask, jsonify, render_template_string, request

from bbapi import BBApi
from bb_site import BBSiteClient
from coachparrot_model import SKILLS
from game import Game
from main import get_xml_text, parse_xml
from minutes_analyzer import minutes_bp
from u21_training import PlayerMetadata, estimate_player, target_seasons_for_player

app = Flask(__name__)
app.register_blueprint(minutes_bp)

LOCAL_NATIONAL_OPTIONS_PATH = Path(__file__).with_name("national_options.json")
DEFAULT_CURRENT_SEASON = 72
VERCEL_ANALYTICS_HTML = """<script>
  window.va = window.va || function () { (window.vaq = window.vaq || []).push(arguments); };
</script>
<script defer src="/_vercel/insights/script.js"></script>"""


@app.after_request
def add_vercel_analytics(response):
    if response.status_code != 200 or response.direct_passthrough:
        return response
    if not response.content_type.startswith("text/html"):
        return response

    html = response.get_data(as_text=True)
    if "/_vercel/insights/script.js" in html:
        return response

    analytics_html = f"\n{VERCEL_ANALYTICS_HTML}\n"
    if re.search(r"</body\s*>", html, flags=re.IGNORECASE):
        html = re.sub(r"</body\s*>", f"{analytics_html}</body>", html, count=1, flags=re.IGNORECASE)
    elif re.search(r"</html\s*>", html, flags=re.IGNORECASE):
        html = re.sub(r"</html\s*>", f"{analytics_html}</html>", html, count=1, flags=re.IGNORECASE)
    else:
        html = f"{html}{analytics_html}"

    response.set_data(html)
    return response


FORM_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Box Score Analysis Web Tool</title>
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
      grid-template-columns: repeat(auto-fit, minmax(145px, 1fr));
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
    .beta-label {
      display: block;
      margin-top: 2px;
      font-size: 10px;
      font-weight: 800;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      opacity: 0.75;
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
    .u21-gate {
      display: grid;
      gap: 10px;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfdff;
    }
    .u21-gate-row {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 10px;
      align-items: end;
    }
    .u21-locked-fields {
      display: grid;
      gap: 12px;
      transition: filter 160ms ease, opacity 160ms ease;
    }
    .u21-locked-fields.locked {
      filter: blur(3px);
      opacity: 0.45;
      pointer-events: none;
      user-select: none;
    }
    .u21-unlock-status {
      min-height: 16px;
    }
  </style>
</head>
<body>
  <main class="wrap">
    <section class="card">
      <h1>Box Score Analysis</h1>
      <p>Enter your BBAPI credentials and a match ID to generate a full report.</p>
      {% if error %}
      <div class="err">{{ error }}</div>
      {% endif %}
      <div class="small" style="margin-bottom:12px">
        Minutes analyzers:
        <a href="/u21-minutes">U21 Minutes</a>
        ·
        <a href="/nt-minutes">NT Minutes</a>
        ·
        <a href="/player-minutes">Player Analyzer</a>
      </div>
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
          <button type="button" class="mode-btn" data-mode="animation">Animation<span class="beta-label">Beta</span></button>
          <button type="button" class="mode-btn" data-mode="u21_training">U21 squad analysis<span class="beta-label">Beta</span></button>
        </div>

        <section id="singlePanel" class="mode-panel">
          <div class="small" id="singleModeHint">Generate a full report for one match.</div>
          <label>Match ID
            <input name="matchid" value="{{ matchid }}" />
          </label>
        </section>

        <section id="multiPanel" class="mode-panel">
          <div class="small">Add match IDs manually, pull them from a national team schedule, or load a team schedule.</div>
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
            <label class="choice-row">
              <input type="radio" name="multi_source_choice" value="team" />
              Team schedule
            </label>
            <div id="teamSchedulePanel" class="source-panel">
              <div class="auto-grid">
                <label>Team ID
                  <input name="team_schedule_team_id" value="{{ team_schedule_team_id }}" />
                </label>
                <label>Season
                  <select name="team_schedule_season" id="teamScheduleSeasonSelect" data-selected="{{ team_schedule_season }}">
                    <option value="">Current season</option>
                  </select>
                </label>
                <label>Games
                  <select name="team_schedule_limit" id="teamScheduleLimit">
                    <option value="5"{% if team_schedule_limit == "5" %} selected{% endif %}>Last 5</option>
                    <option value="10"{% if team_schedule_limit == "10" %} selected{% endif %}>Last 10</option>
                    <option value="15"{% if team_schedule_limit == "15" %} selected{% endif %}>Last 15</option>
                    <option value="20"{% if team_schedule_limit == "20" %} selected{% endif %}>Last 20</option>
                    <option value="all"{% if team_schedule_limit == "all" %} selected{% endif %}>All</option>
                  </select>
                </label>
              </div>
              <div class="auto-grid">
                {% for option in team_schedule_type_options %}
                <label class="inline-check">
                  <input type="checkbox" name="team_schedule_types" value="{{ option.value }}"{% if option.value in team_schedule_types %} checked{% endif %} />
                  {{ option.label }}
                </label>
                {% endfor %}
              </div>
              <div class="hint">Only completed games from the selected season are used; if fewer games exist, fewer will be loaded.</div>
            </div>
          </div>
        </section>

        <section id="u21TrainingPanel" class="mode-panel">
          <div class="small">Estimate a current U21 roster from player club-game minutes and CoachParrot formulas.</div>
          <div class="u21-gate">
            <div class="u21-gate-row">
              <label>Analyzer Password
                <input id="u21AnalyzerPassword" type="password" autocomplete="off" />
              </label>
              <button type="button" id="unlockU21AnalyzerBtn" class="ghost">Unlock</button>
            </div>
            <div class="hint u21-unlock-status" id="u21UnlockStatus">Enter the analyzer password to unlock these fields.</div>
          </div>
          <div id="u21LockedFields" class="u21-locked-fields locked" aria-hidden="true">
            <label>BB Site Password
              <input name="bb_site_password" type="password" autocomplete="current-password" value="{{ bb_site_password }}" disabled />
            </label>
            <button type="button" id="loadEstimatorOptionsBtn" class="ghost" disabled>Load Teams And Seasons</button>
            <div class="auto-grid">
              <label>Country U21 Team
                <select name="estimator_country_id" id="estimatorCountrySelect" data-selected="{{ estimator_country_id }}" disabled>
                  <option value="">Select a team</option>
                </select>
              </label>
              <label>Current Season
                <select name="estimator_season" id="estimatorSeasonSelect" data-selected="{{ estimator_season }}" disabled>
                  <option value="">Current season</option>
                </select>
              </label>
              <label>NT Strength
                <select name="estimator_nt_strength" id="estimatorNtStrengthSelect" disabled>
                  <option value="weak"{% if estimator_nt_strength == "weak" %} selected{% endif %}>Weak NT</option>
                  <option value="strong"{% if estimator_nt_strength == "strong" %} selected{% endif %}>Strong NT</option>
                </select>
              </label>
            </div>
            <div class="hint" id="estimatorOptionsStatus">Use the button after entering BBAPI credentials.</div>
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
    const u21TrainingPanel = document.getElementById("u21TrainingPanel");
    const singleModeHint = document.getElementById("singleModeHint");
    const modeButtons = [...document.querySelectorAll(".mode-btn")];
    const matchesList = document.getElementById("matchesList");
    const addMatchBtn = document.getElementById("addMatchBtn");
    const rowTemplate = document.getElementById("matchRowTemplate");
    const multiSourceInput = document.getElementById("multiSourceInput");
    const sourceChoices = [...document.querySelectorAll("input[name='multi_source_choice']")];
    const manualMatchPanel = document.getElementById("manualMatchPanel");
    const nationalMatchPanel = document.getElementById("nationalMatchPanel");
    const teamSchedulePanel = document.getElementById("teamSchedulePanel");
    const loadNationalOptionsBtn = document.getElementById("loadNationalOptionsBtn");
    const nationalCountrySelect = document.getElementById("nationalCountrySelect");
    const nationalSeasonSelect = document.getElementById("nationalSeasonSelect");
    const teamScheduleSeasonSelect = document.getElementById("teamScheduleSeasonSelect");
    const nationalOptionsStatus = document.getElementById("nationalOptionsStatus");
    const loadEstimatorOptionsBtn = document.getElementById("loadEstimatorOptionsBtn");
    const estimatorCountrySelect = document.getElementById("estimatorCountrySelect");
    const estimatorSeasonSelect = document.getElementById("estimatorSeasonSelect");
    const estimatorOptionsStatus = document.getElementById("estimatorOptionsStatus");
    const u21AnalyzerPassword = document.getElementById("u21AnalyzerPassword");
    const unlockU21AnalyzerBtn = document.getElementById("unlockU21AnalyzerBtn");
    const u21UnlockStatus = document.getElementById("u21UnlockStatus");
    const u21LockedFields = document.getElementById("u21LockedFields");
    const localNationalOptions = {{ national_options | tojson }};

    function applyMode(mode) {
      modeInput.value = mode;
      singlePanel.classList.toggle("active", mode === "single" || mode === "animation");
      multiPanel.classList.toggle("active", mode === "multi");
      u21TrainingPanel.classList.toggle("active", mode === "u21_training");
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

    function setU21Locked(locked) {
      u21LockedFields?.classList.toggle("locked", locked);
      u21LockedFields?.setAttribute("aria-hidden", locked ? "true" : "false");
      u21LockedFields?.querySelectorAll("input, select, button").forEach(control => {
        control.disabled = locked;
      });
    }

    async function unlockU21Analyzer() {
      const password = u21AnalyzerPassword.value;
      if (!password) {
        u21UnlockStatus.textContent = "Enter the analyzer password first.";
        return;
      }
      u21UnlockStatus.textContent = "Checking password...";
      unlockU21AnalyzerBtn.disabled = true;
      try {
        const response = await fetch("/u21-analyzer-unlock", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ password }),
        });
        const payload = await response.json();
        if (!response.ok || !payload.ok) {
          throw new Error(payload.error || "Could not unlock analyzer.");
        }
        setU21Locked(false);
        u21AnalyzerPassword.value = "";
        u21UnlockStatus.textContent = "Analyzer fields unlocked.";
      } catch (err) {
        setU21Locked(true);
        u21UnlockStatus.textContent = err.message;
      } finally {
        unlockU21AnalyzerBtn.disabled = false;
      }
    }

    unlockU21AnalyzerBtn?.addEventListener("click", unlockU21Analyzer);
    u21AnalyzerPassword?.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") {
        ev.preventDefault();
        unlockU21Analyzer();
      }
    });

    function applyMultiSource(source) {
      multiSourceInput.value = source;
      sourceChoices.forEach(choice => {
        choice.checked = choice.value === source;
      });
      manualMatchPanel.classList.toggle("active", source === "manual");
      nationalMatchPanel.classList.toggle("active", source === "national");
      teamSchedulePanel.classList.toggle("active", source === "team");
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
      if (!select) return;
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
      fillSelect(teamScheduleSeasonSelect, payload.seasons || [], teamScheduleSeasonSelect.dataset.selected, "Current season");
      fillSelect(estimatorCountrySelect, payload.countries || [], estimatorCountrySelect.dataset.selected, "Select a team");
      fillSelect(estimatorSeasonSelect, payload.seasons || [], estimatorSeasonSelect.dataset.selected, "Current season");
      nationalOptionsStatus.textContent = statusText;
      estimatorOptionsStatus.textContent = statusText;
    }

    async function fetchNationalOptions(statusEl, button) {
      const username = document.querySelector("input[name='username']").value.trim();
      const password = document.querySelector("input[name='password']").value.trim();
      if (!username || !password) {
        statusEl.textContent = "Enter username and password first.";
        return;
      }
      statusEl.textContent = "Loading teams and seasons...";
      button.disabled = true;
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
        statusEl.textContent = err.message;
      } finally {
        button.disabled = false;
      }
    }

    loadNationalOptionsBtn?.addEventListener("click", () => fetchNationalOptions(nationalOptionsStatus, loadNationalOptionsBtn));
    loadEstimatorOptionsBtn?.addEventListener("click", () => fetchNationalOptions(estimatorOptionsStatus, loadEstimatorOptionsBtn));

    updateRemoveButtons();
    loadOptionsIntoForm(localNationalOptions, "Loaded from local file. Use the button to refresh.");
    applyMultiSource({{ multi_source | tojson }});
    setU21Locked(true);
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
          <input type="hidden" name="multi_source" value="{{ multi_source }}" />
          <input type="hidden" name="national_country_id" value="{{ national_country_id }}" />
          <input type="hidden" name="national_team_kind" value="{{ national_team_kind }}" />
          <input type="hidden" name="national_season" value="{{ national_season }}" />
          <input type="hidden" name="team_schedule_team_id" value="{{ team_schedule_team_id }}" />
          <input type="hidden" name="team_schedule_season" value="{{ team_schedule_season }}" />
          <input type="hidden" name="team_schedule_limit" value="{{ team_schedule_limit }}" />
          {% for value in team_schedule_types %}
          <input type="hidden" name="team_schedule_types" value="{{ value }}" />
          {% endfor %}
          {% if include_friendlies %}
          <input type="hidden" name="include_friendlies" value="1" />
          {% endif %}
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
  <script>
  </script>
</body>
</html>
"""


U21_TRAINING_REPORT_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>U21 squad analysis</title>
  <style>
    :root {
      --bg: #f6f8fb;
      --panel: #fff;
      --line: #d9e1ea;
      --ink: #1f2933;
      --muted: #607285;
      --accent: #0d47a1;
      --warn-bg: #fff7ed;
      --warn-line: #fdba74;
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
      max-width: 1380px;
      margin: 0 auto;
      padding: 24px;
    }
    .topbar {
      margin-bottom: 12px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
    }
    a { color: var(--accent); font-weight: 700; text-decoration: none; }
    .hero, .card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
      box-shadow: var(--shadow);
    }
    .hero {
      padding: 20px;
      margin-bottom: 16px;
    }
    h1 { margin: 0 0 8px; font-size: 28px; }
    h2 { margin: 0; padding: 12px 14px; border-bottom: 1px solid var(--line); font-size: 15px; }
    p { margin: 0; color: var(--muted); }
    .summary-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
      gap: 10px;
      margin-top: 16px;
    }
    .summary-card {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: #fbfdff;
    }
    .k {
      color: var(--muted);
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    .v { margin-top: 4px; font-size: 21px; font-weight: 800; }
    .card { overflow: hidden; }
    .table-wrap { overflow: auto; }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    th, td {
      border-bottom: 1px solid #eef1f5;
      padding: 8px 10px;
      text-align: right;
      vertical-align: top;
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
    .skills {
      display: grid;
      grid-template-columns: repeat(2, minmax(118px, 1fr));
      gap: 5px 8px;
      min-width: 260px;
      white-space: normal;
      text-align: left;
    }
    .skill-pill {
      border: 1px solid #e5eaf1;
      border-radius: 6px;
      padding: 4px 6px;
      background: #fbfdff;
    }
    .skill-pill b { display: inline-block; min-width: 22px; }
    .skill-label {
      margin-left: 5px;
      font-weight: 800;
    }
    .badges {
      display: flex;
      gap: 5px;
      flex-wrap: wrap;
      justify-content: flex-end;
      white-space: normal;
      min-width: 140px;
    }
    .badge {
      border: 1px solid var(--warn-line);
      border-radius: 999px;
      background: var(--warn-bg);
      color: #8a4b12;
      padding: 3px 7px;
      font-size: 11px;
      font-weight: 700;
    }
    details summary {
      cursor: pointer;
      color: var(--accent);
      font-weight: 800;
      margin-bottom: 10px;
    }
    .detail-grid {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(280px, 0.38fr);
      gap: 12px;
      align-items: start;
    }
    .subcard {
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
      background: #fff;
    }
    .subcard h3 {
      margin: 0;
      padding: 9px 10px;
      border-bottom: 1px solid var(--line);
      background: #fbfdff;
      font-size: 13px;
    }
    .subcard .inner { padding: 10px; }
    .mini-table th, .mini-table td { padding: 6px 8px; }
    .weekly-scroll {
      max-height: 260px;
      overflow: auto;
    }
    .training-scroll {
      max-height: 260px;
      overflow: auto;
    }
    .ignored-games summary {
      margin: 0;
      padding: 9px 10px;
      border-bottom: 1px solid var(--line);
      background: #fbfdff;
      font-size: 13px;
    }
    .ignored-games:not([open]) summary {
      border-bottom: 0;
    }
    .ignored-scroll {
      max-height: 180px;
      overflow: auto;
    }
    .muted { color: var(--muted); }
    .empty { color: var(--muted); padding: 12px; }
    .warnings {
      margin: 0;
      padding-left: 18px;
      color: #8a1c1c;
    }
    @media (max-width: 860px) {
      .wrap { padding: 14px; }
      .detail-grid { grid-template-columns: 1fr; }
      .skills { grid-template-columns: repeat(2, minmax(112px, 1fr)); min-width: 230px; }
    }
  </style>
</head>
<body>
  <main class="wrap">
    <div class="topbar">
      <a href="/">Back to report form</a>
      <span class="muted">Generated {{ report.generated_at }}</span>
    </div>
    <section class="hero">
      <h1>U21 squad analysis</h1>
      <p>{{ report.team_name }}{% if report.country_name %} · {{ report.country_name }}{% endif %} · Season {{ report.season }}</p>
      <div class="summary-grid">
        <div class="summary-card"><div class="k">Roster Players</div><div class="v">{{ report.players|length }}</div></div>
        <div class="summary-card"><div class="k">Coach Level</div><div class="v">7</div></div>
        <div class="summary-card"><div class="k">NT Strength</div><div class="v">{{ "Strong" if report.nt_strength == "strong" else "Weak" }}</div></div>
        <div class="summary-card"><div class="k">Skill Anchor</div><div class="v">Salary</div></div>
        <div class="summary-card"><div class="k">Minutes Source</div><div class="v">Club Logs</div></div>
      </div>
      {% if report.warnings %}
      <ul class="warnings">
        {% for warning in report.warnings %}
        <li>{{ warning }}</li>
        {% endfor %}
      </ul>
      {% endif %}
    </section>

    <section class="card">
      <h2>Roster Estimate</h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Player</th>
              <th>Age</th>
              <th>Height</th>
              <th>Salary</th>
              <th>Best Pos</th>
              <th>Potential</th>
              <th>Start Skills</th>
              <th>Modeled Start Salary</th>
              <th>Residual</th>
              <th>Warnings</th>
            </tr>
          </thead>
          <tbody>
            {% for player in report.players %}
            <tr>
              <td><strong>{{ player.name }}</strong><br><span class="muted">#{{ player.player_id }}</span></td>
              <td>{{ player.age if player.age is not none else "N/A" }}</td>
              <td>{{ player.height_cm_used }} cm</td>
              <td>{{ "{:,}".format(player.salary) if player.salary else "N/A" }}</td>
              <td>{{ player.best_position }}</td>
              <td>{{ player.potential }}</td>
              <td>
                <div class="skills">
                  {% for row in player.estimated_start_skill_rows %}
                  {% for skill in row %}
                  <span class="skill-pill">
                    <b>{{ skill.skill }}</b> {{ skill.rounded }}
                    <span class="skill-label" style="color: {{ skill.color }}">{{ skill.label }}</span>
                  </span>
                  {% endfor %}
                  {% endfor %}
                </div>
              </td>
              <td>{{ "{:,}".format(player.modeled_start_salary) if player.modeled_start_salary else "N/A" }}</td>
              <td>{{ "%+d"|format(player.salary_residual) if player.salary_residual is not none else "N/A" }}</td>
              <td>
                <div class="badges">
                  {% for warning in player.warnings %}
                  <span class="badge">{{ warning }}</span>
                  {% endfor %}
                </div>
              </td>
            </tr>
            <tr>
              <td colspan="10">
                <details>
                  <summary>Weekly minutes, inferred training, and reverse-out details</summary>
                  <div class="detail-grid">
                    <div class="subcard">
                      <h3>Club-Game Weekly Minutes</h3>
                      <div class="table-wrap weekly-scroll">
                        <table class="mini-table">
                          <thead>
                            <tr>
                              <th>Season</th><th>Week</th><th>Age</th><th>PG</th><th>SG</th><th>SF</th><th>PF</th><th>C</th><th>46+ Pos</th><th>Training</th>
                            </tr>
                          </thead>
                          <tbody>
                            {% for row in player.weekly_rows %}
                            <tr>
                              <td>{{ row.season }}</td>
                              <td>{{ row.week }}</td>
                              <td>{{ row.age if row.age is not none else "N/A" }}</td>
                              <td>{{ row.position_minutes.PG }}</td>
                              <td>{{ row.position_minutes.SG }}</td>
                              <td>{{ row.position_minutes.SF }}</td>
                              <td>{{ row.position_minutes.PF }}</td>
                              <td>{{ row.position_minutes.C }}</td>
                              <td>{{ row.selected_position or "." }}</td>
                              <td>{{ row.training }}</td>
                            </tr>
                            {% else %}
                            <tr><td colspan="10" class="empty">No counting club-game rows found.</td></tr>
                            {% endfor %}
                          </tbody>
                        </table>
                      </div>
                    </div>
                    <div class="subcard">
                      <h3>Training Summary</h3>
                      <div class="inner training-scroll">
                        <p class="muted">46+ minute weeks by selected position</p>
                        <table class="mini-table">
                          <thead><tr><th>Age</th><th>Weeks</th><th>PG</th><th>SG</th><th>SF</th><th>PF</th><th>C</th></tr></thead>
                          <tbody>
                            {% for summary in player.training_summary_by_age %}
                            <tr>
                              <td>{{ summary.age }}</td>
                              <td>{{ summary.weeks }}</td>
                              <td>{{ summary.counts_by_position.PG }}</td>
                              <td>{{ summary.counts_by_position.SG }}</td>
                              <td>{{ summary.counts_by_position.SF }}</td>
                              <td>{{ summary.counts_by_position.PF }}</td>
                              <td>{{ summary.counts_by_position.C }}</td>
                            </tr>
                            {% else %}
                            <tr><td colspan="7" class="empty">No age summary available.</td></tr>
                            {% endfor %}
                          </tbody>
                        </table>
                        {% for summary in player.training_summary_by_age %}
                        <p class="muted">Age {{ summary.age }} inferred training</p>
                        <table class="mini-table">
                          <tbody>
                            {% for item in summary.trainings %}
                            <tr><td>S{{ item.season }} W{{ item.week }}</td><td>{{ item.training }}</td></tr>
                            {% else %}
                            <tr><td colspan="2" class="empty">No training inferred.</td></tr>
                            {% endfor %}
                          </tbody>
                        </table>
                        {% endfor %}
                        <p class="muted">Current-season training reversed out of the start estimate</p>
                        <table class="mini-table">
                          <tbody>
                            {% for row in player.current_season_training %}
                            <tr><td>W{{ row.week }}</td><td>{{ row.training }}</td></tr>
                            {% else %}
                            <tr><td colspan="2" class="empty">No current-season training inferred.</td></tr>
                            {% endfor %}
                          </tbody>
                        </table>
                      </div>
                    </div>
                    <details class="subcard ignored-games">
                      <summary>Ignored Games ({{ player.ignored_games|length }})</summary>
                      <div class="table-wrap ignored-scroll">
                        <table class="mini-table">
                          <thead><tr><th>Season</th><th>Date</th><th>Type</th><th>Pos</th><th>Min</th><th>Reason</th></tr></thead>
                          <tbody>
                            {% for game in player.ignored_games %}
                            <tr>
                              <td>{{ game.season }}</td>
                              <td>{{ game.date }}</td>
                              <td>{{ game.game_type }}</td>
                              <td>{{ game.position }}</td>
                              <td>{{ game.minutes }}</td>
                              <td>{{ game.reason }}</td>
                            </tr>
                            {% else %}
                            <tr><td colspan="6" class="empty">No ignored rows in selected seasons.</td></tr>
                            {% endfor %}
                          </tbody>
                        </table>
                      </div>
                    </details>
                  </div>
                </details>
              </td>
            </tr>
            {% else %}
            <tr><td colspan="10" class="empty">No roster players were found.</td></tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
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
  <title>Box Score Analysis Multi Match Aggregate</title>
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
    .link-btn {
      border: 0;
      background: none;
      color: var(--accent);
      padding: 0;
      font: inherit;
      font-weight: 800;
      cursor: pointer;
      text-decoration: underline;
    }
    .tactic-row-outside td {
      background: #eef7ff;
    }
    .tactic-row-inside td {
      background: #fff3e8;
    }
    .gdp-line {
      white-space: nowrap;
    }
    .gdp-mark {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 18px;
      height: 18px;
      margin-left: 5px;
      border-radius: 999px;
      font-size: 11px;
      font-weight: 900;
      line-height: 1;
      border: 1px solid transparent;
    }
    .gdp-mark.hit {
      color: #166534;
      background: #dcfce7;
      border-color: #86efac;
    }
    .gdp-mark.miss {
      color: #991b1b;
      background: #fee2e2;
      border-color: #fca5a5;
    }
    .effort-mark {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 22px;
      max-width: 240px;
      padding: 2px 8px;
      border-radius: 999px;
      color: #0f172a;
      background: #eef2ff;
      border: 1px solid #c7d2fe;
      font-weight: 900;
      letter-spacing: 0;
      white-space: nowrap;
      cursor: help;
    }
    .tactic-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      padding: 12px;
    }
    .tactic-card {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      overflow: hidden;
    }
    .tactic-card h3 {
      margin: 0;
      padding: 12px;
      font-size: 16px;
      border-bottom: 1px solid var(--line);
      background: #f9fbff;
    }
    .tactic-card.outside h3 {
      background: #eef7ff;
    }
    .tactic-card.inside h3 {
      background: #fff8df;
    }
    .position-block {
      padding: 10px 12px;
      border-bottom: 1px solid #edf1f5;
    }
    .position-block:last-child {
      border-bottom: 0;
    }
    .position-title {
      margin-bottom: 6px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 800;
    }
    .minutes-list {
      margin: 0;
      padding-left: 18px;
      font-size: 13px;
      line-height: 1.5;
    }
    .minutes-list span {
      color: var(--muted);
      font-size: 12px;
    }
    /* MULTI FILTERS START */
    .filter-bar {
      display: grid;
      grid-template-columns: minmax(180px, 1.2fr) repeat(4, minmax(120px, 0.75fr)) auto;
      gap: 10px;
      align-items: end;
      margin: -4px 0 18px;
      padding: 12px;
      background: #fff;
      border: 1px solid var(--line);
      border-radius: 12px;
      box-shadow: var(--shadow);
    }
    .filter-field {
      display: grid;
      gap: 5px;
      min-width: 0;
      color: var(--muted);
      font-size: 11px;
      font-weight: 800;
      text-transform: uppercase;
    }
    .filter-field input,
    .filter-field select {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px 9px;
      background: #fff;
      color: var(--ink);
      font-size: 13px;
      text-transform: none;
    }
    .filter-reset {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px 10px;
      background: #fff;
      color: var(--accent);
      font-size: 13px;
      font-weight: 800;
      cursor: pointer;
    }
    .filter-note {
      grid-column: 1 / -1;
      color: var(--muted);
      font-size: 12px;
    }
    /* MULTI FILTERS END */
    .card-head-actions {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      background: #fafcff;
    }
    .card-head-actions h2 {
      padding: 0;
      border-bottom: 0;
      background: transparent;
    }
    .nba-controls {
      display: grid;
      grid-template-columns: minmax(180px, 1.3fr) repeat(5, minmax(120px, 1fr));
      gap: 10px;
      padding: 12px;
      border-bottom: 1px solid var(--line);
      background: #fcfdff;
    }
    .nba-note {
      padding: 10px 12px;
      color: var(--muted);
      font-size: 12px;
      border-bottom: 1px solid var(--line);
      background: #fff;
    }
    .nba-actions {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }
    .mini-btn {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 7px 10px;
      background: #fff;
      color: var(--accent);
      font-size: 13px;
      font-weight: 800;
      cursor: pointer;
    }
    .modal-backdrop {
      position: fixed;
      inset: 0;
      display: none;
      align-items: center;
      justify-content: center;
      padding: 18px;
      background: rgba(15, 23, 42, 0.45);
      z-index: 100;
    }
    .modal-backdrop.open {
      display: flex;
    }
    .modal {
      width: min(760px, 100%);
      max-height: min(720px, 90vh);
      overflow: auto;
      border-radius: 12px;
      border: 1px solid var(--line);
      background: #fff;
      box-shadow: var(--shadow);
    }
    .modal-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      background: #fafcff;
    }
    .modal-head h3 {
      margin: 0;
      font-size: 16px;
    }
    .modal-body {
      padding: 14px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.5;
    }
    .modal-body dl {
      display: grid;
      grid-template-columns: minmax(100px, 0.35fr) 1fr;
      gap: 8px 14px;
      margin: 0;
    }
    .modal-body dt {
      color: var(--ink);
      font-weight: 800;
    }
    .modal-body dd {
      margin: 0;
    }
    @media (max-width: 960px) {
      .summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .panel-summary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .insight-grid { grid-template-columns: 1fr; }
      .tactic-grid { grid-template-columns: 1fr; }
      .filter-bar { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .filter-reset { grid-column: 1 / -1; }
      .nba-controls { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .modal-body dl { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <main class="wrap">
    <div class="topbar">
      <div class="small">Multi-match aggregate | BBAPI user: {{ username }}</div>
      <div class="topbar-actions">
        <a href="/">Run another report</a>
      </div>
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

    <!-- MULTI FILTERS START -->
    <section class="filter-bar" aria-label="Multi-match table filters">
      <label class="filter-field">Player
        <select id="globalPlayerFilter">
          <option value="all">All players</option>
        </select>
      </label>
      <label class="filter-field">Result
        <select id="globalResultFilter">
          <option value="all">All</option>
          <option value="win">Wins</option>
          <option value="loss">Losses</option>
        </select>
      </label>
      <label class="filter-field">Tactic Group
        <select id="globalTacticFilter">
          <option value="all">All</option>
          <option value="outside">Outside</option>
          <option value="inside">Inside</option>
          <option value="balanced">Other</option>
        </select>
      </label>
      <label class="filter-field">Min Attempts
        <input id="globalMinAttempts" type="number" min="0" step="1" value="0" />
      </label>
      <label class="filter-field">Min Minutes
        <input id="globalMinMinutes" type="number" min="0" step="1" value="0" />
      </label>
      <button type="button" id="globalResetFilters" class="filter-reset">Reset</button>
      <div class="filter-note" id="globalFilterNote">Filters update detailed tables only. Summary and detections stay based on the full aggregate.</div>
    </section>
    <!-- MULTI FILTERS END -->

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
      <h2>Tactic Position Minutes</h2>
      <div id="tacticMinutesPanel" class="tactic-grid"></div>
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

    <section class="card" id="nbaDashboardCard">
      <div class="card-head-actions">
        <h2>NBA-Style Dashboard</h2>
        <div class="nba-actions">
          <button type="button" id="nbaGlossaryBtn" class="mini-btn">Glossary</button>
        </div>
      </div>
      <div class="nba-controls" aria-label="NBA-style dashboard filters">
        <label class="filter-field">Player
          <select id="nbaPlayerFilter">
            <option value="all">All players</option>
          </select>
        </label>
        <label class="filter-field">Result
          <select id="nbaResultFilter">
            <option value="all">All</option>
            <option value="win">Wins</option>
            <option value="loss">Losses</option>
          </select>
        </label>
        <label class="filter-field">Tactic Group
          <select id="nbaTacticFilter">
            <option value="all">All</option>
            <option value="outside">Outside</option>
            <option value="inside">Inside</option>
            <option value="balanced">Other</option>
          </select>
        </label>
        <label class="filter-field">Min Minutes
          <input id="nbaMinMinutes" type="number" min="0" step="1" value="0" />
        </label>
        <label class="filter-field">Min FGA
          <input id="nbaMinFga" type="number" min="0" step="1" value="0" />
        </label>
        <label class="filter-field">Stat View
          <select id="nbaViewFilter">
            <option value="traditional">Traditional</option>
            <option value="advanced">Advanced Lite</option>
            <option value="shooting">Shooting</option>
            <option value="defense">Defense</option>
            <option value="clutch">Clutch</option>
            <option value="fourFactors">Four Factors</option>
          </select>
        </label>
      </div>
      <div id="nbaDashboardNote" class="nba-note"></div>
      <div id="nbaSummary" class="panel-summary"></div>
      <div class="table-wrap">
        <table id="nbaDashboardTable"></table>
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

    <div id="nbaGlossaryModal" class="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="nbaGlossaryTitle">
      <div class="modal">
        <div class="modal-head">
          <h3 id="nbaGlossaryTitle">NBA-Style Dashboard Glossary</h3>
          <button type="button" id="nbaGlossaryClose" class="mini-btn">Close</button>
        </div>
        <div class="modal-body">
          <dl>
            <dt>Traditional</dt><dd>Exact boxscore totals aggregated from the selected multi-match rows.</dd>
            <dt>FG%, 3P%, FT%</dt><dd>Exact makes divided by attempts for field goals, threes, and free throws.</dd>
            <dt>eFG%</dt><dd>Estimated effective field goal percentage: (FGM + 0.5 * 3PM) / FGA.</dd>
            <dt>TS%</dt><dd>Estimated true shooting percentage: PTS / (2 * (FGA + 0.44 * FTA)).</dd>
            <dt>AST/TO</dt><dd>Exact assists divided by turnovers; shown as N/A when turnovers are zero.</dd>
            <dt>FTr</dt><dd>Free throw rate: FTA / FGA.</dd>
            <dt>Usage Proxy</dt><dd>Estimated share of team shooting possessions: player (FGA + 0.44 * FTA + TO) divided by the same total for all filtered players.</dd>
            <dt>Per 36</dt><dd>Estimated rate per 36 minutes from exact totals and minutes.</dd>
            <dt>Shot Mix</dt><dd>Event-derived share of attempts from close, mid-range, and three-point groups.</dd>
            <dt>Open / Defended</dt><dd>Event-derived split based on whether the play-by-play identified a defender on the shot.</dd>
            <dt>Stop Rate</dt><dd>Estimated defensive success: defended attempts not made by the opponent divided by defended attempts.</dd>
            <dt>Clutch</dt><dd>Event-derived final 5 minutes of Q4 or overtime while score margin is 5 or less.</dd>
            <dt>Four Factors</dt><dd>Team-level estimates: eFG%, turnover rate, offensive rebound rate, and free throw rate.</dd>
          </dl>
        </div>
      </div>
    </div>

    <form id="singleMatchForm" method="post" action="/report" hidden>
      <input type="hidden" name="mode" value="single" />
      <input type="hidden" name="username" value="{{ username }}" />
      <input type="hidden" name="password" value="{{ password }}" />
      <input type="hidden" name="from_multi" value="1" />
      <input type="hidden" name="selected_team_key" value="{{ report_json.selected_team_key }}" />
      <input type="hidden" name="multi_source" value="{{ report_json.return_state.multi_source }}" />
      <input type="hidden" name="national_country_id" value="{{ report_json.return_state.national_country_id }}" />
      <input type="hidden" name="national_team_kind" value="{{ report_json.return_state.national_team_kind }}" />
      <input type="hidden" name="national_season" value="{{ report_json.return_state.national_season }}" />
      <input type="hidden" name="team_schedule_team_id" value="{{ report_json.return_state.team_schedule_team_id }}" />
      <input type="hidden" name="team_schedule_season" value="{{ report_json.return_state.team_schedule_season }}" />
      <input type="hidden" name="team_schedule_limit" value="{{ report_json.return_state.team_schedule_limit }}" />
      {% for value in report_json.return_state.team_schedule_types %}
      <input type="hidden" name="team_schedule_types" value="{{ value }}" />
      {% endfor %}
      {% if report_json.return_state.include_friendlies %}
      <input type="hidden" name="include_friendlies" value="1" />
      {% endif %}
      {% for value in report_json.input_matchids %}
      <input type="hidden" name="matchids" value="{{ value }}" />
      {% endfor %}
      <input type="hidden" name="matchid" id="singleMatchId" value="" />
    </form>

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

      function tacticGroupKey(tactics) {
        const code = tactics?.offense || "";
        if (["LookInside", "LowPost"].includes(code)) return "inside";
        if (["Motion", "RunAndGun", "Princeton"].includes(code)) return "outside";
        if (["Base", "Push", "Patient", "InsideIsolation", "OutsideIsolation"].includes(code)) return "balanced";
        return "";
      }

      function tacticGroupClass(tactics) {
        const group = tacticGroupKey(tactics);
        if (group === "outside") return "tactic-row-outside";
        if (group === "inside") return "tactic-row-inside";
        return "";
      }

      function gdpPartHtml(part) {
        if (!part) return "N/A";
        const value = part.value || "N/A";
        const result = part.result || "N/A";
        if (value === "N/A" && result === "N/A") return "N/A";
        if (result === "Correct") return `${value}<span class="gdp-mark hit" title="Correct">V</span>`;
        if (result === "Incorrect") return `${value}<span class="gdp-mark miss" title="Incorrect">X</span>`;
        return value;
      }

      function tacticSummary(tactics) {
        if (!tactics) return "-";
        return `
          <div><strong>O:</strong> ${tactics.offense_label || tactics.offense || "-"}</div>
          <div><strong>D:</strong> ${tactics.defense_label || tactics.defense || "-"}</div>
        `;
      }

      function gdpSummary(tactics) {
        const gdp = tactics?.gdp || {};
        return `
          <div class="gdp-line"><strong>Focus:</strong> ${gdpPartHtml(gdp.focus)}</div>
          <div class="gdp-line"><strong>Pace:</strong> ${gdpPartHtml(gdp.pace)}</div>
        `;
      }

      function effortMark(row) {
        const display = row.effort_display || {};
        const stronger = display.stronger || "-";
        const other = display.other || "-";
        const symbol = display.symbol || "==";
        return `<span class="effort-mark" title="${row.effort || ""}">${stronger} ${symbol} ${other}</span>`;
      }

      function openSingleMatch(matchid) {
        const form = document.getElementById("singleMatchForm");
        document.getElementById("singleMatchId").value = matchid;
        form.submit();
      }

      function renderTacticMinutes() {
        const panel = document.getElementById("tacticMinutesPanel");
        panel.innerHTML = (data.tactic_minutes || []).map(group => `
          <article class="tactic-card ${group.key}">
            <h3>${group.label}</h3>
            ${group.positions.map(position => `
              <div class="position-block">
                <div class="position-title">${position.label}</div>
                ${
                  position.players.length
                    ? `<ol class="minutes-list">${position.players.map(player => `<li>${player.name} <span>${player.mins} min</span></li>`).join("")}</ol>`
                    : `<div class="empty">No minutes</div>`
                }
              </div>
            `).join("")}
          </article>
        `).join("");
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
      const tableSorts = {
        playerSummary: { key: "fga", dir: "desc" },
        matchup: { key: "total_attempts", dir: "desc" },
        defense: { key: "total_attempts", dir: "desc" }
      };

      /* MULTI FILTERS START */
      const globalPlayerFilter = document.getElementById("globalPlayerFilter");
      const globalResultFilter = document.getElementById("globalResultFilter");
      const globalTacticFilter = document.getElementById("globalTacticFilter");
      const globalMinAttempts = document.getElementById("globalMinAttempts");
      const globalMinMinutes = document.getElementById("globalMinMinutes");
      const globalResetFilters = document.getElementById("globalResetFilters");
      const globalFilterNote = document.getElementById("globalFilterNote");
      const matchesById = new Map((data.matches || []).map(row => [String(row.matchid), row]));

      function filterState() {
        return {
          player: globalPlayerFilter.value,
          result: globalResultFilter.value,
          tactic: globalTacticFilter.value,
          minAttempts: Math.max(0, Number(globalMinAttempts.value) || 0),
          minMinutes: Math.max(0, Number(globalMinMinutes.value) || 0)
        };
      }

      function matchPassesGlobalFilters(matchid) {
        const state = filterState();
        const row = matchesById.get(String(matchid));
        if (!row) return true;
        if (state.result !== "all") {
          const result = String(row.result || "").toLowerCase();
          if (state.result === "win" && !result.startsWith("w")) return false;
          if (state.result === "loss" && !result.startsWith("l")) return false;
        }
        if (state.tactic !== "all") {
          const group = tacticGroupKey(row.selected_tactics);
          if (state.tactic === "balanced") {
            if (group === "outside" || group === "inside") return false;
          } else if (group !== state.tactic) return false;
        }
        return true;
      }

      function playerPassesGlobalFilters(row, attempts = 0, minutes = 0) {
        const state = filterState();
        if (state.player !== "all" && row.name !== state.player) return false;
        if (state.minAttempts && attempts < state.minAttempts) return false;
        if (state.minMinutes && minutes < state.minMinutes) return false;
        return true;
      }

      function filteredMatches() {
        const state = filterState();
        return (data.matches || []).filter(row => {
          if (state.result !== "all") {
            const result = String(row.result || "").toLowerCase();
            if (state.result === "win" && !result.startsWith("w")) return false;
            if (state.result === "loss" && !result.startsWith("l")) return false;
          }
          if (state.tactic !== "all") {
            const group = tacticGroupKey(row.selected_tactics);
            if (state.tactic === "balanced") {
              if (group === "outside" || group === "inside") return false;
            } else if (group !== state.tactic) return false;
          }
          return true;
        });
      }

      function populateGlobalFilters() {
        const names = new Set();
        (data.player_summary || []).forEach(row => names.add(row.name));
        (data.offense?.players || []).forEach(row => names.add(row.name));
        (data.defended_shots?.players || []).forEach(name => names.add(name));
        [...names].sort((a, b) => a.localeCompare(b)).forEach(name => {
          const opt = document.createElement("option");
          opt.value = name;
          opt.textContent = name;
          globalPlayerFilter.appendChild(opt);
        });
      }

      function renderFilteredTables() {
        renderMatchSummaryTable();
        renderPlayerSummaryTable();
        renderPlayerMatchupTable();
        renderPlayerDefenseTable();
        renderOffensePlayersTable();
        renderDefendedShots();
        const state = filterState();
        const active = [
          state.player !== "all",
          state.result !== "all",
          state.tactic !== "all",
          state.minAttempts > 0,
          state.minMinutes > 0
        ].filter(Boolean).length;
        globalFilterNote.textContent = active
          ? `${active} filter${active === 1 ? "" : "s"} active. Summary and detections stay based on the full aggregate.`
          : "Filters update detailed tables only. Summary and detections stay based on the full aggregate.";
      }

      function resetGlobalFilters() {
        globalPlayerFilter.value = "all";
        globalResultFilter.value = "all";
        globalTacticFilter.value = "all";
        globalMinAttempts.value = "0";
        globalMinMinutes.value = "0";
        renderFilteredTables();
      }
      /* MULTI FILTERS END */


      function shotStatRatio(stat) {
        return stat && stat.a ? stat.m / stat.a : null;
      }

      function defenseSuccessRatio(stat) {
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

      function statRatio(stat) {
        return stat && stat.a ? stat.m / stat.a : -1;
      }

      function defenseRatio(stat) {
        return stat && stat.a ? (stat.a - stat.m) / stat.a : -1;
      }

      function compareNumbers(av, bv, dir) {
        return ((Number(av) || 0) - (Number(bv) || 0)) * dir;
      }

      function compareStats(a, b, column, dir) {
        const av = column.get(a);
        const bv = column.get(b);
        if (column.type === "text") {
          return String(av || "").localeCompare(String(bv || ""), undefined, { sensitivity: "base" }) * dir;
        }
        if (column.type === "shot") {
          return (
            (statRatio(av) - statRatio(bv)) * dir ||
            compareNumbers(av?.a, bv?.a, dir) ||
            compareNumbers(av?.m, bv?.m, dir)
          );
        }
        if (column.type === "defense") {
          return (
            (defenseRatio(av) - defenseRatio(bv)) * dir ||
            compareNumbers(av?.a, bv?.a, dir) ||
            compareNumbers((av?.a || 0) - (av?.m || 0), (bv?.a || 0) - (bv?.m || 0), dir)
          );
        }
        return compareNumbers(av, bv, dir);
      }

      function sortRows(rows, columns, sortState) {
        const column = columns.find(item => item.key === sortState.key) || columns[0];
        const dir = sortState.dir === "asc" ? 1 : -1;
        return [...rows].sort((a, b) => (
          compareStats(a, b, column, dir) ||
          String(a.name || "").localeCompare(String(b.name || ""), undefined, { sensitivity: "base" })
        ));
      }

      function sortableHeader(column, sortState) {
        const active = sortState.key === column.key;
        return `
          <th class="sortable-th" data-sort-key="${column.key}" aria-sort="${active ? (sortState.dir === "asc" ? "ascending" : "descending") : "none"}">
            ${column.label}<span class="sort-indicator">${active ? (sortState.dir === "asc" ? "^" : "v") : ""}</span>
          </th>
        `;
      }

      function attachSortHandlers(table, sortState, renderFn) {
        table.querySelectorAll("th[data-sort-key]").forEach(th => {
          th.addEventListener("click", () => {
            const key = th.dataset.sortKey;
            sortState.dir = sortState.key === key && sortState.dir === "desc" ? "asc" : "desc";
            sortState.key = key;
            renderFn();
          });
        });
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
          const on = defenseSuccessRatio(row.teamDefOn);
          const off = defenseSuccessRatio(row.teamDefOff);
          if (on === null || off === null || row.teamDefOn.a < MIN_DETECTION_ATTEMPTS || row.teamDefOff.a < MIN_DETECTION_ATTEMPTS) return;
          const lift = (on - off) * 100;
          const score = Math.abs(lift) * Math.log1p(Math.min(row.teamDefOn.a, row.teamDefOff.a));
          const better = lift > 0;
          pushDetection(rows, {
            type: "Defensive On/Off Lift",
            player: row.name,
            finding: `Defensive success rate ${better ? "rises" : "falls"} by ${Math.abs(lift).toFixed(1)}pp when he plays`,
            evidence: `On ${formatPctRatio(on)} (${row.teamDefOn.a - row.teamDefOn.m}/${row.teamDefOn.a}), off ${formatPctRatio(off)} (${row.teamDefOff.a - row.teamDefOff.m}/${row.teamDefOff.a})`,
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
          const teamSuccess = defenseSuccessRatio(total);
          if (teamSuccess === null) return;
          (data.defense || []).forEach(row => {
            const stat = row[key];
            const success = defenseSuccessRatio(stat);
            if (success === null || stat.a < MIN_DETECTION_ATTEMPTS) return;
            const diff = (success - teamSuccess) * 100;
            const score = Math.abs(diff) * Math.log1p(stat.a);
            const better = diff > 0;
            pushDetection(rows, {
              type: "Defended Shot Signal",
              player: row.name,
              finding: `${better ? "Strong" : "Concerning"} result on ${label}`,
              evidence: `${formatPctRatio(success)} success (${stat.a - stat.m}/${stat.a}) vs team ${formatPctRatio(teamSuccess)}, ${formatSignedPp(diff)}`,
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

      function renderMatchSummaryTable() {
        const rows = filteredMatches();
        document.getElementById("matchSummaryTable").innerHTML = `
          <thead>
            <tr>
              <th>Match ID</th><th>Home Team</th><th>Away Team</th><th>Score</th><th>Detected Team Side</th><th>Result</th><th>Selected Tactics</th><th>Selected GDP</th><th>Opponent Tactics</th><th>Opponent GDP</th><th>Status</th><th>Effort</th>
            </tr>
          </thead>
          <tbody>
            ${rows.map(row => `
              <tr class="${tacticGroupClass(row.selected_tactics)}">
                <td>${String(row.matchid).match(/^\\d+$/) ? `<button type="button" class="link-btn" data-match-id="${row.matchid}">${row.matchid}</button>` : row.matchid}</td>
                <td>${row.home_team}</td>
                <td>${row.away_team}</td>
                <td>${row.score}</td>
                <td>${row.detected_side}</td>
                <td>${row.result}</td>
                <td>${tacticSummary(row.selected_tactics)}</td>
                <td>${gdpSummary(row.selected_tactics)}</td>
                <td>${tacticSummary(row.opponent_tactics)}</td>
                <td>${gdpSummary(row.opponent_tactics)}</td>
                <td>${row.status}</td>
                <td>${effortMark(row)}</td>
              </tr>
            `).join("") || `<tr><td colspan="12" class="empty">No matches match the current filters.</td></tr>`}
          </tbody>
        `;
        document.querySelectorAll("#matchSummaryTable [data-match-id]").forEach(button => {
          button.addEventListener("click", () => openSingleMatch(button.dataset.matchId));
        });
      }

      renderTacticMinutes();

      const playerSummaryColumns = [
        { key: "name", label: "Player", type: "text", get: row => row.name },
        { key: "gp", label: "GP", type: "number", get: row => row.gp },
        { key: "mins", label: "MIN", type: "number", get: row => row.mins },
        { key: "pts", label: "PTS", type: "number", get: row => row.pts },
        { key: "fga", label: "FG", type: "shot", get: row => ({ m: row.fgm, a: row.fga }) },
        { key: "tpa", label: "3PT", type: "shot", get: row => ({ m: row.tpm, a: row.tpa }) },
        { key: "fta", label: "FT", type: "shot", get: row => ({ m: row.ftm, a: row.fta }) },
        { key: "tr", label: "REB", type: "number", get: row => row.tr },
        { key: "ast", label: "AST", type: "number", get: row => row.ast },
        { key: "to", label: "TO", type: "number", get: row => row.to },
        { key: "stl", label: "STL", type: "number", get: row => row.stl },
        { key: "blk", label: "BLK", type: "number", get: row => row.blk },
        { key: "pf", label: "PF", type: "number", get: row => row.pf },
        { key: "pm", label: "+/-", type: "number", get: row => row.pm }
      ];

      const matchupColumns = [
        { key: "name", label: "Player", type: "text", get: row => row.name },
        { key: "defended", label: "With Defense", type: "shot", get: row => row.defended },
        { key: "openClose", label: "Open Close", type: "shot", get: row => row.openClose },
        { key: "openMid", label: "Open Mid", type: "shot", get: row => row.openMid },
        { key: "openThree", label: "Open 3PT", type: "shot", get: row => row.openThree },
        { key: "openTotal", label: "Open Total", type: "shot", get: row => row.openTotal },
        { key: "teamOn", label: "Team FG On", type: "shot", get: row => row.teamOn },
        { key: "teamOff", label: "Team FG Off", type: "shot", get: row => row.teamOff },
        { key: "withPass", label: "Pass Received", type: "shot", get: row => row.withPass },
        { key: "withoutPass", label: "No Pass", type: "shot", get: row => row.withoutPass },
        { key: "total_attempts", label: "Attempts", type: "number", get: row => row.total_attempts }
      ];

      const defenseColumns = [
        { key: "name", label: "Player", type: "text", get: row => row.name },
        { key: "teamDefOn", label: "Team Def On", type: "defense", get: row => row.teamDefOn },
        { key: "teamDefOff", label: "Team Def Off", type: "defense", get: row => row.teamDefOff },
        { key: "defendedTotal", label: "Defended Total", type: "defense", get: row => row.defendedTotal },
        { key: "defendedClose", label: "Defended Close", type: "defense", get: row => row.defendedClose },
        { key: "defendedMid", label: "Defended Mid", type: "defense", get: row => row.defendedMid },
        { key: "defendedThree", label: "Defended 3PT", type: "defense", get: row => row.defendedThree },
        { key: "total_attempts", label: "Attempts", type: "number", get: row => row.total_attempts }
      ];

      function renderPlayerSummaryTable() {
        const table = document.getElementById("playerSummaryTable");
        const baseRows = (data.player_summary || []).filter(row => playerPassesGlobalFilters(row, row.fga || 0, row.mins || 0));
        const rows = sortRows(baseRows, playerSummaryColumns, tableSorts.playerSummary);
        table.innerHTML = `
          <thead><tr>${playerSummaryColumns.map(column => sortableHeader(column, tableSorts.playerSummary)).join("")}</tr></thead>
          <tbody>
            ${rows.map(row => `
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
            `).join("") || `<tr><td colspan="14" class="empty">No players match the current filters.</td></tr>`}
          </tbody>
        `;
        attachSortHandlers(table, tableSorts.playerSummary, renderPlayerSummaryTable);
      }

      function renderPlayerMatchupTable() {
        const table = document.getElementById("playerMatchupTable");
        const rows = sortRows(
          (data.matchup || []).filter(row => playerPassesGlobalFilters(row, row.total_attempts || 0, 0)),
          matchupColumns,
          tableSorts.matchup
        );
        table.innerHTML = `
          <thead><tr>${matchupColumns.filter(column => column.key !== "total_attempts").map(column => sortableHeader(column, tableSorts.matchup)).join("")}</tr></thead>
          <tbody>
            ${rows.map(row => `
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
            `).join("") || `<tr><td colspan="10" class="empty">No matchup rows match the current filters.</td></tr>`}
          </tbody>
        `;
        attachSortHandlers(table, tableSorts.matchup, renderPlayerMatchupTable);
      }

      function renderPlayerDefenseTable() {
        const table = document.getElementById("playerDefenseTable");
        const rows = sortRows(
          (data.defense || []).filter(row => playerPassesGlobalFilters(row, row.total_attempts || 0, 0)),
          defenseColumns,
          tableSorts.defense
        );
        table.innerHTML = `
          <thead><tr>${defenseColumns.filter(column => column.key !== "total_attempts").map(column => sortableHeader(column, tableSorts.defense)).join("")}</tr></thead>
          <tbody>
            ${rows.map(row => `
              <tr>
                <td>${row.name}</td>
                <td>${defensePctHtml(row.teamDefOn)}</td>
                <td>${defensePctHtml(row.teamDefOff)}</td>
                <td>${defenseStatHtml(row.defendedTotal)}</td>
                <td>${defenseStatHtml(row.defendedClose)}</td>
                <td>${defenseStatHtml(row.defendedMid)}</td>
                <td>${defenseStatHtml(row.defendedThree)}</td>
              </tr>
            `).join("") || `<tr><td colspan="7" class="empty">No defense rows match the current filters.</td></tr>`}
          </tbody>
        `;
        attachSortHandlers(table, tableSorts.defense, renderPlayerDefenseTable);
      }

      renderDetections();

      function renderOffensePlayersTable() {
        const rows = [...(data.offense.players || [])]
          .filter(row => playerPassesGlobalFilters(row, row.total?.a || 0, 0))
          .sort((a, b) => b.total.a - a.total.a || a.name.localeCompare(b.name));
        document.getElementById("offPlayersTable").innerHTML = `
          <thead>
            <tr>
              <th>Player</th>
              ${data.offense.shot_types.map(code => `<th>${shotTypeLabel[code] || code}</th>`).join("")}
              <th>Total</th>
            </tr>
          </thead>
          <tbody>
            ${rows.map(row => `
              <tr>
                <td>${row.name}</td>
                ${data.offense.shot_types.map(code => `<td>${offCellHtml(row.counts[code])}</td>`).join("")}
                <td>${offCellHtml(row.total)}</td>
              </tr>
            `).join("") || `<tr><td colspan="${(data.offense.shot_types || []).length + 2}" class="empty">No offense rows match the current filters.</td></tr>`}
          </tbody>
        `;
      }

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
          if (!matchPassesGlobalFilters(ev.matchid)) return false;
          const state = filterState();
          if (state.player !== "all" && ev.defender !== state.player && ev.shooter !== state.player) return false;
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

      const nbaPlayerFilter = document.getElementById("nbaPlayerFilter");
      const nbaResultFilter = document.getElementById("nbaResultFilter");
      const nbaTacticFilter = document.getElementById("nbaTacticFilter");
      const nbaMinMinutes = document.getElementById("nbaMinMinutes");
      const nbaMinFga = document.getElementById("nbaMinFga");
      const nbaViewFilter = document.getElementById("nbaViewFilter");
      const nbaSummary = document.getElementById("nbaSummary");
      const nbaDashboardNote = document.getElementById("nbaDashboardNote");
      const nbaDashboardTable = document.getElementById("nbaDashboardTable");
      const nbaGlossaryModal = document.getElementById("nbaGlossaryModal");
      const nbaGlossaryBtn = document.getElementById("nbaGlossaryBtn");
      const nbaGlossaryClose = document.getElementById("nbaGlossaryClose");
      const nbaSorts = {
        traditional: { key: "pts", dir: "desc" },
        advanced: { key: "efg", dir: "desc" },
        shooting: { key: "fga", dir: "desc" },
        defense: { key: "defendedShots", dir: "desc" },
        clutch: { key: "clutchPts", dir: "desc" },
        fourFactors: { key: "efg", dir: "desc" }
      };

      function nbaFilterState() {
        return {
          player: nbaPlayerFilter.value,
          result: nbaResultFilter.value,
          tactic: nbaTacticFilter.value,
          minMinutes: Math.max(0, Number(nbaMinMinutes.value) || 0),
          minFga: Math.max(0, Number(nbaMinFga.value) || 0),
          view: nbaViewFilter.value
        };
      }

      function nbaRowPassesFilters(row, state) {
        if (state.player !== "all" && row.name !== state.player) return false;
        if (state.result !== "all") {
          if (state.result === "win" && row.result !== "W") return false;
          if (state.result === "loss" && row.result !== "L") return false;
        }
        if (state.tactic !== "all" && row.tactic_group !== state.tactic) return false;
        return true;
      }

      function nbaTeamRowPassesFilters(row, state) {
        if (state.result !== "all") {
          if (state.result === "win" && row.result !== "W") return false;
          if (state.result === "loss" && row.result !== "L") return false;
        }
        if (state.tactic !== "all" && row.tactic_group !== state.tactic) return false;
        return true;
      }

      function emptyNbaSplit() {
        return { m: 0, a: 0 };
      }

      function addNbaSplit(target, source) {
        target.m += source?.m || 0;
        target.a += source?.a || 0;
      }

      function emptyNbaAggregate(name) {
        return {
          name,
          matches: new Set(),
          mins: 0,
          pts: 0,
          fgm: 0,
          fga: 0,
          tpm: 0,
          tpa: 0,
          ftm: 0,
          fta: 0,
          or: 0,
          dr: 0,
          tr: 0,
          ast: 0,
          to: 0,
          stl: 0,
          blk: 0,
          pf: 0,
          pm: 0,
          shots_close: emptyNbaSplit(),
          shots_mid: emptyNbaSplit(),
          shots_three: emptyNbaSplit(),
          assisted: emptyNbaSplit(),
          unassisted: emptyNbaSplit(),
          open: emptyNbaSplit(),
          defended: emptyNbaSplit(),
          team_def_on: emptyNbaSplit(),
          team_def_off: emptyNbaSplit(),
          defended_total: emptyNbaSplit(),
          defended_close: emptyNbaSplit(),
          defended_mid: emptyNbaSplit(),
          defended_three: emptyNbaSplit(),
          clutch: { pts: 0, fgm: 0, fga: 0, tpm: 0, tpa: 0, ast: 0, to: 0, pm: 0 }
        };
      }

      function aggregateNbaPlayers(state) {
        const byName = new Map();
        (data.nba_dashboard?.players || []).forEach(row => {
          if (!nbaRowPassesFilters(row, state)) return;
          const item = byName.get(row.name) || emptyNbaAggregate(row.name);
          byName.set(row.name, item);
          item.matches.add(row.matchid);
          ["mins", "pts", "fgm", "fga", "tpm", "tpa", "ftm", "fta", "or", "dr", "tr", "ast", "to", "stl", "blk", "pf", "pm"].forEach(key => {
            item[key] += Number(row[key]) || 0;
          });
          ["shots_close", "shots_mid", "shots_three", "assisted", "unassisted", "open", "defended", "team_def_on", "team_def_off", "defended_total", "defended_close", "defended_mid", "defended_three"].forEach(key => {
            addNbaSplit(item[key], row[key]);
          });
          ["pts", "fgm", "fga", "tpm", "tpa", "ast", "to", "pm"].forEach(key => {
            item.clutch[key] += Number(row.clutch?.[key]) || 0;
          });
        });
        return [...byName.values()]
          .map(row => ({ ...row, gp: row.matches.size }))
          .filter(row => row.mins >= state.minMinutes && row.fga >= state.minFga)
          .sort((a, b) => b.fga - a.fga || b.pts - a.pts || a.name.localeCompare(b.name));
      }

      function aggregateNbaTeamRows(state) {
        return (data.nba_dashboard?.team_rows || []).filter(row => nbaTeamRowPassesFilters(row, state));
      }

      function pct(made, attempts) {
        return attempts ? `${((made / attempts) * 100).toFixed(1)}%` : "";
      }

      function ratio(value, denom) {
        return denom ? value / denom : null;
      }

      function formatRatio(value, digits = 2) {
        return value === null || !Number.isFinite(value) ? "N/A" : value.toFixed(digits);
      }

      function per36(value, mins) {
        return mins ? ((value / mins) * 36).toFixed(1) : "";
      }

      function splitMadeAttemptPct(split) {
        return split?.a ? `${split.m}/${split.a} ${pct(split.m, split.a)}` : "";
      }

      function stopRate(split) {
        return split?.a ? `${split.a - split.m}/${split.a} ${pct(split.a - split.m, split.a)}` : "";
      }

      function sumTeamStats(rows, side) {
        const out = { pts: 0, fgm: 0, fga: 0, tpm: 0, tpa: 0, ftm: 0, fta: 0, or: 0, dr: 0, tr: 0, to: 0 };
        rows.forEach(row => {
          const source = row[side] || {};
          Object.keys(out).forEach(key => {
            out[key] += Number(source[key]) || 0;
          });
        });
        return out;
      }

      function estimatedPoss(stats) {
        return stats.fga + (0.44 * stats.fta) - stats.or + stats.to;
      }

      function nullableRatio(value, denom) {
        return denom ? value / denom : null;
      }

      function compareNullable(av, bv, dir) {
        const aMissing = av === null || av === undefined || Number.isNaN(av);
        const bMissing = bv === null || bv === undefined || Number.isNaN(bv);
        if (aMissing && bMissing) return 0;
        if (aMissing) return 1;
        if (bMissing) return -1;
        return (av - bv) * dir;
      }

      function nbaSortValue(row, column) {
        const value = column.sortValue ? column.sortValue(row) : column.value(row);
        if (column.type === "text") return String(value || "");
        return value === "" ? null : Number(value);
      }

      function sortNbaRows(rows, columns, sortState) {
        const column = columns.find(item => item.key === sortState.key) || columns[0];
        const dir = sortState.dir === "asc" ? 1 : -1;
        return [...rows].sort((a, b) => {
          const av = nbaSortValue(a, column);
          const bv = nbaSortValue(b, column);
          if (column.type === "text") {
            return String(av).localeCompare(String(bv), undefined, { sensitivity: "base" }) * dir;
          }
          return compareNullable(av, bv, dir) || String(a.name || a.label || "").localeCompare(String(b.name || b.label || ""), undefined, { sensitivity: "base" });
        });
      }

      function nbaSortableHeader(column, sortState) {
        const active = sortState.key === column.key;
        return `
          <th class="sortable-th" data-nba-sort-key="${column.key}" aria-sort="${active ? (sortState.dir === "asc" ? "ascending" : "descending") : "none"}">
            ${column.label}<span class="sort-indicator">${active ? (sortState.dir === "asc" ? "^" : "v") : ""}</span>
          </th>
        `;
      }

      function renderNbaTable(columns, rows, emptyColspan, emptyMessage) {
        const sortState = nbaSorts[nbaViewFilter.value] || nbaSorts.traditional;
        const sorted = sortNbaRows(rows, columns, sortState);
        nbaDashboardTable.innerHTML = `
          <thead><tr>${columns.map(column => nbaSortableHeader(column, sortState)).join("")}</tr></thead>
          <tbody>
            ${sorted.map(row => `<tr>${columns.map(column => `<td>${column.render ? column.render(row) : column.value(row)}</td>`).join("")}</tr>`).join("") || `<tr><td colspan="${emptyColspan}" class="empty">${emptyMessage}</td></tr>`}
          </tbody>
        `;
        nbaDashboardTable.querySelectorAll("th[data-nba-sort-key]").forEach(th => {
          th.addEventListener("click", () => {
            const key = th.dataset.nbaSortKey;
            sortState.dir = sortState.key === key && sortState.dir === "desc" ? "asc" : "desc";
            sortState.key = key;
            renderNbaDashboard();
          });
        });
      }

      function renderNbaSummary(rows, teamRows, view) {
        const teamStats = sumTeamStats(teamRows, "team");
        const oppStats = sumTeamStats(teamRows, "opponent");
        const teamPoss = estimatedPoss(teamStats);
        const oppPoss = estimatedPoss(oppStats);
        nbaSummary.innerHTML = `
          <div class="summary-card"><div class="k">Players Shown</div><div class="v">${rows.length}</div></div>
          <div class="summary-card"><div class="k">Matches</div><div class="v">${teamRows.length}</div></div>
          <div class="summary-card"><div class="k">Team eFG%</div><div class="v">${pct(teamStats.fgm + 0.5 * teamStats.tpm, teamStats.fga) || "0.0%"}</div></div>
          <div class="summary-card"><div class="k">Opp eFG%</div><div class="v">${pct(oppStats.fgm + 0.5 * oppStats.tpm, oppStats.fga) || "0.0%"}</div></div>
          <div class="summary-card"><div class="k">Poss Est.</div><div class="v">${teamPoss ? teamPoss.toFixed(1) : "0.0"}</div></div>
          <div class="summary-card"><div class="k">View</div><div class="v">${view.replace(/([A-Z])/g, " $1")}</div></div>
        `;
      }

      function renderNbaTraditional(rows) {
        const columns = [
          { key: "name", label: "Player", type: "text", value: row => row.name },
          { key: "gp", label: "GP", value: row => row.gp },
          { key: "mins", label: "MIN", value: row => row.mins },
          { key: "pts", label: "PTS", value: row => row.pts },
          { key: "tr", label: "REB", value: row => row.tr },
          { key: "ast", label: "AST", value: row => row.ast },
          { key: "to", label: "TO", value: row => row.to },
          { key: "stl", label: "STL", value: row => row.stl },
          { key: "blk", label: "BLK", value: row => row.blk },
          { key: "pf", label: "PF", value: row => row.pf },
          { key: "pm", label: "+/-", value: row => row.pm },
          { key: "fgPct", label: "FG%", value: row => pct(row.fgm, row.fga), sortValue: row => nullableRatio(row.fgm, row.fga) },
          { key: "threePct", label: "3P%", value: row => pct(row.tpm, row.tpa), sortValue: row => nullableRatio(row.tpm, row.tpa) },
          { key: "ftPct", label: "FT%", value: row => pct(row.ftm, row.fta), sortValue: row => nullableRatio(row.ftm, row.fta) }
        ];
        renderNbaTable(columns, rows, columns.length, "No players match the NBA dashboard filters.");
      }

      function renderNbaAdvanced(rows) {
        const usageDenom = rows.reduce((sum, row) => sum + row.fga + (0.44 * row.fta) + row.to, 0);
        const usageValue = row => usageDenom ? (row.fga + (0.44 * row.fta) + row.to) / usageDenom : null;
        const columns = [
          { key: "name", label: "Player", type: "text", value: row => row.name },
          { key: "efg", label: "eFG%", value: row => pct(row.fgm + 0.5 * row.tpm, row.fga), sortValue: row => nullableRatio(row.fgm + 0.5 * row.tpm, row.fga) },
          { key: "ts", label: "TS% Est.", value: row => pct(row.pts, 2 * (row.fga + 0.44 * row.fta)), sortValue: row => nullableRatio(row.pts, 2 * (row.fga + 0.44 * row.fta)) },
          { key: "astTo", label: "AST/TO", value: row => formatRatio(ratio(row.ast, row.to)), sortValue: row => ratio(row.ast, row.to) },
          { key: "ftr", label: "FTr", value: row => formatRatio(ratio(row.fta, row.fga)), sortValue: row => ratio(row.fta, row.fga) },
          { key: "pps", label: "PTS/FGA", value: row => formatRatio(ratio(row.pts, row.fga)), sortValue: row => ratio(row.pts, row.fga) },
          { key: "usage", label: "Usage Proxy", value: row => usageValue(row) === null ? "N/A" : `${(usageValue(row) * 100).toFixed(1)}%`, sortValue: usageValue },
          { key: "pts36", label: "PTS/36", value: row => per36(row.pts, row.mins), sortValue: row => ratio(row.pts * 36, row.mins) },
          { key: "reb36", label: "REB/36", value: row => per36(row.tr, row.mins), sortValue: row => ratio(row.tr * 36, row.mins) },
          { key: "ast36", label: "AST/36", value: row => per36(row.ast, row.mins), sortValue: row => ratio(row.ast * 36, row.mins) }
        ];
        renderNbaTable(columns, rows, columns.length, "No players match the NBA dashboard filters.");
      }

      function renderNbaShooting(rows) {
        const shotAttempts = row => row.shots_close.a + row.shots_mid.a + row.shots_three.a;
        const columns = [
          { key: "name", label: "Player", type: "text", value: row => row.name },
          { key: "closeMix", label: "Close Mix", value: row => pct(row.shots_close.a, shotAttempts(row)), sortValue: row => nullableRatio(row.shots_close.a, shotAttempts(row)) },
          { key: "closeFg", label: "Close FG", value: row => splitMadeAttemptPct(row.shots_close), sortValue: row => nullableRatio(row.shots_close.m, row.shots_close.a) },
          { key: "midMix", label: "Mid Mix", value: row => pct(row.shots_mid.a, shotAttempts(row)), sortValue: row => nullableRatio(row.shots_mid.a, shotAttempts(row)) },
          { key: "midFg", label: "Mid FG", value: row => splitMadeAttemptPct(row.shots_mid), sortValue: row => nullableRatio(row.shots_mid.m, row.shots_mid.a) },
          { key: "threeMix", label: "3PT Mix", value: row => pct(row.shots_three.a, shotAttempts(row)), sortValue: row => nullableRatio(row.shots_three.a, shotAttempts(row)) },
          { key: "threeFg", label: "3PT FG", value: row => splitMadeAttemptPct(row.shots_three), sortValue: row => nullableRatio(row.shots_three.m, row.shots_three.a) },
          { key: "assisted", label: "Assisted", value: row => splitMadeAttemptPct(row.assisted), sortValue: row => nullableRatio(row.assisted.m, row.assisted.a) },
          { key: "unassisted", label: "Unassisted", value: row => splitMadeAttemptPct(row.unassisted), sortValue: row => nullableRatio(row.unassisted.m, row.unassisted.a) },
          { key: "open", label: "Open", value: row => splitMadeAttemptPct(row.open), sortValue: row => nullableRatio(row.open.m, row.open.a) },
          { key: "defended", label: "Defended", value: row => splitMadeAttemptPct(row.defended), sortValue: row => nullableRatio(row.defended.m, row.defended.a) },
          { key: "fga", label: "FGA", value: row => row.fga }
        ];
        renderNbaTable(columns, rows, columns.length, "No players match the NBA dashboard filters.");
      }

      function renderNbaDefense(rows) {
        const stopValue = split => split?.a ? (split.a - split.m) / split.a : null;
        const columns = [
          { key: "name", label: "Player", type: "text", value: row => row.name },
          { key: "defendedShots", label: "Defended Shots", value: row => row.defended_total.a },
          { key: "stopRate", label: "Stop Rate", value: row => stopRate(row.defended_total), sortValue: row => stopValue(row.defended_total) },
          { key: "closeStops", label: "Close Stops", value: row => stopRate(row.defended_close), sortValue: row => stopValue(row.defended_close) },
          { key: "midStops", label: "Mid Stops", value: row => stopRate(row.defended_mid), sortValue: row => stopValue(row.defended_mid) },
          { key: "threeStops", label: "3PT Stops", value: row => stopRate(row.defended_three), sortValue: row => stopValue(row.defended_three) },
          { key: "teamDefOn", label: "Team Def On", value: row => stopRate(row.team_def_on), sortValue: row => stopValue(row.team_def_on) },
          { key: "teamDefOff", label: "Team Def Off", value: row => stopRate(row.team_def_off), sortValue: row => stopValue(row.team_def_off) }
        ];
        renderNbaTable(columns, rows, columns.length, "No players match the NBA dashboard filters.");
      }

      function renderNbaClutch(rows) {
        const columns = [
          { key: "name", label: "Player", type: "text", value: row => row.name },
          { key: "clutchPts", label: "PTS", value: row => row.clutch.pts },
          { key: "clutchFga", label: "FGA", value: row => row.clutch.fga },
          { key: "clutchFgPct", label: "FG%", value: row => pct(row.clutch.fgm, row.clutch.fga), sortValue: row => nullableRatio(row.clutch.fgm, row.clutch.fga) },
          { key: "clutchTpa", label: "3PA", value: row => row.clutch.tpa },
          { key: "clutchThreePct", label: "3P%", value: row => pct(row.clutch.tpm, row.clutch.tpa), sortValue: row => nullableRatio(row.clutch.tpm, row.clutch.tpa) },
          { key: "clutchAst", label: "AST", value: row => row.clutch.ast },
          { key: "clutchTo", label: "TO", value: row => row.clutch.to },
          { key: "clutchPm", label: "+/-", value: row => row.clutch.pm }
        ];
        renderNbaTable(columns, rows, columns.length, "No players match the NBA dashboard filters.");
      }

      function renderNbaFourFactors(teamRows) {
        const rows = [
          { label: data.team_name, stats: sumTeamStats(teamRows, "team"), opp: sumTeamStats(teamRows, "opponent") },
          { label: "Opponents", stats: sumTeamStats(teamRows, "opponent"), opp: sumTeamStats(teamRows, "team") }
        ];
        const possValue = row => estimatedPoss(row.stats);
        const columns = [
          { key: "label", label: "Side", type: "text", value: row => row.label },
          { key: "efg", label: "eFG%", value: row => pct(row.stats.fgm + 0.5 * row.stats.tpm, row.stats.fga), sortValue: row => nullableRatio(row.stats.fgm + 0.5 * row.stats.tpm, row.stats.fga) },
          { key: "tov", label: "TOV% Est.", value: row => pct(row.stats.to, possValue(row)), sortValue: row => nullableRatio(row.stats.to, possValue(row)) },
          { key: "orb", label: "ORB%", value: row => pct(row.stats.or, row.stats.or + row.opp.dr), sortValue: row => nullableRatio(row.stats.or, row.stats.or + row.opp.dr) },
          { key: "ftr", label: "FTr", value: row => formatRatio(ratio(row.stats.fta, row.stats.fga)), sortValue: row => ratio(row.stats.fta, row.stats.fga) },
          { key: "poss", label: "Poss Est.", value: row => possValue(row) ? possValue(row).toFixed(1) : "0.0", sortValue: possValue },
          { key: "ptsPoss", label: "PTS/Poss Est.", value: row => formatRatio(ratio(row.stats.pts, possValue(row))), sortValue: row => ratio(row.stats.pts, possValue(row)) }
        ];
        renderNbaTable(columns, rows, columns.length, "No team rows match the NBA dashboard filters.");
      }

      function renderNbaDashboard() {
        const state = nbaFilterState();
        const playerState = state.view === "fourFactors"
          ? { ...state, player: "all", minMinutes: 0, minFga: 0 }
          : state;
        const rows = aggregateNbaPlayers(playerState);
        const teamRows = aggregateNbaTeamRows(state);
        renderNbaSummary(rows, teamRows, state.view);
        nbaDashboardNote.textContent = state.view === "fourFactors"
          ? "Four Factors are team-level estimates from the selected matches. Player and minute filters are ignored in this view."
          : "These filters apply only to this NBA-style dashboard. Estimated and proxy metrics are labeled in the glossary.";
        if (state.view === "traditional") renderNbaTraditional(rows);
        else if (state.view === "advanced") renderNbaAdvanced(rows);
        else if (state.view === "shooting") renderNbaShooting(rows);
        else if (state.view === "defense") renderNbaDefense(rows);
        else if (state.view === "clutch") renderNbaClutch(rows);
        else renderNbaFourFactors(teamRows);
      }

      function populateNbaFilters() {
        const names = new Set();
        (data.nba_dashboard?.players || []).forEach(row => names.add(row.name));
        [...names].sort((a, b) => a.localeCompare(b)).forEach(name => {
          const opt = document.createElement("option");
          opt.value = name;
          opt.textContent = name;
          nbaPlayerFilter.appendChild(opt);
        });
      }

      nbaGlossaryBtn.addEventListener("click", () => nbaGlossaryModal.classList.add("open"));
      nbaGlossaryClose.addEventListener("click", () => nbaGlossaryModal.classList.remove("open"));
      nbaGlossaryModal.addEventListener("click", ev => {
        if (ev.target === nbaGlossaryModal) nbaGlossaryModal.classList.remove("open");
      });
      [nbaPlayerFilter, nbaResultFilter, nbaTacticFilter, nbaMinMinutes, nbaMinFga, nbaViewFilter].forEach(node => {
        node.addEventListener("change", renderNbaDashboard);
        node.addEventListener("input", renderNbaDashboard);
      });

      document.addEventListener("click", () => {
        document.querySelectorAll(".multi-dd.open").forEach(node => node.classList.remove("open"));
      });

      populateNbaFilters();
      renderNbaDashboard();
      populateGlobalFilters();
      [globalPlayerFilter, globalResultFilter, globalTacticFilter, globalMinAttempts, globalMinMinutes].forEach(node => {
        node.addEventListener("change", renderFilteredTables);
        node.addEventListener("input", renderFilteredTables);
      });
      globalResetFilters.addEventListener("click", resetGlobalFilters);
      renderFilteredTables();
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
  <title>Box Score Analysis Match {{ matchid }}</title>
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
    .topbar-actions {
      display: flex;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }
    .topbar form {
      margin: 0;
    }
    .topbar button {
      border: 0;
      background: none;
      color: #0d47a1;
      padding: 0;
      font: inherit;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
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
      <div class="topbar-actions">
        {% if from_multi %}
        <form method="post" action="/report">
          <input type="hidden" name="mode" value="multi" />
          <input type="hidden" name="username" value="{{ username }}" />
          <input type="hidden" name="password" value="{{ password }}" />
          <input type="hidden" name="selected_team_key" value="{{ selected_team_key }}" />
          <input type="hidden" name="multi_source" value="{{ multi_source }}" />
          <input type="hidden" name="national_country_id" value="{{ national_country_id }}" />
          <input type="hidden" name="national_team_kind" value="{{ national_team_kind }}" />
          <input type="hidden" name="national_season" value="{{ national_season }}" />
          <input type="hidden" name="team_schedule_team_id" value="{{ team_schedule_team_id }}" />
          <input type="hidden" name="team_schedule_season" value="{{ team_schedule_season }}" />
          <input type="hidden" name="team_schedule_limit" value="{{ team_schedule_limit }}" />
          {% for value in team_schedule_types %}
          <input type="hidden" name="team_schedule_types" value="{{ value }}" />
          {% endfor %}
          {% if include_friendlies %}
          <input type="hidden" name="include_friendlies" value="1" />
          {% endif %}
          {% for value in multi_matchids %}
          <input type="hidden" name="matchids" value="{{ value }}" />
          {% endfor %}
          <button type="submit">Back to Multi Match</button>
        </form>
        {% endif %}
        <a href="/">Run another report</a>
      </div>
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
        <div class="small filter-block">
          <span>Player</span>
          <div id="eventPlayerFilter"></div>
        </div>
        <div class="small filter-block">
          <span>Event Type</span>
          <div id="eventTypeFilter"></div>
        </div>
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
    const eventPlayerFilter = document.getElementById("eventPlayerFilter");
    const eventTypeFilter = document.getElementById("eventTypeFilter");
    const eventCount = document.getElementById("eventCount");
    const eventPlayerFilterOptions = eventPlayerOptions();
    const eventTypeOptions = [
      { value: "passes", label: "Passes" },
      { value: "shot_close", label: "Shots Taken - Close" },
      { value: "shot_mid", label: "Shots Taken - Mid" },
      { value: "shot_three", label: "Shots Taken - 3PT" },
      { value: "rebound", label: "Rebound" },
      { value: "turnover", label: "Turnover" },
      { value: "score", label: "Score" },
      { value: "miss", label: "Miss" },
      { value: "assist", label: "Assist" },
      { value: "block", label: "Block" },
      { value: "foul", label: "Foul" }
    ];

    function eventPlayerOptions() {
      return [
        ...home.players.map((p, i) => ({ value: `0:${i}`, label: `${p.name} (${home.name})` })),
        ...away.players.map((p, i) => ({ value: `1:${i}`, label: `${p.name} (${away.name})` }))
      ];
    }

    function addEventPlayerKey(out, side, rawSlot) {
      const teamObj = getTeamBySide(Number(side));
      if (!teamObj || !Array.isArray(teamObj.players)) return;
      const idx = normalizeSlot(rawSlot, teamObj.players.length);
      if (idx !== null) out.add(`${Number(side)}:${idx}`);
    }

    function addEventPlayerIndexKey(out, side, rawIndex) {
      const teamObj = getTeamBySide(Number(side));
      if (!teamObj || !Array.isArray(teamObj.players)) return;
      const idx = normalizePlayerIndex(rawIndex, teamObj.players.length);
      if (idx !== null) out.add(`${Number(side)}:${idx}`);
    }

    function involvedPlayerKeys(ev) {
      const out = new Set();
      if (ev.event_type === "shot") {
        addEventPlayerKey(out, ev.attacking_team, ev.attacker);
        addEventPlayerKey(out, ev.defending_team, ev.defender);
        addEventPlayerKey(out, ev.attacking_team, ev.assistant);
      } else if (ev.event_type === "free_throw") {
        addEventPlayerKey(out, ev.attacking_team, ev.attacker);
      } else if (["interrupt", "foul", "rebound"].includes(ev.event_type)) {
        addEventPlayerKey(out, ev.attacking_team, ev.attacker);
        addEventPlayerKey(out, ev.defending_team, ev.defender);
      } else if (ev.event_type === "sub") {
        addEventPlayerIndexKey(out, ev.team, ev.player_in);
        addEventPlayerIndexKey(out, ev.team, ev.player_out);
      } else if (ev.event_type === "injury") {
        addEventPlayerKey(out, ev.injured_team, ev.injured_player);
        addEventPlayerKey(out, ev.causedby_team, ev.causedby_player);
      }
      return out;
    }

    function eventHasSelectedPlayer(ev, selectedPlayers) {
      if (selectedPlayers.size === 0 || selectedPlayers.size === eventPlayerFilterOptions.length) return true;
      const involved = involvedPlayerKeys(ev);
      return [...selectedPlayers].some(key => involved.has(key));
    }

    function eventTypeKeys(ev) {
      const keys = new Set();
      if (ev.event_type === "shot") {
        const range = getShotRange(ev.shot_type);
        if (range === "paint") keys.add("shot_close");
        else if (range === "jump") keys.add("shot_mid");
        else if (range === "three") keys.add("shot_three");

        if (madeResults.has(String(ev.shot_result))) keys.add("score");
        else keys.add("miss");

        if (String(ev.shot_result) === "3") keys.add("block");
        if (normalizeSlot(ev.assistant, getTeamBySide(Number(ev.attacking_team)).players.length) !== null) {
          keys.add("passes");
          if (madeResults.has(String(ev.shot_result))) keys.add("assist");
        }
      } else if (ev.event_type === "free_throw") {
        if (madeResults.has(String(ev.shot_result))) keys.add("score");
        else keys.add("miss");
      } else if (ev.event_type === "rebound") {
        if (!["933", "934"].includes(String(ev.rebound_type))) keys.add("rebound");
      } else if (ev.event_type === "interrupt") {
        keys.add("turnover");
      } else if (ev.event_type === "foul") {
        keys.add("foul");
      }
      return keys;
    }

    function eventTypeActorKeys(ev, typeKey) {
      const keys = new Set();
      if (ev.event_type === "shot") {
        if (["shot_close", "shot_mid", "shot_three", "score", "miss"].includes(typeKey)) {
          addEventPlayerKey(keys, ev.attacking_team, ev.attacker);
        } else if (["passes", "assist"].includes(typeKey)) {
          addEventPlayerKey(keys, ev.attacking_team, ev.assistant);
        } else if (typeKey === "block") {
          addEventPlayerKey(keys, ev.defending_team, ev.defender);
        }
      } else if (ev.event_type === "free_throw" && ["score", "miss"].includes(typeKey)) {
        addEventPlayerKey(keys, ev.attacking_team, ev.attacker);
      } else if (ev.event_type === "rebound" && typeKey === "rebound") {
        addEventPlayerKey(keys, ev.attacking_team, ev.attacker);
        addEventPlayerKey(keys, ev.defending_team, ev.defender);
      } else if (ev.event_type === "interrupt" && typeKey === "turnover") {
        addEventPlayerKey(keys, ev.attacking_team, ev.attacker);
        addEventPlayerKey(keys, ev.defending_team, ev.defender);
      } else if (ev.event_type === "foul" && typeKey === "foul") {
        addEventPlayerKey(keys, ev.attacking_team, ev.attacker);
        addEventPlayerKey(keys, ev.defending_team, ev.defender);
      }
      return keys;
    }

    function eventMatchesSelectedTypes(ev, selectedTypes) {
      if (selectedTypes.size === 0 || selectedTypes.size === eventTypeOptions.length) return true;
      const keys = eventTypeKeys(ev);
      return [...selectedTypes].some(key => keys.has(key));
    }

    function eventMatchesSelectedTypeRoles(ev, selectedTypes, selectedPlayers) {
      if (selectedPlayers.size === 0 || selectedPlayers.size === eventPlayerFilterOptions.length) {
        return eventMatchesSelectedTypes(ev, selectedTypes);
      }
      if (selectedTypes.size === 0 || selectedTypes.size === eventTypeOptions.length) return true;

      const eventKeys = eventTypeKeys(ev);
      return [...selectedTypes].some(typeKey => {
        if (!eventKeys.has(typeKey)) return false;
        const actorKeys = eventTypeActorKeys(ev, typeKey);
        return [...selectedPlayers].some(playerKey => actorKeys.has(playerKey));
      });
    }

    function setupEventFeedFilters() {
      initMultiDropdown(eventPlayerFilter, eventPlayerFilterOptions, renderEvents);
      initMultiDropdown(eventTypeFilter, eventTypeOptions, renderEvents);
    }

    function renderEvents() {
      const teamVal = teamFilter.value;
      const textVal = textFilter.value.trim().toLowerCase();
      const selectedPlayers = selectedValues(eventPlayerFilter);
      const selectedTypes = selectedValues(eventTypeFilter);
      const filtered = data.events.filter(ev => {
        const side = eventSide(ev.attacking_team);
        if (teamVal !== "all" && side !== teamVal) return false;
        if (!eventHasSelectedPlayer(ev, selectedPlayers)) return false;
        if (!eventMatchesSelectedTypeRoles(ev, selectedTypes, selectedPlayers)) return false;
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
    setupEventFeedFilters();
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
  <title>Box Score Analysis Animation {{ matchid }}</title>
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
      <div class="topbar-actions">
        <a href="/">New report</a>
      </div>
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


TACTIC_LABELS = {
    "LookInside": "Look inside",
    "LowPost": "Low post",
    "Motion": "Motion",
    "RunAndGun": "Run and gun",
    "Princeton": "Princeton",
    "Base": "Base Offense",
    "Push": "Push the ball",
    "Patient": "Patient",
    "InsideIsolation": "inside isolation",
    "OutsideIsolation": "outside isolation",
}

TACTIC_GROUPS = {
    "inside": {"label": "Inside", "tactics": {"LookInside", "LowPost"}},
    "outside": {"label": "Outside", "tactics": {"Motion", "RunAndGun", "Princeton"}},
    "balanced": {
        "label": "Balanced",
        "tactics": {"Base", "Push", "Patient", "InsideIsolation", "OutsideIsolation"},
    },
}

POSITION_SECONDS = [
    ("pg", "PG", "secs_pg"),
    ("sg", "SG", "secs_sg"),
    ("sf", "SF", "secs_sf"),
    ("pf", "PF", "secs_pf"),
    ("c", "C", "secs_c"),
]

TEAM_SCHEDULE_TYPE_OPTIONS = [
    {"value": "league", "label": "League"},
    {"value": "cup", "label": "Cup"},
    {"value": "bbm", "label": "BBM"},
    {"value": "pl", "label": "Private league"},
    {"value": "friendly", "label": "Friendly"},
    {"value": "nt", "label": "National team"},
    {"value": "bbb", "label": "BBB"},
    {"value": "unknown", "label": "Unknown"},
]

DEFAULT_TEAM_SCHEDULE_TYPES = [option["value"] for option in TEAM_SCHEDULE_TYPE_OPTIONS]


def tactic_label(code: Any) -> str:
    cleaned = str(code or "").strip()
    if not cleaned:
        return "-"
    return TACTIC_LABELS.get(cleaned, cleaned)


def tactic_group_key(code: Any) -> str | None:
    cleaned = str(code or "").strip()
    for key, group in TACTIC_GROUPS.items():
        if cleaned in group["tactics"]:
            return key
    return None


def parse_gdp_value(value: str | None) -> dict[str, str]:
    raw = (value or "N/A").strip() or "N/A"
    if raw.upper() == "N/A":
        return {"raw": "N/A", "value": "N/A", "result": "N/A"}
    if "." not in raw:
        return {"raw": raw, "value": raw, "result": "N/A"}
    base, suffix = raw.rsplit(".", 1)
    result_map = {"hit": "Correct", "miss": "Incorrect"}
    return {"raw": raw, "value": base or raw, "result": result_map.get(suffix.casefold(), suffix)}


def parse_team_tactics(xml_team: xml.Element | None) -> dict[str, Any]:
    if xml_team is None:
        return {
            "offense": "-",
            "offense_label": "-",
            "defense": "-",
            "defense_label": "-",
            "effort": "",
            "gdp": {"focus": parse_gdp_value(None), "pace": parse_gdp_value(None)},
        }

    off_strategy = (xml_team.findtext("./offStrategy") or "-").strip()
    def_strategy = (xml_team.findtext("./defStrategy") or "-").strip()
    return {
        "offense": off_strategy,
        "offense_label": tactic_label(off_strategy),
        "defense": def_strategy,
        "defense_label": tactic_label(def_strategy),
        "effort": (xml_team.findtext("./effort") or "").strip(),
        "gdp": {
            "focus": parse_gdp_value(xml_team.findtext("./gdp/focus")),
            "pace": parse_gdp_value(xml_team.findtext("./gdp/pace")),
        },
    }


def parse_int(value: str | None, default: int = 0) -> int:
    try:
        return int(str(value or "").strip())
    except ValueError:
        return default


def effort_summary(delta: int, away_name: str, home_name: str, away_effort: str = "", home_effort: str = "") -> str:
    # BBAPI appears to expose effortDelta as home effort minus away effort.
    if delta > 0:
        stronger = home_name
        other = away_name
        visible_effort = home_effort
    elif delta < 0:
        stronger = away_name
        other = home_name
        visible_effort = away_effort
    else:
        if away_effort and home_effort and away_effort == home_effort:
            detail = f" Effort: {away_effort}"
        else:
            details = []
            if away_effort:
                details.append(f"{away_name}: {away_effort}")
            if home_effort:
                details.append(f"{home_name}: {home_effort}")
            detail = f" Effort: {', '.join(details)}" if details else ""
        return f"Both teams put similar effort into this game.{detail}"

    if abs(delta) >= 2:
        sentence = f"{stronger} looked like the only team trying out there"
    else:
        sentence = f"{stronger} put more into this game than {other}"
    if visible_effort:
        sentence = f"{sentence}. Effort: {visible_effort}"
    return sentence


def effort_display(delta: int, away_name: str, home_name: str) -> dict[str, str]:
    if delta > 0:
        return {
            "stronger": home_name,
            "other": away_name,
            "symbol": ">>" if abs(delta) >= 2 else ">",
        }
    if delta < 0:
        return {
            "stronger": away_name,
            "other": home_name,
            "symbol": ">>" if abs(delta) >= 2 else ">",
        }
    return {"stronger": home_name, "other": away_name, "symbol": "=="}


def parse_boxscore_metadata(xml_text: str) -> dict[str, Any]:
    root = xml.fromstring(xml_text)
    match = root.find("./match")
    away = root.find("./match/awayTeam")
    home = root.find("./match/homeTeam")
    away_tactics = parse_team_tactics(away)
    home_tactics = parse_team_tactics(home)
    delta = parse_int(match.findtext("./effortDelta") if match is not None else None)
    away_name = away.findtext("./teamName", "Away") if away is not None else "Away"
    home_name = home.findtext("./teamName", "Home") if home is not None else "Home"
    return {
        "away": away_tactics,
        "home": home_tactics,
        "start_time": (match.findtext("./startTime") or "").strip() if match is not None else "",
        "effort_delta": delta,
        "effort_display": effort_display(delta, away_name, home_name),
        "effort_summary": effort_summary(
            delta,
            away_name,
            home_name,
            away_tactics.get("effort", ""),
            home_tactics.get("effort", ""),
        ),
    }


def empty_form_context(
    *,
    error: str = "",
    username: str = "",
    password: str = "",
    matchid: str = "138595249",
    mode: str = "multi",
    multi_matchids: list[str] | None = None,
    multi_source: str = "national",
    national_country_id: str = "",
    national_team_kind: str = "nt",
    national_season: str = "",
    include_friendlies: bool = False,
    team_schedule_team_id: str = "",
    team_schedule_season: str = "",
    team_schedule_limit: str = "10",
    team_schedule_types: list[str] | None = None,
    bb_site_password: str = "",
    estimator_country_id: str = "",
    estimator_season: str = "",
    estimator_nt_strength: str = "weak",
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
        "team_schedule_team_id": team_schedule_team_id,
        "team_schedule_season": team_schedule_season,
        "team_schedule_limit": team_schedule_limit,
        "team_schedule_types": list(team_schedule_types or DEFAULT_TEAM_SCHEDULE_TYPES),
        "bb_site_password": bb_site_password,
        "estimator_country_id": estimator_country_id,
        "estimator_season": estimator_season,
        "estimator_nt_strength": estimator_nt_strength if estimator_nt_strength in {"weak", "strong"} else "weak",
        "team_schedule_type_options": TEAM_SCHEDULE_TYPE_OPTIONS,
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
    return [
        {"id": str(season), "label": f"Season {season}", "current": season == DEFAULT_CURRENT_SEASON}
        for season in range(DEFAULT_CURRENT_SEASON, max(DEFAULT_CURRENT_SEASON - 10, 0), -1)
    ]


def normalize_season_options(seasons: Any) -> list[dict[str, Any]]:
    fallback = default_local_seasons()
    if not isinstance(seasons, list):
        return fallback

    by_id: dict[str, dict[str, Any]] = {}
    for season in seasons:
        if not isinstance(season, dict):
            continue
        season_id = str(season.get("id", "")).strip()
        if not season_id.isdigit():
            continue
        by_id[season_id] = {
            "id": season_id,
            "label": str(season.get("label") or f"Season {season_id}"),
            "current": False,
            "start": str(season.get("start") or ""),
            "end": str(season.get("end") or ""),
        }

    current_id = str(DEFAULT_CURRENT_SEASON)
    if current_id not in by_id:
        by_id[current_id] = {"id": current_id, "label": f"Season {current_id}", "current": False, "start": "", "end": ""}
    for season in by_id.values():
        season["current"] = season["id"] == current_id

    rows = sorted(by_id.values(), key=lambda item: int(str(item["id"])), reverse=True)
    return rows or fallback


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
    seasons = normalize_season_options(payload.get("seasons"))
    return {
        "countries": countries or fallback["countries"],
        "seasons": seasons or fallback["seasons"],
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
        if str(season.get("id")) == str(DEFAULT_CURRENT_SEASON):
            return str(season["id"])
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


def schedule_type_category(match_type: str) -> str:
    value = match_type.casefold()
    if value.startswith("league."):
        return "league"
    if value.startswith("cup"):
        return "cup"
    if value.startswith("bbm"):
        return "bbm"
    if value.startswith("pl."):
        return "pl"
    if value == "friendly" or value.startswith("friendly."):
        return "friendly"
    if value.startswith("nt."):
        return "nt"
    if value.startswith("bbb"):
        return "bbb"
    return "unknown"


def schedule_match_completed(row: dict[str, str]) -> bool:
    return bool(row.get("id")) and row.get("away_score", "").isdigit() and row.get("home_score", "").isdigit()


def fetch_team_schedule_matchids(
    username: str,
    password: str,
    team_id: str,
    season: str,
    limit: str,
    selected_types: list[str],
) -> tuple[list[str], list[str]]:
    if not team_id.isdigit():
        raise ValueError("Team ID must be numeric.")

    api = BBApi(username, password)
    if not getattr(api, "logged_in", False):
        raise ValueError("BBAPI login failed. Check username/password.")

    selected_season = season
    if not selected_season:
        selected_season = current_season_from_options(api.seasons())
    if not selected_season:
        raise ValueError("Could not detect the current BB season.")

    selected_type_set = set(selected_types or DEFAULT_TEAM_SCHEDULE_TYPES)
    rows = [
        row
        for row in api.schedule_matches(team_id, selected_season)
        if schedule_match_completed(row) and schedule_type_category(row.get("type", "")) in selected_type_set
    ]
    rows.sort(key=lambda row: row.get("start", ""), reverse=True)

    warnings: list[str] = [
        f"Team schedule source: only completed games from season {selected_season} were considered."
    ]
    if limit != "all":
        requested = int(limit) if limit.isdigit() else 10
        if len(rows) < requested:
            warnings.append(f"Team schedule source: found {len(rows)} completed matching games, fewer than the requested {requested}.")
        rows = rows[:requested]

    return [row["id"] for row in rows], warnings


def country_name_from_options(country_id: str) -> str:
    for country in load_local_national_options().get("countries", []):
        if str(country.get("id")) == str(country_id):
            return str(country.get("name", ""))
    return ""


def build_u21_training_report(
    username: str,
    password: str,
    site_password: str,
    country_id: str,
    season: str,
    nt_strength: str = "weak",
) -> dict[str, Any]:
    api = BBApi(username, password)
    if not getattr(api, "logged_in", False):
        raise ValueError("BBAPI login failed. Check username/security code.")

    selected_season = season or current_season_from_options(api.seasons())
    if not selected_season:
        raise ValueError("Could not detect the current BB season.")
    try:
        current_season = int(selected_season)
    except ValueError as exc:
        raise ValueError("Season must be numeric.") from exc

    site = BBSiteClient(username, site_password)
    site.login()
    team_name, roster = site.fetch_u21_roster(country_id)

    players: list[dict[str, Any]] = []
    report_warnings: list[str] = []
    if not roster:
        report_warnings.append("No players were found on the selected U21 roster page.")

    for roster_player in roster:
        player_warnings: list[str] = []
        try:
            info = api.player_info(roster_player.player_id)
        except Exception as exc:
            info = {"player_id": roster_player.player_id}
            player_warnings.append(f"BBAPI metadata failed: {exc}")

        metadata = PlayerMetadata(
            player_id=roster_player.player_id,
            first_name=str(info.get("first_name") or ""),
            last_name=str(info.get("last_name") or ""),
            age=info.get("age"),
            height=info.get("height"),
            salary=info.get("salary"),
            best_position=str(info.get("best_position") or ""),
            potential=info.get("potential"),
            game_shape=info.get("game_shape"),
            dmi=info.get("dmi"),
        )

        logs_by_season: dict[int, list[Any]] = {}
        for target_season in target_seasons_for_player(metadata.age, current_season):
            try:
                logs_by_season[target_season] = site.fetch_player_game_log(
                    roster_player.player_id,
                    target_season,
                )
            except Exception as exc:
                logs_by_season[target_season] = []
                player_warnings.append(f"Could not load player log for season {target_season}: {exc}")

        estimate = estimate_player(
            roster_player,
            metadata,
            logs_by_season,
            current_season=current_season,
            nt_strength=nt_strength,
        )
        estimate["warnings"] = player_warnings + estimate.get("warnings", [])
        players.append(estimate)

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "country_id": str(country_id),
        "country_name": country_name_from_options(country_id),
        "team_name": team_name,
        "season": current_season,
        "nt_strength": nt_strength if nt_strength in {"weak", "strong"} else "weak",
        "training_multiplier": 1.5 if nt_strength == "strong" else 1.0,
        "skills": list(SKILLS),
        "players": players,
        "warnings": report_warnings,
    }


def empty_nba_shot_split() -> dict[str, int]:
    return {"m": 0, "a": 0}


def empty_nba_player_row(
    matchid: str,
    result: str,
    tactic_group: str,
    player_name: str,
) -> dict[str, Any]:
    return {
        "matchid": matchid,
        "result": result,
        "tactic_group": tactic_group,
        "name": player_name,
        "mins": 0,
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
        "shots_close": empty_nba_shot_split(),
        "shots_mid": empty_nba_shot_split(),
        "shots_three": empty_nba_shot_split(),
        "assisted": empty_nba_shot_split(),
        "unassisted": empty_nba_shot_split(),
        "open": empty_nba_shot_split(),
        "defended": empty_nba_shot_split(),
        "team_def_on": empty_nba_shot_split(),
        "team_def_off": empty_nba_shot_split(),
        "defended_total": empty_nba_shot_split(),
        "defended_close": empty_nba_shot_split(),
        "defended_mid": empty_nba_shot_split(),
        "defended_three": empty_nba_shot_split(),
        "clutch": {
            "pts": 0,
            "fgm": 0,
            "fga": 0,
            "tpm": 0,
            "tpa": 0,
            "ast": 0,
            "to": 0,
            "pm": 0,
        },
    }


def add_nba_shot_split(target: dict[str, int], made: bool) -> None:
    target["a"] += 1
    if made:
        target["m"] += 1


def is_nba_made_result(value: Any) -> bool:
    return str(value) in {"1", "2", "5"}


def shot_points(shot_type: Any) -> int:
    return 3 if str(shot_type).startswith("10") else 2


def nba_tactic_group(code: Any) -> str:
    return tactic_group_key(code) or "balanced"


def nba_is_clutch(gameclock: Any, selected_score: int, opponent_score: int) -> bool:
    try:
        clock = int(gameclock)
    except (TypeError, ValueError):
        return False
    if abs(selected_score - opponent_score) > 5:
        return False
    if 2580 <= clock < 2880:
        return True
    if clock >= 2880:
        return ((clock - 2880) % 420) >= 120
    return False


def build_nba_team_row(
    matchid: str,
    result: str,
    tactic_group: str,
    team_obj: dict[str, Any],
    opp_obj: dict[str, Any],
) -> dict[str, Any]:
    team = team_obj["stats"]["total"]
    opp = opp_obj["stats"]["total"]
    return {
        "matchid": matchid,
        "result": result,
        "tactic_group": tactic_group,
        "team": {
            "pts": team["pts"],
            "fgm": team["fgm"],
            "fga": team["fga"],
            "tpm": team["tpm"],
            "tpa": team["tpa"],
            "ftm": team["ftm"],
            "fta": team["fta"],
            "or": team["or"],
            "dr": team["dr"],
            "tr": team["tr"],
            "to": team["to"],
        },
        "opponent": {
            "pts": opp["pts"],
            "fgm": opp["fgm"],
            "fga": opp["fga"],
            "tpm": opp["tpm"],
            "tpa": opp["tpa"],
            "ftm": opp["ftm"],
            "fta": opp["fta"],
            "or": opp["or"],
            "dr": opp["dr"],
            "tr": opp["tr"],
            "to": opp["to"],
        },
    }


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


def empty_match_tactics() -> dict[str, Any]:
    return {
        "offense": "-",
        "offense_label": "-",
        "defense": "-",
        "defense_label": "-",
        "effort": "",
        "gdp": {"focus": parse_gdp_value(None), "pace": parse_gdp_value(None)},
    }


def blank_match_row(matchid: str, status: str) -> dict[str, Any]:
    return {
        "matchid": matchid,
        "start_time": "",
        "home_team": "-",
        "away_team": "-",
        "score": "-",
        "detected_side": "-",
        "result": "-",
        "status": status,
        "effort": "-",
        "effort_delta": 0,
        "effort_display": {"stronger": "-", "other": "-", "symbol": "=="},
        "selected_tactics": empty_match_tactics(),
        "opponent_tactics": empty_match_tactics(),
    }


def init_tactic_minutes() -> dict[str, Any]:
    return {
        key: {
            "label": group["label"],
            "positions": {
                pos_key: {"label": pos_label, "players": {}}
                for pos_key, pos_label, _ in POSITION_SECONDS
            },
        }
        for key, group in TACTIC_GROUPS.items()
    }


def add_tactic_minutes(
    tactic_minutes: dict[str, Any],
    tactic_code: Any,
    players: list[dict[str, Any]],
    slot_map: dict[int, tuple[str, str]],
) -> None:
    group_key = tactic_group_key(tactic_code)
    if group_key is None:
        return

    for idx, player in enumerate(players):
        if idx not in slot_map:
            continue
        player_key, player_label = slot_map[idx]
        totals = player["stats"]["total"]
        for pos_key, _, secs_key in POSITION_SECONDS:
            secs = int(totals.get(secs_key, 0) or 0)
            if secs <= 0:
                continue
            players_by_pos = tactic_minutes[group_key]["positions"][pos_key]["players"]
            entry = players_by_pos.setdefault(player_key, {"name": player_label, "secs": 0})
            entry["secs"] += secs


def finalize_tactic_minutes(tactic_minutes: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for group_key in ("inside", "outside", "balanced"):
        group = tactic_minutes[group_key]
        positions = []
        for pos_key, pos_label, _ in POSITION_SECONDS:
            players = sorted(
                group["positions"][pos_key]["players"].values(),
                key=lambda item: (-item["secs"], item["name"].casefold()),
            )[:3]
            positions.append(
                {
                    "key": pos_key,
                    "label": pos_label,
                    "players": [
                        {"name": item["name"], "mins": secs_to_minutes(item["secs"])}
                        for item in players
                    ],
                }
            )
        out.append({"key": group_key, "label": group["label"], "positions": positions})
    return out


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
    boxscore_metadata = parse_boxscore_metadata(api.get_xml_boxscore(matchid=int(matchid)))

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
    report["start_time"] = boxscore_metadata.get("start_time", "")
    report["teamHome"]["tactics"] = boxscore_metadata["home"]
    report["teamAway"]["tactics"] = boxscore_metadata["away"]
    report["effort_delta"] = boxscore_metadata["effort_delta"]
    report["effort_display"] = boxscore_metadata["effort_display"]
    report["effort_summary"] = boxscore_metadata["effort_summary"]
    return report


def generate_report(matchid: str, username: str, password: str) -> dict[str, Any]:
    return load_game_report(matchid, username, password)


def aggregate_multi_match_report(
    matchids: list[str],
    username: str,
    password: str,
    selected_team_key: str | None = None,
    *,
    multi_source: str = "manual",
    national_country_id: str = "",
    national_team_kind: str = "nt",
    national_season: str = "",
    include_friendlies: bool = False,
    team_schedule_team_id: str = "",
    team_schedule_season: str = "",
    team_schedule_limit: str = "10",
    team_schedule_types: list[str] | None = None,
) -> tuple[str, dict[str, Any] | list[dict[str, Any]]]:
    loaded_games: list[dict[str, Any]] = []
    initial_rows: list[dict[str, Any]] = []
    warnings: list[str] = []

    for matchid in matchids:
        if not matchid.isdigit():
            msg = "Match ID must be numeric."
            warnings.append(f"Match {matchid}: {msg}")
            initial_rows.append(blank_match_row(matchid, msg))
            continue
        try:
            game_data = load_game_report(matchid, username, password)
        except Exception as exc:
            msg = f"Skipped: {exc}"
            warnings.append(f"Match {matchid}: {exc}")
            initial_rows.append(blank_match_row(matchid, msg))
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
    tactic_minutes = init_tactic_minutes()
    nba_player_rows: list[dict[str, Any]] = []
    nba_team_rows: list[dict[str, Any]] = []
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
                    "start_time": game_data.get("start_time", ""),
                    "home_team": game_data["teamHome"]["name"],
                    "away_team": game_data["teamAway"]["name"],
                    "score": format_score(game_data),
                    "detected_side": "-",
                    "result": "-",
                    "status": msg,
                    "effort": game_data.get("effort_summary", "-"),
                    "effort_delta": game_data.get("effort_delta", 0),
                    "effort_display": game_data.get("effort_display", {"stronger": "-", "other": "-", "symbol": "=="}),
                    "selected_tactics": empty_match_tactics(),
                    "opponent_tactics": empty_match_tactics(),
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
        tactic_group = nba_tactic_group(team_obj.get("tactics", {}).get("offense"))
        if result == "W":
            wins += 1
        else:
            losses += 1

        match_rows.append(
            {
                "matchid": matchid,
                "start_time": game_data.get("start_time", ""),
                "home_team": game_data["teamHome"]["name"],
                "away_team": game_data["teamAway"]["name"],
                "score": format_score(game_data),
                "detected_side": "Home" if side == 0 else "Away",
                "result": result,
                "status": "Used",
                "effort": game_data.get("effort_summary", "-"),
                "effort_delta": game_data.get("effort_delta", 0),
                "effort_display": game_data.get("effort_display", {"stronger": "-", "other": "-", "symbol": "=="}),
                "selected_tactics": team_obj.get("tactics", empty_match_tactics()),
                "opponent_tactics": opp_obj.get("tactics", empty_match_tactics()),
            }
        )

        slot_map = canonical_player_names(team_obj["players"], warnings, matchid)
        add_tactic_minutes(
            tactic_minutes,
            team_obj.get("tactics", {}).get("offense"),
            team_obj["players"],
            slot_map,
        )

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
        nba_match_rows: dict[str, dict[str, Any]] = {}
        for idx, player in enumerate(team_obj["players"]):
            if idx not in slot_map:
                continue
            player_key, player_label = slot_map[idx]
            totals = player["stats"]["total"]
            total_secs = sum(int(totals.get(key, 0) or 0) for _, _, key in POSITION_SECONDS)
            row = empty_nba_player_row(matchid, result, tactic_group, player_label)
            row.update(
                {
                    "mins": secs_to_minutes(total_secs),
                    "pts": totals["pts"],
                    "fgm": totals["fgm"],
                    "fga": totals["fga"],
                    "tpm": totals["tpm"],
                    "tpa": totals["tpa"],
                    "ftm": totals["ftm"],
                    "fta": totals["fta"],
                    "or": totals["or"],
                    "dr": totals["dr"],
                    "tr": totals["tr"],
                    "ast": totals["ast"],
                    "to": totals["to"],
                    "stl": totals["stl"],
                    "blk": totals["blk"],
                    "pf": totals["pf"],
                    "pm": totals["+/-"],
                }
            )
            nba_match_rows[player_key] = row
        nba_team_rows.append(build_nba_team_row(matchid, result, tactic_group, team_obj, opp_obj))

        selected_score = 0
        opponent_score = 0

        for ev in game_data["events"]:
            if ev["event_type"] == "shot":
                made = str(ev["shot_result"]) in {"1", "2", "5"}
                shot_type = str(ev["shot_type"])
                shot_result = str(ev["shot_result"])
                shot_type_codes.add(shot_type)
                shot_result_codes.add(shot_result)
                points = shot_points(shot_type)
                clutch = nba_is_clutch(ev.get("gameclock"), selected_score, opponent_score)
                counted_fg_attempt = shot_result != "4"

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
                        nba_row = nba_match_rows.get(shooter_key)
                        if nba_row is not None:
                            range_key = shot_range(shot_type)
                            if range_key == "paint":
                                add_nba_shot_split(nba_row["shots_close"], made)
                            elif range_key == "jump":
                                add_nba_shot_split(nba_row["shots_mid"], made)
                            else:
                                add_nba_shot_split(nba_row["shots_three"], made)
                            defender_idx = normalize_slot(ev["defender"], len(opp_obj["players"]))
                            add_nba_shot_split(nba_row["defended" if defender_idx is not None else "open"], made)
                            assistant_idx = normalize_slot(ev["assistant"], len(team_obj["players"]))
                            add_nba_shot_split(nba_row["assisted" if assistant_idx is not None else "unassisted"], made)
                            if clutch:
                                if counted_fg_attempt:
                                    nba_row["clutch"]["fga"] += 1
                                if made:
                                    nba_row["clutch"]["fgm"] += 1
                                    nba_row["clutch"]["pts"] += points
                                if shot_type.startswith("10") and counted_fg_attempt:
                                    nba_row["clutch"]["tpa"] += 1
                                    if made:
                                        nba_row["clutch"]["tpm"] += 1
                                if assistant_idx is not None and made:
                                    assistant_key = slot_map.get(assistant_idx, ("", ""))[0]
                                    if assistant_key in nba_match_rows:
                                        nba_match_rows[assistant_key]["clutch"]["ast"] += 1
                        if clutch and made:
                            for active_key in active_keys:
                                if active_key in nba_match_rows:
                                    nba_match_rows[active_key]["clutch"]["pm"] += points

                if int(ev["defending_team"]) == side:
                    for player_key in slot_map.values():
                        add_shot_stat(
                            defense_map[player_key[0]]["teamDefOn" if player_key[0] in active_keys else "teamDefOff"],
                            made,
                        )
                        nba_key = player_key[0]
                        if nba_key in nba_match_rows:
                            add_nba_shot_split(nba_match_rows[nba_key]["team_def_on" if nba_key in active_keys else "team_def_off"], made)

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
                        nba_row = nba_match_rows.get(defender_key)
                        if nba_row is not None:
                            add_nba_shot_split(nba_row["defended_total"], made)
                            if range_key == "paint":
                                add_nba_shot_split(nba_row["defended_close"], made)
                            elif range_key == "jump":
                                add_nba_shot_split(nba_row["defended_mid"], made)
                            else:
                                add_nba_shot_split(nba_row["defended_three"], made)

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
                    if clutch and made:
                        for active_key in active_keys:
                            if active_key in nba_match_rows:
                                nba_match_rows[active_key]["clutch"]["pm"] -= points

                if made:
                    if int(ev["attacking_team"]) == side:
                        selected_score += points
                    else:
                        opponent_score += points

                continue

            if ev["event_type"] == "free_throw":
                made = is_nba_made_result(ev.get("shot_result"))
                clutch = nba_is_clutch(ev.get("gameclock"), selected_score, opponent_score)
                if int(ev["attacking_team"]) == side:
                    shooter_idx = normalize_slot(ev["attacker"], len(team_obj["players"]))
                    if clutch and shooter_idx is not None and shooter_idx in slot_map:
                        shooter_key, _ = slot_map[shooter_idx]
                        if shooter_key in nba_match_rows and made:
                            nba_match_rows[shooter_key]["clutch"]["pts"] += 1
                    if clutch and made:
                        for active_key in active_keys:
                            if active_key in nba_match_rows:
                                nba_match_rows[active_key]["clutch"]["pm"] += 1
                    if made:
                        selected_score += 1
                else:
                    if clutch and made:
                        for active_key in active_keys:
                            if active_key in nba_match_rows:
                                nba_match_rows[active_key]["clutch"]["pm"] -= 1
                    if made:
                        opponent_score += 1
                continue

            if ev["event_type"] == "interrupt" and int(ev["attacking_team"]) == side:
                if clutch := nba_is_clutch(ev.get("gameclock"), selected_score, opponent_score):
                    player_idx = normalize_slot(ev.get("attacker"), len(team_obj["players"]))
                    if player_idx is not None and player_idx in slot_map:
                        player_key, _ = slot_map[player_idx]
                        if player_key in nba_match_rows:
                            nba_match_rows[player_key]["clutch"]["to"] += 1
                continue

            if ev["event_type"] == "foul" and int(ev["attacking_team"]) == side and str(ev.get("foul_type")) == "803":
                if clutch := nba_is_clutch(ev.get("gameclock"), selected_score, opponent_score):
                    player_idx = normalize_slot(ev.get("attacker"), len(team_obj["players"]))
                    if player_idx is not None and player_idx in slot_map:
                        player_key, _ = slot_map[player_idx]
                        if player_key in nba_match_rows:
                            nba_match_rows[player_key]["clutch"]["to"] += 1
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

        nba_player_rows.extend(nba_match_rows.values())

    if used_matches == 0:
        return (
            "error",
            {
                "message": "No matches included the selected team after validation.",
                "rows": match_rows,
                "warnings": warnings,
            },
        )

    match_rows.sort(key=lambda row: row.get("start_time", ""), reverse=True)

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
            "selected_team_key": selected_team_key,
            "input_matchids": matchids,
            "return_state": {
                "multi_source": multi_source,
                "national_country_id": national_country_id,
                "national_team_kind": national_team_kind,
                "national_season": national_season,
                "include_friendlies": include_friendlies,
                "team_schedule_team_id": team_schedule_team_id,
                "team_schedule_season": team_schedule_season,
                "team_schedule_limit": team_schedule_limit,
                "team_schedule_types": list(team_schedule_types or DEFAULT_TEAM_SCHEDULE_TYPES),
            },
            "tactic_minutes": finalize_tactic_minutes(tactic_minutes),
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
            "nba_dashboard": {
                "players": nba_player_rows,
                "team_rows": nba_team_rows,
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


@app.post("/u21-analyzer-unlock")
def u21_analyzer_unlock() -> tuple[Any, int] | Any:
    payload = request.get_json(silent=True) or {}
    submitted_password = str(payload.get("password", ""))
    expected_password = os.environ.get("U21_ANALYZER_PASSWORD", "")
    if expected_password and hmac.compare_digest(submitted_password, expected_password):
        return jsonify({"ok": True})
    return jsonify({"error": "Analyzer password is incorrect or not configured."}), 400


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
    team_schedule_team_id: str,
    team_schedule_season: str,
    team_schedule_limit: str,
    team_schedule_types: list[str],
    bb_site_password: str,
    estimator_country_id: str,
    estimator_season: str,
    estimator_nt_strength: str,
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
                team_schedule_team_id=team_schedule_team_id,
                team_schedule_season=team_schedule_season,
                team_schedule_limit=team_schedule_limit,
                team_schedule_types=team_schedule_types,
                bb_site_password=bb_site_password,
                estimator_country_id=estimator_country_id,
                estimator_season=estimator_season,
                estimator_nt_strength=estimator_nt_strength,
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
    team_schedule_team_id = request.form.get("team_schedule_team_id", "").strip()
    team_schedule_season = request.form.get("team_schedule_season", "").strip()
    team_schedule_limit = request.form.get("team_schedule_limit", "10").strip() or "10"
    team_schedule_types = request.form.getlist("team_schedule_types") or DEFAULT_TEAM_SCHEDULE_TYPES
    bb_site_password = request.form.get("bb_site_password", "").strip()
    estimator_country_id = request.form.get("estimator_country_id", "").strip()
    estimator_season = request.form.get("estimator_season", "").strip()
    estimator_nt_strength = request.form.get("estimator_nt_strength", "weak").strip()
    if estimator_nt_strength not in {"weak", "strong"}:
        estimator_nt_strength = "weak"
    from_multi = request.form.get("from_multi") == "1"

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
            team_schedule_team_id=team_schedule_team_id,
            team_schedule_season=team_schedule_season,
            team_schedule_limit=team_schedule_limit,
            team_schedule_types=team_schedule_types,
            bb_site_password=bb_site_password if keep_password else "",
            estimator_country_id=estimator_country_id,
            estimator_season=estimator_season,
            estimator_nt_strength=estimator_nt_strength,
        )

    if not username or not password:
        return form_error("Username and password are required.", 400)

    if mode == "u21_training":
        if not bb_site_password:
            return form_error("BB site password is required for U21 squad analysis.", 400)
        if not estimator_country_id:
            return form_error("Choose a country U21 team before generating the estimator.", 400)
        try:
            payload = build_u21_training_report(
                username=username,
                password=password,
                site_password=bb_site_password,
                country_id=estimator_country_id,
                season=estimator_season,
                nt_strength=estimator_nt_strength,
            )
        except Exception as exc:
            return form_error(f"Failed to build U21 squad analysis: {exc}", 400, keep_password=False)

        return render_template_string(U21_TRAINING_REPORT_HTML, report=payload)

    if mode == "multi":
        source_warnings: list[str] = []
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
        elif multi_source == "team":
            if not team_schedule_team_id:
                return form_error("Enter a team ID before generating the report.", 400)
            try:
                multi_matchids, source_warnings = fetch_team_schedule_matchids(
                    username=username,
                    password=password,
                    team_id=team_schedule_team_id,
                    season=team_schedule_season,
                    limit=team_schedule_limit,
                    selected_types=team_schedule_types,
                )
            except Exception as exc:
                return form_error(f"Could not load team schedule: {exc}", 400, keep_password=False)

        if not multi_matchids:
            if multi_source == "national":
                return form_error("No matches were found for that national team schedule.", 400)
            if multi_source == "team":
                return form_error("No completed matches were found for that team schedule and filter.", 400)
            return form_error("Enter at least one match ID for multi-match mode.", 400)

        status, payload = aggregate_multi_match_report(
            multi_matchids,
            username,
            password,
            selected_team_key=selected_team_key,
            multi_source=multi_source,
            national_country_id=national_country_id,
            national_team_kind=national_team_kind,
            national_season=national_season,
            include_friendlies=include_friendlies,
            team_schedule_team_id=team_schedule_team_id,
            team_schedule_season=team_schedule_season,
            team_schedule_limit=team_schedule_limit,
            team_schedule_types=team_schedule_types,
        )

        if status == "choose_team":
            return render_template_string(
                TEAM_CHOICE_HTML,
                username=username,
                password=password,
                matchids=multi_matchids,
                candidates=payload,
                multi_source=multi_source,
                national_country_id=national_country_id,
                national_team_kind=national_team_kind,
                national_season=national_season,
                include_friendlies=include_friendlies,
                team_schedule_team_id=team_schedule_team_id,
                team_schedule_season=team_schedule_season,
                team_schedule_limit=team_schedule_limit,
                team_schedule_types=team_schedule_types,
            )

        if status == "error":
            message = payload["message"]
            extra_warnings = payload.get("warnings", [])
            if extra_warnings:
                message = f'{message} {" | ".join(extra_warnings)}'
            return form_error(message, 400, keep_password=False)

        payload["warnings"].extend(source_warnings)
        return render_template_string(
            MULTI_REPORT_HTML,
            report_json=payload,
            username=username,
            password=password,
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
        password=password,
        from_multi=from_multi,
        multi_matchids=multi_matchids,
        selected_team_key=selected_team_key or "",
        multi_source=multi_source,
        national_country_id=national_country_id,
        national_team_kind=national_team_kind,
        national_season=national_season,
        include_friendlies=include_friendlies,
        team_schedule_team_id=team_schedule_team_id,
        team_schedule_season=team_schedule_season,
        team_schedule_limit=team_schedule_limit,
        team_schedule_types=team_schedule_types,
        court_image_url=get_court_image_data_url(),
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
