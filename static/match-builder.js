/* One active source, native radio keyboard controls, and a readable report preview. */
(() => {
  const form = document.getElementById('match-builder-form');
  if (!form) return;
  const field = name => form.elements.namedItem(name);
  const sourceInputs = [...form.querySelectorAll('[name="source_mode"]')];
  const manualCountry = document.getElementById('manual-country-toggle');
  const matchIds = field('match_ids');
  const count = document.getElementById('match-id-count');
  const selectionTitle = document.getElementById('selection-title');
  const selectionDetail = document.getElementById('selection-detail');
  const button = document.getElementById('build-report');
  const status = document.getElementById('build-status');
  const selectedMode = () => sourceInputs.find(input => input.checked)?.value || 'matches';
  const stateInputs = [...form.querySelectorAll('input:not([type="hidden"]),select,textarea')];
  const stateKey = input => input.id || `${input.name}:${input.value}`;
  function restoreSelection() {
    const saved = history.state?.nikaMatchSelection;
    if (!saved) return;
    for (const input of stateInputs) {
      const value = saved[stateKey(input)];
      if (!value) continue;
      input.value = value.value;
      if (input.type === 'radio' || input.type === 'checkbox') input.checked = value.checked;
    }
  }
  function update() {
    const mode = selectedMode();
    for (const panel of form.querySelectorAll('[data-source-panel]')) {
      panel.hidden = panel.dataset.sourcePanel !== mode;
      panel.disabled = panel.hidden;
    }
    const schedule = form.querySelector('[data-schedule-options]');
    schedule.hidden = mode === 'matches';
    schedule.disabled = schedule.hidden;
    const useCode = manualCountry.checked;
    document.getElementById('country-code-field').hidden = !useCode;
    document.getElementById('country-list-field').hidden = useCode;
    field('national_country_id').disabled = useCode;
    field('national_other_code').disabled = !useCode;
    field('national_country_id').required = mode === 'national' && !useCode;
    field('national_other_code').required = mode === 'national' && useCode;
    matchIds.required = mode === 'matches';
    field('schedule_team_id').required = mode === 'club';
    field('count').required = mode !== 'matches';
    const ids = [...new Set(matchIds.value.trim().split(/[\s,]+/).filter(Boolean))];
    count.textContent = ids.length ? `${ids.length} / 30 games` : '';
    count.classList.toggle('is-over-limit', ids.length > 30);
    matchIds.setCustomValidity(mode === 'matches' && ids.length > 30 ? 'Choose up to 30 different matches.' : '');
    if (mode === 'matches') {
      selectionTitle.textContent = ids.length ? `${ids.length} ${ids.length === 1 ? 'match' : 'matches'} selected` : 'Choose your matches';
      selectionDetail.textContent = ids.length ? 'One combined team report.' : 'Paste match IDs to get started.';
    } else {
      const country = useCode ? field('national_other_code').value.trim().toUpperCase() : field('national_country_id').value ? field('national_country_id').selectedOptions[0].textContent.trim() : '';
      selectionTitle.textContent = mode === 'club' ? (field('schedule_team_id').value.trim() ? 'Club schedule' : 'Choose your club') : country ? `${country} · ${field('national_kind').value === 'SeniorNationalTeam' ? 'Senior' : 'U21'}` : 'Choose your national team';
      const season = field('season').value.trim();
      selectionDetail.textContent = `Last ${field('count').value || '10'} completed games · ${season ? 'Season ' + season : 'Current season'}`;
    }
    const dataOptions = [...form.querySelectorAll('.included-data input[type="checkbox"]')];
    for (const item of form.querySelectorAll('.report-includes li')) item.hidden = false;
    if (!dataOptions[0].checked) form.querySelectorAll('.report-includes li')[2].hidden = true;
  }
  form.addEventListener('input', update);
  form.addEventListener('change', update);
  form.addEventListener('submit', () => {
    // Keep the selection on this history entry, including when no-store causes
    // Back to load a fresh document whose inactive fields start disabled.
    const selection = Object.fromEntries(stateInputs.map(input => [stateKey(input), {value:input.value, checked:input.checked}]));
    history.replaceState({...history.state, nikaMatchSelection:selection}, '');
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    button.querySelector('span').textContent = 'Building report…';
    status.textContent = 'Loading your games. This may take a moment.';
  });
  // Restore the button after browser Back restores a submitted form from memory.
  window.addEventListener('pageshow', () => {
    restoreSelection();
    button.disabled = form.dataset.connected !== 'true';
    button.removeAttribute('aria-busy');
    button.querySelector('span').textContent = 'Build report';
    status.textContent = form.dataset.connected === 'true' ? 'Your selected games, combined into one report.' : 'Connect your account above to continue.';
    update();
  });
  restoreSelection();
  update();
  const error = document.getElementById('builder-error');
  if (error) error.focus();
})();
