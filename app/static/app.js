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

// ── Device selector ───────────────────────────────────────────

/**
 * Populate a <select> element with devices fetched from /devices API.
 * Auto-selects the device stored in localStorage, or the first device.
 * @param {string} selectId  The id of the <select> element to populate
 */
async function loadDeviceSelector(selectId) {
  const sel = document.getElementById(selectId);
  if (!sel) return;

  try {
    const resp = await api('/devices');
    const devices = resp.data || [];
    sel.innerHTML = '';

    if (devices.length === 0) {
      const opt = document.createElement('option');
      opt.value = '';
      opt.textContent = '未找到设备';
      sel.appendChild(opt);
      return;
    }

    const saved = localStorage.getItem('dot_selected_device');

    devices.forEach(dev => {
      const opt = document.createElement('option');
      opt.value = dev.deviceId || dev.device_id || dev.id || '';
      const alias = dev.alias || dev.name || '';
      opt.textContent = alias ? alias + ' (' + opt.value + ')' : opt.value;
      sel.appendChild(opt);
    });

    // Restore previous selection if still available
    if (saved && [...sel.options].some(o => o.value === saved)) {
      sel.value = saved;
    }

    // Persist selection on change
    sel.addEventListener('change', () => {
      localStorage.setItem('dot_selected_device', sel.value);
    });

    // Store the initial selection
    localStorage.setItem('dot_selected_device', sel.value);
  } catch (e) {
    sel.innerHTML = '<option value="">加载设备失败</option>';
    console.error('loadDeviceSelector:', e);
  }
}

/**
 * Get the currently selected device_id from a selector.
 * @param {string} selectId
 * @returns {string|undefined}
 */
function getSelectedDevice(selectId) {
  const sel = document.getElementById(selectId);
  return sel && sel.value ? sel.value : undefined;
}
