const output = document.getElementById('output');
const input = document.getElementById('input');
const status = document.getElementById('status');
const indicator = document.getElementById('indicator');
const syncRatio = document.getElementById('sync-ratio');
const modelSelect = document.getElementById('model-select');

let ws;
let msgCount = 0;
let processing = false;
let currentModel = null;
let currentProvider = null;

// Fetch available models and populate the dropdown
async function loadModels() {
  try {
    const res = await fetch('/api/models');
    const providers = await res.json();
    modelSelect.innerHTML = '';
    providers.forEach(prov => {
      const group = document.createElement('optgroup');
      group.label = prov.label;
      prov.models.forEach(m => {
        const opt = document.createElement('option');
        opt.value = JSON.stringify({ model: m.id, provider: prov.id });
        opt.textContent = m.label;
        group.appendChild(opt);
      });
      modelSelect.appendChild(group);
    });
    // Select first option as default
    if (modelSelect.options.length > 0) {
      const first = JSON.parse(modelSelect.value);
      currentModel = first.model;
      currentProvider = first.provider;
    }
  } catch (e) {
    modelSelect.innerHTML = '<option value="">UNAVAILABLE</option>';
  }
}

modelSelect.addEventListener('change', () => {
  if (!modelSelect.value) return;
  const { model, provider } = JSON.parse(modelSelect.value);
  currentModel = model;
  currentProvider = provider;
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'config', model, provider }));
  }
});

function connect() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws`);

  ws.onopen = () => {
    setOnline(true);
    // Send current model selection on connect
    if (currentModel) {
      ws.send(JSON.stringify({ type: 'config', model: currentModel, provider: currentProvider }));
    }
  };

  ws.onmessage = (e) => {
    const data = JSON.parse(e.data);

    // "PROCESSING..." is a transient status — show it as a pulsing indicator
    if (data.type === 'system' && data.content === 'PROCESSING...') {
      setProcessing(true);
      return;
    }

    // Any other message clears the processing state
    if (processing) {
      setProcessing(false);
    }

    appendMessage(data.type, data.content);
    updateSync();
  };

  ws.onclose = () => {
    setOnline(false);
    setProcessing(false);
    appendMessage('system', 'LINK SEVERED — RECONNECTING...');
    setTimeout(connect, 3000);
  };

  ws.onerror = () => {
    ws.close();
  };
}

function appendMessage(type, content) {
  const el = document.createElement('div');
  el.className = `msg ${type}`;
  el.textContent = content;
  output.appendChild(el);
  output.scrollTop = output.scrollHeight;
  msgCount++;
}

function updateSync() {
  const ratio = Math.min(99.99, msgCount * 7.77).toFixed(2);
  syncRatio.textContent = ratio.padStart(6, '0');
}

function setOnline(on) {
  status.textContent = on ? 'ONLINE' : 'OFFLINE';
  status.classList.toggle('online', on);
  indicator.classList.toggle('active', on);
}

function setProcessing(on) {
  processing = on;
  input.disabled = on;

  // Remove any previous processing message
  const prev = output.querySelector('.msg.system.processing');
  if (prev) prev.remove();

  if (on) {
    const el = document.createElement('div');
    el.className = 'msg system processing';
    el.textContent = 'PROCESSING...';
    output.appendChild(el);
    output.scrollTop = output.scrollHeight;
    input.placeholder = 'AWAITING RESPONSE...';
  } else {
    input.placeholder = '';
    input.focus();
  }
}

input.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && input.value.trim() && !processing) {
    const msg = input.value.trim();
    appendMessage('user', msg);
    ws.send(JSON.stringify({ content: msg }));
    input.value = '';
  }
});

loadModels().then(connect);
