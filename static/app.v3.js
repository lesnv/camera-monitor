console.log('✅ Загружена App v3.0');
const API = '';
let currentPi = null;

// Безопасная функция: не упадёт, если элемент не найден
function safeSet(id, html) {
  console.log(`🔧 safeSet: id="${id}", html length=${html?.length || 0}`);
  const el = document.getElementById(id);
  if (el) el.innerHTML = html;
}

document.addEventListener('DOMContentLoaded', () => {
  loadPiList();
  initTabs();
});

function initTabs() {
  document.querySelectorAll('#view-detail .tab').forEach(tab => {
    tab.onclick = function() {
      // Убираем активный класс со всех
      document.querySelectorAll('#view-detail .tab').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('#view-detail .tab-content').forEach(c => c.classList.remove('active'));
      // Добавляем текущему
      this.classList.add('active');
      const tabName = this.dataset.tab;
      const content = document.getElementById('tab-' + tabName);
      if (content) {
        content.classList.add('active');
        // Загружаем контент при необходимости
        if (tabName === 'events' && currentPi) loadEvents(currentPi.id);
        if (tabName === 'gallery' && currentPi) loadGallery(currentPi.id);
      }
    };
  });
}

async function loadPiList() {
  safeSet('view-list', '');
  const viewList = document.getElementById('view-list');
  const viewDetail = document.getElementById('view-detail');
  if (viewList) viewList.classList.remove('hidden');
  if (viewDetail) viewDetail.classList.add('hidden');
  
  safeSet('pi-list', '<p class="card">Загрузка...</p>');
  
  try {
    const res = await fetch(`${API}/api/orangepi`);
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const pis = await res.json();
    
    if (!pis || !pis.length) {
      safeSet('pi-list', '<p class="card">Нет устройств</p>');
      return;
    }
    
    const html = pis.map(p => {
      const isOn = p.last_seen && (new Date().getTime() - new Date(p.last_seen).getTime()) < 120000;
      return `<div class="card" onclick="openPi(${p.id})">
        <div style="display:flex;justify-content:space-between">
          <h3>${p.name || 'Unknown'}</h3>
          <span class="badge ${isOn ? 'online' : 'offline'}">${isOn ? '🟢' : '🔴'}</span>
        </div>
        <p style="font-size:0.85em;color:#94a3b8">🌐 ${p.ip || '—'} | 🌡️ ${p.temp || '—'}°C</p>
        <p style="font-size:0.85em">CPU: ${p.cpu || 0}% | RAM: ${p.ram || 0}%</p>
      </div>`;
    }).join('');
    safeSet('pi-list', html);
  } catch (e) {
    safeSet('pi-list', '<p class="card" style="color:var(--danger)">Ошибка: ' + e.message + '</p>');
    console.error('loadPiList:', e);
  }
}

async function openPi(id) {
  currentPi = null;
  const viewList = document.getElementById('view-list');
  const viewDetail = document.getElementById('view-detail');
  if (viewList) viewList.classList.add('hidden');
  if (viewDetail) viewDetail.classList.remove('hidden');
  
  // Сброс вкладок
  document.querySelectorAll('#view-detail .tab, #view-detail .tab-content').forEach(el => el?.classList.remove('active'));
  const firstTab = document.querySelector('#view-detail .tab[data-tab="overview"]');
  const firstContent = document.getElementById('tab-overview');
  if (firstTab) firstTab.classList.add('active');
  if (firstContent) firstContent.classList.add('active');
  
  try {
    const res = await fetch(`${API}/api/orangepi/${id}`);
    if (!res.ok) throw new Error('HTTP ' + res.status);
    currentPi = await res.json();
    safeSet('detail-title', currentPi.name || 'Unknown');
    renderOverview(currentPi);
    renderCameras(currentPi);
  } catch (e) {
    safeSet('detail-title', 'Ошибка: ' + e.message);
    console.error('openPi:', e);
  }
}

function renderOverview(pi) {
  if (!pi) return;
  let lastSeenStr = '—';
  if (pi.last_seen) {
    try {
      const d = new Date(pi.last_seen);
      if (!isNaN(d.getTime())) lastSeenStr = d.toLocaleString('ru-RU');
    } catch (e) { lastSeenStr = 'Invalid date'; }
  }
  const isOn = pi.last_seen && (new Date().getTime() - new Date(pi.last_seen).getTime()) < 120000;
  const html = `<div class="card"><h3>📊 Сводка</h3>
    <p>IP: ${pi.ip || '—'} | 🌡️ ${pi.temp || '—'}°C</p>
    <p>Последний пульс: ${lastSeenStr} <span class="badge ${isOn ? 'online' : 'offline'}">${isOn ? '🟢' : '🔴'}</span></p>
    <div style="display:flex;gap:8px;margin-top:12px">
      <button class="btn" onclick="checkStatus(${pi.id})">🔍 Ping</button>
      <button class="btn gray" onclick="rebootPi(${pi.id})">🔄 Перезагрузить</button>
    </div>
    <div id="status-result" style="margin-top:8px;color:#94a3b8"></div></div>`;
  safeSet('tab-overview', html);
}

