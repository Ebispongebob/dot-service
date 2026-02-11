/**
 * Dot Service — Frontend utility functions
 * Shared across all pages via base.html
 */

// ── API helper ────────────────────────────────────────────────

/**
 * Fetch wrapper that talks to the Dot Service backend.
 * Automatically parses JSON and handles errors.
 */
async function api(path, opts = {}) {
  const resp = await fetch(path, opts);
  if (!resp.ok) {
    let msg = resp.statusText;
    try {
      const body = await resp.json();
      msg = body.detail || body.message || msg;
    } catch (_) {}
    throw new Error(msg);
  }
  return resp.json();
}

// ── Toast notifications ───────────────────────────────────────

/**
 * Show a toast notification.
 * @param {string} message
 * @param {'success'|'error'|'warning'} type
 * @param {number} duration  ms before auto-dismiss (default 3500)
 */
function toast(message, type = 'success', duration = 3500) {
  const container = document.getElementById('toastContainer');
  if (!container) return;

  const el = document.createElement('div');
  el.className = 'toast ' + type;

  // Icon
  const icons = { success: '\u2713', error: '\u2717', warning: '\u26A0' };
  el.innerHTML = '<strong>' + (icons[type] || '') + '</strong> ' + esc(message);

  container.appendChild(el);

  setTimeout(() => {
    el.classList.add('fade-out');
    el.addEventListener('animationend', () => el.remove());
  }, duration);
}

// ── HTML escaping ─────────────────────────────────────────────

function esc(str) {
  if (str == null) return '';
  const d = document.createElement('div');
  d.textContent = String(str);
  return d.innerHTML;
}
