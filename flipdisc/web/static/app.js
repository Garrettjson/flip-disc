async function fetchJSON(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${path} failed: ${res.status}`);
  return res.json();
}

async function postJSON(path, payload) {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: payload ? JSON.stringify(payload) : null,
  });
  if (!res.ok) throw new Error(`${path} failed: ${res.status}`);
  return res.json();
}

// UI elements
const runningEl = document.getElementById('running');
const connectedEl = document.getElementById('connected');
const fpsEl = document.getElementById('fps');
const presentedEl = document.getElementById('presented');
const sizeEl = document.getElementById('size');
const bufferEl = document.getElementById('buffer');
const animSelect = document.getElementById('anim');
const startBtn = document.getElementById('start');
const stopBtn = document.getElementById('stop');
const fpsInput = document.getElementById('fps-input');
const setFpsBtn = document.getElementById('set-fps');
const refreshBtn = document.getElementById('refresh');
const canvas = document.getElementById('preview');
const ctx = canvas.getContext('2d');

function drawBits(bits, width, height) {
  if (!bits || bits.length === 0) {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    return;
  }
  const scaleX = canvas.width / width;
  const scaleY = canvas.height / height;
  ctx.fillStyle = 'black';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = 'white';
  for (let y = 0; y < height; y++) {
    const row = bits[y];
    for (let x = 0; x < width; x++) {
      if (row[x]) {
        ctx.fillRect(Math.floor(x * scaleX), Math.floor(y * scaleY), Math.ceil(scaleX), Math.ceil(scaleY));
      }
    }
  }
}

async function loadAnimations() {
  const data = await fetchJSON('/animations');
  animSelect.innerHTML = '';
  (data.animations || []).forEach(name => {
    const opt = document.createElement('option');
    opt.value = name; opt.textContent = name;
    animSelect.appendChild(opt);
  });
}

async function refreshStatus() {
  const s = await fetchJSON('/status');
  runningEl.textContent = s.hardware.running ? 'Yes' : 'No';
  connectedEl.textContent = s.hardware.connected ? 'Yes' : 'No';
  fpsEl.textContent = s.config.refresh_rate;
  presentedEl.textContent = s.hardware.frames_presented;
  sizeEl.textContent = `${s.config.width} x ${s.config.height}`;
  const b = s.hardware.buffer;
  bufferEl.textContent = `${b.size}/${b.max_size} (free ${b.free})`;
}

async function refreshPreview() {
  try {
    const p = await fetchJSON('/preview');
    drawBits(p.bits, p.width, p.height);
  } catch (e) {
    // ignore transient errors
  }
}

async function startSelected() {
  const name = animSelect.value;
  if (!name) return;
  await postJSON(`/anim/${encodeURIComponent(name)}`);
  await refreshStatus();
}
async function stopAnimation() {
  await postJSON('/animations/stop');
  await refreshStatus();
}
// Clear/reset removed from UI; only start/stop remain.
async function setFps() {
  const v = parseFloat(fpsInput.value || '0');
  if (v > 0) {
    await postJSON(`/fps?new_fps=${encodeURIComponent(v)}`);
    await refreshStatus();
  }
}

startBtn.addEventListener('click', startSelected);
setFpsBtn.addEventListener('click', setFps);
refreshBtn.addEventListener('click', refreshStatus);
stopBtn.addEventListener('click', stopAnimation);

// Init
(async function init() {
  await loadAnimations();
  await refreshStatus();
  await refreshPreview();
  setInterval(refreshStatus, 2000);
  setInterval(refreshPreview, 500);
})();