async function checkStatus(piId) {
  const el = document.getElementById('status-result');
  if (!el) return;
  el.textContent = 'Проверка...';
  try {
    const res = await fetch(`${API}/api/orangepi/${piId}/ping`, { method: 'POST' });
    const d = await res.json();
    el.textContent = d.status === 'online' ? '✅ Онлайн' : '❌ ' + (d.message || d.status);
  } catch (e) { el.textContent = 'Ошибка: ' + e.message; }
}

async function rebootPi(piId) {
  if (!confirm('Перезагрузить устройство?')) return;
  try {
    await fetch(`${API}/api/orangepi/${piId}/reboot`, { method: 'POST' });
    alert('Команда отправлена');
  } catch (e) { alert('Ошибка: ' + e.message); }
}

function renderCameras(pi) {
  console.log("🔍 renderCameras вызвана, pi=", pi);
  console.log("🔍 pi.cameras=", pi?.cameras);
  if (pi?.cameras) console.log("🔍 Первая камера:", pi.cameras[0]);
  if (!pi || !pi.cameras) return;
  const cams = pi.cameras;
  let html = `<div class="card"><h3>📹 Камеры (${cams.length}/4)</h3>`;
  
  // Форма добавления (если меньше 4 камер)
  if (cams.length < 4) {
    html += `<div style="background:#0f172a;padding:12px;border-radius:6px;margin:8px 0">
      <input id="cam-name" placeholder="Название*" style="width:100%;padding:8px;margin-bottom:8px">
      <input id="cam-rtsp" placeholder="RTSP URL" style="width:100%;padding:8px;margin-bottom:8px">
      <div style="display:flex;gap:8px;margin-bottom:8px">
        <select id="cam-res" style="flex:1;padding:8px">
          <option value="640">640×420</option>
          <option value="420">420×280</option>
          <option value="380">380×250</option>
          <option value="320">320×210</option>
        </select>
        <input id="cam-int" type="number" value="10" placeholder="Сек" style="flex:1;padding:8px">
      </div>
      <select id="cam-model" style="width:100%;padding:8px;margin-bottom:8px">
        <option value="qwen2.5vl:3b" selected>qwen2.5vl:3b</option>
        <option value="llava:7b">llava:7b</option>
      </select>
      <textarea id="cam-aprompt" placeholder="Промпт анализа" style="width:100%;padding:8px;margin-bottom:8px;height:50px">Кратко опиши что на кадре</textarea>
      <textarea id="cam-rprompt" placeholder="Промпт отчёта" style="width:100%;padding:8px;margin-bottom:8px;height:50px">Опиши события за период</textarea>
      <button class="btn" onclick="addCamera(${pi.id})" style="width:100%">Добавить</button>
    </div><hr style="border-color:#334155">`;
  }
  
  // Список камер
  html += cams.length ? cams.map(c => `
    <div style="background:#0f172a;padding:12px;margin:8px 0;border-radius:6px">
      <div style="display:flex;justify-content:space-between">
        <strong>${c.name || 'Camera'}</strong>
        <span>${c.enabled ? '🟢' : '🔴'}</span>
      </div>
      <small style="color:#94a3b8">${c.rtsp || 'Локальная'} | 🤖 ${c.analysis_model || 'qwen2.5vl:3b'}</small><br>
      <div style="display:flex;gap:8px;margin-top:8px">
        <button class="btn gray" onclick="testPhoto(${c.id})" style="flex:1">📸 Тест</button>
        <button class="btn gray" onclick="editCamera(${c.id})" style="flex:2">✏️ Ред.</button>
        <button class="btn red" onclick="delCamera(${c.id})" style="flex:1">🗑️</button>
      </div>
    </div>`).join('') : '<p style="color:#94a3b8">Камер нет</p>';
  
  html += '</div>';
  safeSet('tab-cameras', html);
}

async function addCamera(piId) {
  const name = document.getElementById('cam-name')?.value?.trim();
  if (!name) return alert('Введите название');
  const data = {
    name,
    rtsp_url: document.getElementById('cam-rtsp')?.value?.trim() || null,
    resolution: document.getElementById('cam-res')?.value,
    motion_interval: +document.getElementById('cam-int')?.value || 10,
    analysis_model: document.getElementById('cam-model')?.value,
    analysis_prompt: document.getElementById('cam-aprompt')?.value?.trim(),
    report_prompt: document.getElementById('cam-rprompt')?.value?.trim(),
    enabled: true
  };
  try {
    const res = await fetch(`${API}/api/orangepi/${piId}/cameras`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'HTTP ' + res.status);
    }
    alert('✅ Камера добавлена');
    openPi(piId);
  } catch (e) {
    alert('❌ Ошибка: ' + e.message);
    console.error('addCamera:', e);
  }
}

async function delCamera(id) {
  if (!confirm('Удалить камеру?')) return;
  try {
    await fetch(`${API}/api/cameras/${id}`, { method: 'DELETE' });
    if (currentPi) openPi(currentPi.id);
  } catch (e) { alert('Ошибка: ' + e.message); }
}

