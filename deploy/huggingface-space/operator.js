(() => {
  'use strict';

  const button = document.querySelector('a.button.primary');
  if (!button) return;

  button.removeAttribute('href');
  button.removeAttribute('target');
  button.textContent = 'Scan now';
  button.setAttribute('role', 'button');
  button.setAttribute('aria-label', 'Start a fresh DropFinder scan');

  function token() {
    let value = sessionStorage.getItem('dropfinder-operator-token') || '';
    if (!value) {
      value = window.prompt('Enter the DropFinder operator token. It stays only in this browser session.') || '';
      if (value) sessionStorage.setItem('dropfinder-operator-token', value);
    }
    return value;
  }

  async function refreshState() {
    try {
      const response = await fetch('/api/scan-state', { cache: 'no-store' });
      if (!response.ok) return;
      const state = await response.json();
      button.textContent = state.running ? 'Scanning…' : 'Scan now';
      button.setAttribute('aria-busy', state.running ? 'true' : 'false');
    } catch (_) {
      button.textContent = 'Scan now';
    }
  }

  button.addEventListener('click', async event => {
    event.preventDefault();
    const operatorToken = token();
    if (!operatorToken) return;
    button.textContent = 'Starting…';
    try {
      const response = await fetch('/api/scan', {
        method: 'POST',
        headers: { Authorization: `Bearer ${operatorToken}` },
      });
      if (response.status === 401) {
        sessionStorage.removeItem('dropfinder-operator-token');
        throw new Error('The operator token was rejected. Reopen Scan now and enter the current token.');
      }
      if (!response.ok) throw new Error(`Scan request failed with HTTP ${response.status}.`);
      const result = await response.json();
      button.textContent = result.accepted === false ? 'Scanning…' : 'Started';
      window.setTimeout(refreshState, 1200);
    } catch (error) {
      button.textContent = 'Scan now';
      window.alert(error instanceof Error ? error.message : 'The scan could not be started.');
    }
  });

  refreshState();
  window.setInterval(refreshState, 15000);
})();
