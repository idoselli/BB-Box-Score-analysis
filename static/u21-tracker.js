const filters = document.getElementById("tracker-filters");
filters?.addEventListener("change", () => {
  if (filters.elements.countryId.value === filters.elements.compareCountryId.value) {
    filters.elements.compareCountryId.value = "";
  }
  filters.requestSubmit();
});

const chart = document.getElementById("chart");
const numberFormat = new Intl.NumberFormat("en-US");

if (chart) initializeChart();

function initializeChart() {
  const { season, squads, positions, weeks } = JSON.parse(document.getElementById("tracker-data").textContent);
  const metric = document.getElementById("metric");
  const picker = document.querySelector(".tracker-picker");
  const legend = document.getElementById("chart-legend");
  const count = document.getElementById("tracker-selection-count");
  const checkboxes = document.querySelectorAll("input[data-player-key]");
  const storageKey = `nika-u21-tracker-${season}`;
  const preferences = readPreferences(storageKey);
  const selected = new Set();
  const players = squads.flatMap((squad, team) => squad.players.map(player => ({
    ...player,
    key: `${squad.countryId}/${player.playerId}`,
    positionCode: positions[player.position] || "",
    team,
    teamName: squad.countryName,
  })));

  if (Array.from(metric.options).some(option => option.value === preferences.metric)) {
    metric.value = preferences.metric;
  }
  squads.forEach((squad, team) => {
    const roster = players.filter(player => player.team === team);
    const saved = preferences.squads?.[squad.countryId];
    const picks = Array.isArray(saved) ? new Set(saved) : new Set(
      [...roster]
        .sort((a, b) => (b.points.at(-1).dmi ?? -Infinity) - (a.points.at(-1).dmi ?? -Infinity))
        .slice(0, 3)
        .map(player => player.playerId)
    );
    roster.filter(player => picks.has(player.playerId)).forEach(player => selected.add(player.key));
  });

  function savePreferences() {
    preferences.metric = metric.value;
    preferences.squads ??= {};
    squads.forEach((squad, team) => {
      preferences.squads[squad.countryId] = players
        .filter(player => player.team === team && selected.has(player.key))
        .map(player => player.playerId);
    });
    try {
      sessionStorage.setItem(storageKey, JSON.stringify(preferences));
    } catch {
      // Selection still works when browser storage is unavailable.
    }
  }

  function draw() {
    count.textContent = `${selected.size} selected`;
    for (const checkbox of checkboxes) {
      checkbox.checked = selected.has(checkbox.dataset.playerKey);
      checkbox.closest("tr")?.classList.toggle("is-selected", checkbox.checked);
    }
    const plotted = players
      .filter(player => selected.has(player.key))
      .map(player => ({
        ...player,
        points: player.points.filter(point => Number.isFinite(point[metric.value])),
      }))
      .filter(player => player.points.length);

    legend.replaceChildren();
    if (!plotted.length) {
      chart.textContent = selected.size ? "No values for this metric." : "Select players to plot.";
      return;
    }
    chart.replaceChildren(drawPlot(chart.clientWidth, weeks, metric.value, metric.selectedOptions[0].text, plotted));
    for (const player of plotted) {
      const item = document.createElement("li");
      const symbol = document.createElement("i");
      symbol.className = "tracker-legend-symbol";
      symbol.dataset.position = player.positionCode;
      symbol.dataset.team = player.team;
      symbol.setAttribute("aria-hidden", "true");
      const qualifier = [player.positionCode, squads.length > 1 ? player.teamName : ""].filter(Boolean).join(" · ");
      item.append(symbol, document.createTextNode(qualifier ? `${player.name} · ${qualifier}` : player.name));
      legend.append(item);
    }
  }

  function applySelection() {
    savePreferences();
    draw();
  }

  for (const checkbox of checkboxes) {
    checkbox.addEventListener("change", () => {
      const key = checkbox.dataset.playerKey;
      if (checkbox.checked) selected.add(key);
      else selected.delete(key);
      applySelection();
    });
  }
  picker.querySelector("[data-selection=all]").addEventListener("click", () => {
    players.forEach(player => selected.add(player.key));
    applySelection();
  });
  picker.querySelector("[data-selection=clear]").addEventListener("click", () => {
    selected.clear();
    applySelection();
  });
  picker.addEventListener("keydown", event => {
    if (event.key !== "Escape") return;
    picker.open = false;
    picker.querySelector("summary").focus();
  });
  document.addEventListener("click", event => {
    if (picker.open && !picker.contains(event.target)) picker.open = false;
  });
  metric.addEventListener("change", applySelection);
  window.addEventListener("resize", draw);
  draw();
}