async function testPhoto(id) {
  try {
    await fetch(`${API}/api/cameras/${id}/test`, { method: 'POST' });
    alert('✅ Запрос отправлен. Ждите ~30 сек.');
  } catch (e) { alert('Ошибка: ' + e.message); }
}

async function editCamera(camId) {
  if (!currentPi) return;
  const c = currentPi.cameras?.find(x => x.id === camId);
  if (!c) return;
  const name = prompt('Название:', c.name); if (!name) return;
  const rtsp = prompt('RTSP URL:', c.rtsp || '');
  const res = prompt('Разрешение (640/420/380/320):', c.res || '640');
  const interval = prompt('Интервал (сек):', c.interval || 10);
  const model = prompt('Модель:', c.analysis_model || 'qwen2.5vl:3b');
  const ap = prompt('Промпт анализа:', c.analysis_prompt || '');
  const rp = prompt('Промпт отчёта:', c.report_prompt || '');
  if (name && res && interval) {
    try {
      await fetch(`${API}/api/cameras/${camId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name, rtsp_url: rtsp || null, resolution: res,
          motion_interval: +interval, analysis_model: model,
          analysis_prompt: ap, report_prompt: rp
        })
      });
      alert('✅ Обновлено');
      openPi(currentPi.id);
    } catch (e) { alert('❌ ' + e.message); }
  }
}

async function loadEvents(piId) {
  const el = document.getElementById('tab-events');
  if (!el) return;
  el.innerHTML = '<p style="text-align:center;padding:40px;color:#94a3b8">Загрузка событий...</p>';
  try {
    const res = await fetch(`${API}/api/screenshots/pi/${piId}`);
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const items = await res.json();
    if (!items || !items.length) {
      el.innerHTML = '<p style="text-align:center;padding:40px;color:#94a3b8">Нет событий</p>';
      return;
    }
    const html = items.map(s => {
      let timeStr = '—';
      if (s.time) {
        try {
          const d = new Date(s.time);
          if (!isNaN(d.getTime())) timeStr = d.toLocaleString('ru-RU');
        } catch (e) { timeStr = 'Invalid'; }
      }
      return `<div style="background:#0f172a;padding:12px;margin:8px 0;border-radius:6px">
        ${s.url ? `<img src="${s.url}" style="max-width:100%;max-height:200px;border-radius:4px;margin-bottom:8px" onerror="this.style.display='none'">` : ''}
        <div style="font-size:0.85em;color:#94a3b8">${timeStr}</div>
        <div style="margin-top:4px">${s.desc || '<em style="color:#64748b">Нет описания</em>'}</div>
        ${s.danger ? '<span style="background:var(--danger);color:#000;padding:2px 8px;border-radius:4px;font-size:0.85em;margin-top:4px;display:inline-block">⚠️</span>' : ''}
      </div>`;
    }).join('');
    el.innerHTML = html;
  } catch (e) {
    el.innerHTML = '<p style="color:var(--danger)">Ошибка: ' + e.message + '</p>';
    console.error('loadEvents:', e);
  }
}

async function loadGallery(piId) {
  const el = document.getElementById('tab-gallery');
  if (!el) return;
  el.innerHTML = '<p style="text-align:center;padding:40px;color:#94a3b8">Загрузка галереи...</p>';
  try {
    const res = await fetch(`${API}/api/orangepi/${piId}/folders`);
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const data = await res.json();
    if (!data || !data.folders || !data.folders.length) {
      el.innerHTML = '<p style="text-align:center;padding:40px;color:#94a3b8">Нет фотографий</p>';
      return;
    }
    let html = '<div class="card" style="padding:12px"><h3>📁 Галерея</h3>';
    data.folders.forEach(f => {
      html += `<h4 style="margin:16px 0 12px;color:#94a3b8">📅 ${f.date}</h4>`;
      f.cameras?.forEach(c => {
        html += `<div style="margin:12px 0;padding:12px;background:#0f172a;border-radius:6px">
          <p style="margin-bottom:8px"><strong>Камера ${c.camera_id}</strong> <span style="color:#94a3b8">(${c.count} фото)</span></p>
          <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:8px">`;
        c.files?.slice(0, 12).forEach(fn => {
          const url = `/uploads/pi_${piId}/${f.date}/camera_${c.camera_id}/${fn}`;
          html += `<a href="${url}" target="_blank"><img src="${url}" style="width:100%;height:90px;object-fit:cover;border-radius:4px" loading="lazy"></a>`;
        });
        html += '</div></div>';
      });
    });
    el.innerHTML = html + '</div>';
  } catch (e) {
    el.innerHTML = '<p style="color:var(--danger)">Ошибка: ' + e.message + '</p>';
    console.error('loadGallery:', e);
  }
}

function showList() {
  const viewList = document.getElementById('view-list');
  const viewDetail = document.getElementById('view-detail');
  if (viewList) viewList.classList.remove('hidden');
  if (viewDetail) viewDetail.classList.add('hidden');
  loadPiList();
}
