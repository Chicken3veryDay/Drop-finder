(() => {
  'use strict';

  const button = document.querySelector('#scanButton');
  if (!button) return;

  button.removeAttribute('href');
  button.removeAttribute('target');
  button.textContent = 'Scan now';
  button.setAttribute('role', 'button');
  button.setAttribute('aria-label', 'Start a fresh DropFinder scan');

  let operatorStartedScan = false;
  let observedRunning = false;

  function operatorToken() {
    let value = sessionStorage.getItem('dropfinder-operator-token') || '';
    if (!value) {
      value = window.prompt('Enter the DropFinder operator token. It remains only in this browser session.') || '';
      if (value) sessionStorage.setItem('dropfinder-operator-token', value);
    }
    return value;
  }

  async function refreshState() {
    try {
      const response = await fetch('/api/scan-state', { cache: 'no-store' });
      if (!response.ok) return;
      const state = await response.json();
      const running = Boolean(state.running);
      button.textContent = running ? 'Scanning…' : 'Scan now';
      button.setAttribute('aria-busy', running ? 'true' : 'false');
      observedRunning = observedRunning || running;
      if (operatorStartedScan && observedRunning && !running && state.last_success_at && !state.last_error) {
        operatorStartedScan = false;
        window.location.reload();
      }
    } catch (_) {
      button.textContent = 'Scan now';
      button.setAttribute('aria-busy', 'false');
    }
  }

  button.addEventListener('click', async event => {
    event.preventDefault();
    const token = operatorToken();
    if (!token) return;

    button.textContent = 'Starting…';
    button.setAttribute('aria-busy', 'true');
    try {
      const response = await fetch('/api/scan', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (response.status === 401) {
        sessionStorage.removeItem('dropfinder-operator-token');
        throw new Error('The operator token was rejected. Tap Scan now and enter the current token.');
      }
      if (!response.ok) throw new Error(`Scan request failed with HTTP ${response.status}.`);
      const result = await response.json();
      operatorStartedScan = true;
      observedRunning = result.accepted === false;
      button.textContent = result.accepted === false ? 'Scanning…' : 'Started';
      window.setTimeout(refreshState, 900);
    } catch (error) {
      operatorStartedScan = false;
      button.textContent = 'Scan now';
      button.setAttribute('aria-busy', 'false');
      window.alert(error instanceof Error ? error.message : 'The scan could not be started.');
    }
  });

  refreshState();
  window.setInterval(refreshState, 5000);
})();