function readPreferences(key) {
  try {
    return JSON.parse(sessionStorage.getItem(key)) || {};
  } catch {
    return {};
  }
}

function svg(tag, attributes, label) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, String(value));
  if (label !== undefined) node.textContent = label;
  return node;
}

function drawPlot(containerWidth, weeks, metric, metricLabel, players) {
  const values = players.flatMap(player => player.points.map(point => point[metric]));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const padding = max === min ? Math.max(1, max * .05) : (max - min) * .08;
  const interval = (max - min + 2 * padding) / 4;
  const magnitude = 10 ** Math.floor(Math.log10(interval));
  const step = Math.max(1, magnitude * [1, 2, 5, 10].find(multiplier => multiplier * magnitude >= interval));
  const low = Math.max(0, Math.floor((min - padding) / step) * step);
  const high = Math.ceil((max + padding) / step) * step;
  const width = Math.max(containerWidth, 260);
  const height = 286;
  const left = Math.max(48, numberFormat.format(high).length * 7 + 13);
  const right = width - 25;
  const top = 18;
  const bottom = height - 34;
  const firstWeek = weeks[0];
  const lastWeek = weeks.at(-1);
  const x = week => weeks.length === 1 ? (left + right) / 2 : left + (week - firstWeek) * (right - left) / (lastWeek - firstWeek);
  const y = value => bottom - (value - low) * (bottom - top) / (high - low);
  const canvas = svg("svg", {
    viewBox: `0 0 ${width} ${height}`,
    role: "img",
    "aria-label": `${metricLabel} by week for ${players.length} ${players.length === 1 ? "player" : "players"}`,
  });

  for (let value = low; value <= high; value += step) {
    canvas.append(
      svg("line", { x1: left, y1: y(value), x2: right, y2: y(value), class: "tracker-grid-line" }),
      svg("text", { x: left - 8, y: y(value) + 4, "text-anchor": "end", class: "tracker-axis-label" }, numberFormat.format(value))
    );
  }
  const weekStride = Math.max(1, Math.ceil(weeks.length / Math.floor((right - left) / 38)));
  weeks.forEach((week, index) => {
    const isTick = index % weekStride === 0 && weeks.length - 1 - index >= weekStride / 2;
    if (isTick || week === lastWeek) {
      canvas.append(svg("text", { x: x(week), y: height - 12, "text-anchor": "middle", class: "tracker-axis-label" }, `W${week}`));
    }
  });

  for (const player of players) {
    const series = svg("g", { class: "tracker-series", "data-position": player.positionCode, "data-team": player.team, "data-player-key": player.key });
    const illustrative = point => metric === "dmi" && point.syntheticDmi;
    player.points.forEach((point, index) => {
      const previous = player.points[index - 1];
      const cx = x(point.week);
      const cy = y(point[metric]);
      if (previous && point.week - previous.week === 1) {
        series.append(svg("line", {
          x1: x(previous.week), y1: y(previous[metric]), x2: cx, y2: cy,
          class: illustrative(previous) || illustrative(point) ? "is-illustrative" : "",
        }));
      }
      const markerClass = illustrative(point) ? "tracker-point is-illustrative" : "tracker-point";
      const marker = player.team === 1
        ? svg("rect", { x: cx - 4, y: cy - 4, width: 8, height: 8, transform: `rotate(45 ${cx} ${cy})`, class: markerClass })
        : svg("circle", { cx, cy, r: 4.8, class: markerClass });
      const value = numberFormat.format(point[metric]);
      marker.append(svg("title", {}, `${player.name} (${player.teamName}) · W${point.week} · ${value}${illustrative(point) ? " (illustrative)" : ""}`));
      series.append(marker);
    });
    canvas.append(series);
  }
  return canvas;
}
