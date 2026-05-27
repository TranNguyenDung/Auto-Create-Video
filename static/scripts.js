/* ═══════════════════════════════════════════════════════════════
   Pipeline Web - JavaScript
   ═══════════════════════════════════════════════════════════════ */

let selectedContent = '';
let historyData = [];
let eventSource = null;

// ═══ Tab Switching ═══
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
    if (btn.dataset.tab === 'history') refreshHistory();
    if (btn.dataset.tab === 'log') {
      const container = document.getElementById('log-container');
      if (container) container.scrollTop = container.scrollHeight;
    }
  });
});

// ═══ Dropdown ═══
document.querySelectorAll('.dropdown-btn').forEach(btn => {
  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    document.querySelectorAll('.dropdown-menu').forEach(m => m.classList.remove('show'));
    btn.nextElementSibling.classList.toggle('show');
  });
});

document.addEventListener('click', () => {
  document.querySelectorAll('.dropdown-menu').forEach(m => m.classList.remove('show'));
});

// ═══ Search ═══
function filterContent() {
  renderContentList();
}

// ═══ Load Content List ═══
async function loadContents() {
  try {
    const res = await fetch('/api/contents');
    const data = await res.json();
    return data;
  } catch (e) {
    console.error('Failed to load contents:', e);
    return [];
  }
}

async function loadContentDetail(name) {
  try {
    const res = await fetch(`/api/contents/${encodeURIComponent(name)}`);
    return await res.json();
  } catch (e) {
    console.error('Failed to load detail:', e);
    return null;
  }
}

// ═══ Render Content List ═══
async function renderContentList() {
  const contents = await loadContents();
  const search = document.getElementById('search-input').value.toLowerCase().trim();
  const list = document.getElementById('content-list');
  list.innerHTML = '';

  document.getElementById('header-badge').textContent = `${contents.length} contents`;

  if (contents.length === 0) {
    list.innerHTML = '<div class="empty-msg">(Không có file content nào)<br>Tạo file .txt trong B1-Content/</div>';
    return;
  }

  let filtered = contents;
  if (search) {
    filtered = contents.filter(c => c.name.toLowerCase().includes(search));
  }

  if (filtered.length === 0) {
    list.innerHTML = `<div class="empty-msg">Không tìm thấy content "${search}"</div>`;
    return;
  }

  filtered.forEach(c => {
    const item = document.createElement('div');
    item.className = `content-item ${c.status}`;
    if (c.name === selectedContent) item.classList.add('selected');
    item.dataset.name = c.name;

    const statusText = c.status === 'done' ? '✅ Hoàn tất' :
                       c.status === 'partial' ? '🔄 Đang tiến hành' : '⏳ Chưa chạy';

    let badgesHtml = '';
    badgesHtml += `<label class="chk-yt${c.youtube ? ' checked' : ''}">
      <input type="checkbox" ${c.youtube ? 'checked' : ''} data-platform="youtube">YT
    </label>`;
    badgesHtml += `<label class="chk-yt-shorts${c.youtube_shorts ? ' checked' : ''}">
      <input type="checkbox" ${c.youtube_shorts ? 'checked' : ''} data-platform="youtube_shorts">#
    </label>`;
    badgesHtml += `<label class="chk-tt${c.tiktok ? ' checked' : ''}">
      <input type="checkbox" ${c.tiktok ? 'checked' : ''} data-platform="tiktok">TT
    </label>`;
    badgesHtml += `<label class="chk-fb${c.facebook ? ' checked' : ''}">
      <input type="checkbox" ${c.facebook ? 'checked' : ''} data-platform="facebook">FB
    </label>`;
    if (c.note) {
      const noteShort = c.note.length > 18 ? c.note.substring(0, 18) + '...' : c.note;
      badgesHtml += `<span class="note-preview">📝 ${noteShort}</span>`;
    }

    let stepsHtml = '';
    ['B2','B3','B4','B5'].forEach(s => {
      const done = c.steps && c.steps[s];
      stepsHtml += `<span class="step-icon ${done ? 'done' : ''}">${getStepIcon(s)}</span>`;
    });

    item.innerHTML = `
      <div class="content-name-row">
        <span class="content-name">${c.name}</span>
        <span class="content-status">${statusText}</span>
      </div>
      <div class="content-steps">${stepsHtml}</div>
      <div class="content-meta">${badgesHtml}</div>
    `;

    // Checkbox toggle
    item.querySelectorAll('input[type="checkbox"]').forEach(cb => {
      cb.addEventListener('change', async (e) => {
        e.stopPropagation();
        const name = c.name;
        const platform = cb.dataset.platform;
        try {
          const res = await fetch(`/api/contents/${encodeURIComponent(name)}/metadata`);
          const meta = await res.json();
          meta[platform] = cb.checked;
          await fetch(`/api/contents/${encodeURIComponent(name)}/metadata`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(meta),
          });
          cb.parentElement.classList.toggle('checked', cb.checked);
          if (name === selectedContent) updateDetails(name);
        } catch (e) {
          console.error('Failed to toggle platform:', e);
        }
      });
    });

    item.addEventListener('click', () => selectContent(c.name));
    list.appendChild(item);
  });

  if (!selectedContent && filtered.length > 0) {
    selectContent(filtered[0].name);
  }
}

function getStepIcon(step) {
  const icons = {'B2':'🔊','B3':'📜','B4':'✅','B5':'🎬'};
  return icons[step] || '•';
}

// ═══ Select Content ═══
function selectContent(name) {
  selectedContent = name;
  document.querySelectorAll('.content-item').forEach(el => {
    el.classList.toggle('selected', el.dataset.name === name);
  });
  updateDetails(name);
}

// ═══ Update Details Panel ═══
async function updateDetails(name) {
  const detail = await loadContentDetail(name);
  if (!detail) return;

  // Info
  document.getElementById('info-name').textContent = name;
  if (detail.exists) {
    document.getElementById('info-file').textContent = `${name}.txt  •  ${detail.size}  •  ${detail.lines} dòng`;
    document.getElementById('info-mtime').textContent = detail.mtime;
  } else {
    document.getElementById('info-file').textContent = '(file không tồn tại)';
    document.getElementById('info-mtime').textContent = '';
  }

  if (detail.last_run) {
    try {
      const dt = new Date(detail.last_run);
      document.getElementById('info-lastrun').textContent = dt.toLocaleDateString('vi-VN') + ' ' + dt.toLocaleTimeString('vi-VN', {hour:'2-digit',minute:'2-digit'});
    } catch(e) {
      document.getElementById('info-lastrun').textContent = detail.last_run;
    }
  } else {
    document.getElementById('info-lastrun').textContent = '(chưa chạy)';
  }

  document.getElementById('info-stats').textContent =
    `Đã chạy ${detail.run_count} lần  •  ✅ ${detail.success_count} thành công  •  ❌ ${detail.fail_count} thất bại`;

  // Steps
  const stepsContainer = document.getElementById('steps-container');
  stepsContainer.innerHTML = '';

  const allSteps = ['B1', 'B2', 'B3', 'B4', 'B5'];
  allSteps.forEach(s => {
    const done = detail.steps && detail.steps[s];
    const stepInfo = detail[`step_${s}_info`];

    const row = document.createElement('div');
    row.className = 'step-row';

    const nameSpan = document.createElement('span');
    nameSpan.className = 'step-name';
    nameSpan.textContent = `${getStepIcon(s)}  ${getStepName(s)}`;
    row.appendChild(nameSpan);

    const badge = document.createElement('span');
    badge.className = `step-badge ${done ? 'done' : 'pending'}`;
    badge.textContent = done ? '✓ Hoàn tất' : '⏳ Chờ';
    row.appendChild(badge);

    if (done && stepInfo) {
      const info = document.createElement('span');
      info.className = 'step-info';
      info.textContent = `📦 ${stepInfo.size || ''}${stepInfo.duration ? `  •  ⏱ ${stepInfo.duration}` : ''}`;
      row.appendChild(info);
    }

    stepsContainer.appendChild(row);
  });

  // Metadata
  const meta = detail.metadata || {};
  document.getElementById('btn-yt').classList.toggle('active', meta.youtube);
  document.getElementById('btn-yt').textContent = meta.youtube ? '✅  YouTube' : '▶  YouTube';
  document.getElementById('btn-yt-shorts').classList.toggle('active', meta.youtube_shorts);
  document.getElementById('btn-yt-shorts').textContent = meta.youtube_shorts ? '✅  Shorts' : '#  Shorts';
  document.getElementById('btn-tt').classList.toggle('active', meta.tiktok);
  document.getElementById('btn-tt').textContent = meta.tiktok ? '✅  TikTok' : '♪  TikTok';
  document.getElementById('btn-fb').classList.toggle('active', meta.facebook);
  document.getElementById('btn-fb').textContent = meta.facebook ? '✅  Facebook' : '📘  Facebook';
  document.getElementById('note-input').value = meta.note || '';

  updateUploadStatus(meta);
}

function getStepName(step) {
  const names = {'B1':'📝 Nội dung','B2':'🔊 TTS','B3':'📜 SRT','B4':'✅ Xác thực SRT','B5':'🎬 Tạo Video'};
  return names[step] || step;
}

// ═══ Upload Metadata ═══
async function toggleUpload(platform) {
  if (!selectedContent) return;
  try {
    const res = await fetch(`/api/contents/${encodeURIComponent(selectedContent)}/metadata`);
    const meta = await res.json();
    meta[platform] = !meta[platform];

    await fetch(`/api/contents/${encodeURIComponent(selectedContent)}/metadata`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(meta),
    });

    renderContentList();
    updateDetails(selectedContent);
  } catch (e) {
    console.error('Failed to toggle upload:', e);
  }
}

async function saveMetadata() {
  if (!selectedContent) return;
  try {
    const res = await fetch(`/api/contents/${encodeURIComponent(selectedContent)}/metadata`);
    const meta = await res.json();
    meta.note = document.getElementById('note-input').value;

    await fetch(`/api/contents/${encodeURIComponent(selectedContent)}/metadata`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(meta),
    });

    renderContentList();
  } catch (e) {
    console.error('Failed to save metadata:', e);
  }
}

function updateUploadStatus(meta) {
  const tags = [];
  if (meta.youtube) tags.push('▶ YouTube');
  if (meta.youtube_shorts) tags.push('# Shorts');
  if (meta.tiktok) tags.push('♪ TikTok');
  if (meta.facebook) tags.push('📘 Facebook');
  const el = document.getElementById('upload-status');
  if (tags.length > 0) {
    el.textContent = `✅ Đã đăng: ${tags.join(' & ')}`;
    el.style.color = 'var(--success)';
  } else {
    el.textContent = '⏳ Chưa đăng nền tảng nào';
    el.style.color = '';
  }
}

// ═══ Dropdown Menu ═══
(async function initRunFromMenu() {
  const menu = document.getElementById('run-from-menu');
  const steps = ['B2','B3','B4','B5'];
  const names = {'B2':'🔊 TTS','B3':'📜 SRT','B4':'✅ Xác thực SRT','B5':'🎬 Tạo Video'};
  steps.forEach(s => {
    const btn = document.createElement('button');
    btn.className = 'dropdown-item';
    btn.textContent = `${names[s]}`;
    btn.onclick = () => runPipeline(s);
    menu.appendChild(btn);
  });
})();

// ═══ Pipeline Controls ═══
async function runPipeline(startStep) {
  if (!selectedContent) {
    alert('Vui lòng chọn một content.');
    return;
  }

  const stepsToRun = startStep === 'ALL' ? ['B2','B3','B4','B5'] : ['B2','B3','B4','B5'].slice(['B2','B3','B4','B5'].indexOf(startStep));
  const stepNames = stepsToRun.map(s => getStepName(s));

  if (!confirm(`Content: ${selectedContent}\nCác bước: ${stepNames.join(' → ')}\n\nBắt đầu chạy pipeline?`)) return;

  try {
    const res = await fetch('/api/pipeline/start', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({content_name: selectedContent, start_step: startStep}),
    });

    const data = await res.json();
    if (data.error) {
      alert(data.error);
      return;
    }

    // Start SSE
    startSSE();
    pollPipelineStatus();
  } catch (e) {
    console.error('Failed to start pipeline:', e);
  }
}

async function cancelPipeline() {
  try {
    await fetch('/api/pipeline/cancel', { method: 'POST' });
  } catch (e) {
    console.error('Failed to cancel:', e);
  }
}

// ═══ SSE Log Streaming ═══
function startSSE() {
  if (eventSource) {
    eventSource.close();
  }

  eventSource = new EventSource('/api/pipeline/stream');
  const logContent = document.getElementById('log-content');

  eventSource.onmessage = function(e) {
    if (e.data === ': keepalive') return;

    try {
      const entry = JSON.parse(e.data);
      if (entry.tag === '__done__') {
        eventSource.close();
        eventSource = null;
        return;
      }

      const div = document.createElement('div');
      div.className = `log-entry log-${entry.tag}`;
      div.textContent = `[${entry.timestamp}] ${entry.message}`;
      logContent.appendChild(div);
      logContent.parentElement.scrollTop = logContent.parentElement.scrollHeight;
    } catch (e) {
      // ignore parse errors for keepalive
    }
  };

  eventSource.onerror = function() {
    eventSource.close();
    eventSource = null;
  };
}

// ═══ Pipeline Status Polling ═══
let statusTimer = null;

function pollPipelineStatus() {
  if (statusTimer) clearInterval(statusTimer);

  statusTimer = setInterval(async () => {
    try {
      const res = await fetch('/api/pipeline/status');
      const status = await res.json();

      document.getElementById('progress-fill').style.width = `${status.progress}%`;
      const progressText = status.current_step ? `${getStepName(status.current_step)} (${Math.round(status.progress)}%)` : '';
      document.getElementById('status-text').textContent =
        status.running ? `🔄 ${status.content_name} - ${getStepName(status.current_step)}` : 'Sẵn sàng';

      const dot = document.getElementById('status-dot');
      dot.style.color = status.running ? 'var(--accent)' : 'var(--success)';

      document.getElementById('btn-run-all').style.display = status.running ? 'none' : 'inline-flex';
      document.getElementById('btn-cancel').style.display = status.running ? 'inline-flex' : 'none';

      if (!status.running || status.status === 'success' || status.status === 'fail' || status.status === 'cancelled') {
        clearInterval(statusTimer);
        statusTimer = null;
        if (!status.running && status.status === 'idle') return;

        // Switch to log tab briefly
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        document.querySelector('[data-tab="log"]').classList.add('active');
        document.getElementById('tab-log').classList.add('active');

        setTimeout(() => {
          refreshAll();
        }, 500);
      }
    } catch (e) {
      console.error('Status poll error:', e);
    }
  }, 1000);
}

// ═══ Time Window Toggle ═══
function toggleTimeWindow() {
  const enabled = document.getElementById('schedule-time-enable').checked;
  document.getElementById('schedule-time-row').style.display = enabled ? 'flex' : 'none';
}

// ═══ Schedule ═══
let scheduleTimer = null;

async function initSchedule() {
  try {
    const res = await fetch('/api/contents');
    const contents = await res.json();
    const names = contents.map(c => c.name);
    const fromSel = document.getElementById('schedule-from');
    const toSel = document.getElementById('schedule-to');
    fromSel.innerHTML = '';
    toSel.innerHTML = '';
    names.forEach(n => {
      fromSel.innerHTML += `<option value="${n}">${n}</option>`;
      toSel.innerHTML += `<option value="${n}">${n}</option>`;
    });
    // Default: first to last
    if (names.length > 1) {
      const mid = Math.min(11, names.length - 1);
      toSel.value = names[mid];
    }
  } catch (e) {
    console.error('Failed to init schedule:', e);
  }
}

async function startSchedule() {
  const from = document.getElementById('schedule-from').value;
  const to = document.getElementById('schedule-to').value;
  const shutdown = document.getElementById('schedule-shutdown').checked;
  if (!from || !to) { alert('Vui lòng chọn khoảng content.'); return; }

  // Time window
  let time_from = '';
  let time_to = '';
  if (document.getElementById('schedule-time-enable').checked) {
    time_from = document.getElementById('schedule-time-from').value;
    time_to = document.getElementById('schedule-time-to').value;
    if (!time_from || !time_to) { alert('Vui lòng nhập khung giờ.'); return; }
  }

  // Disable button to prevent double-click
  document.getElementById('btn-schedule-start').disabled = true;
  document.getElementById('btn-schedule-start').textContent = '⏳ Đang khởi tạo...';

  try {
    const res = await fetch('/api/schedule/start', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({from, to, shutdown, time_from, time_to}),
    });
    const data = await res.json();
    if (data.error) { 
      alert(data.error);
      document.getElementById('btn-schedule-start').disabled = false;
      document.getElementById('btn-schedule-start').textContent = '📅 Chạy theo lịch';
      return; 
    }

    document.getElementById('btn-schedule-start').style.display = 'none';
    document.getElementById('btn-schedule-cancel').style.display = 'inline-flex';
    document.getElementById('schedule-progress').style.display = 'block';

    startSSE();
    pollScheduleStatus();
  } catch (e) {
    console.error('Failed to start schedule:', e);
    document.getElementById('btn-schedule-start').disabled = false;
    document.getElementById('btn-schedule-start').textContent = '📅 Chạy theo lịch';
  }
}

async function cancelSchedule() {
  try {
    await fetch('/api/schedule/cancel', { method: 'POST' });
  } catch (e) {
    console.error('Failed to cancel schedule:', e);
  }
}

function pollScheduleStatus() {
  if (scheduleTimer) clearInterval(scheduleTimer);
  scheduleTimer = setInterval(async () => {
    try {
      const res = await fetch('/api/schedule/status');
      const s = await res.json();

      const fill = document.getElementById('schedule-progress-fill');
      const text = document.getElementById('schedule-status-text');

      if (s.active) {
        fill.style.width = `${s.progress}%`;

        // Show waiting or running info
        if (s.waiting) {
          text.textContent = `⏳ Đang chờ đến ${s.wait_until}...`;
        } else if (s.current_index >= 0) {
          text.textContent = `[${s.current_index + 1}/${s.contents.length}] ${s.current_content}...`;
        } else {
          text.textContent = `Đang khởi tạo ${s.contents.length} contents...`;
        }

        document.getElementById('btn-schedule-cancel').style.display = 'inline-flex';
      } else {
        // Schedule finished
        clearInterval(scheduleTimer);
        scheduleTimer = null;

        document.getElementById('btn-schedule-start').style.display = 'inline-flex';
        document.getElementById('btn-schedule-start').disabled = false;
        document.getElementById('btn-schedule-start').textContent = '📅 Chạy theo lịch';
        document.getElementById('btn-schedule-cancel').style.display = 'none';

        if (s.status === 'completed') {
          fill.style.width = '100%';
          text.textContent = `✅ Hoàn tất ${s.contents.length} contents!`;
          if (s.shutdown) text.textContent += ' 🔌 Sắp tắt máy...';
        } else if (s.status === 'cancelled') {
          text.textContent = '⏹ Đã huỷ lịch chạy.';
        }

        if (s.shutdown && s.status === 'completed') {
          text.innerHTML = `✅ Hoàn tất ${s.contents.length} contents! 🔌 Sắp tắt máy... <button class="btn btn-sm btn-outline" onclick="cancelShutdown()">Huỷ tắt máy</button>`;
        }

        setTimeout(() => {
          document.getElementById('schedule-progress').style.display = 'none';
          refreshAll();
        }, 5000);
      }
    } catch (e) {
      console.error('Schedule poll error:', e);
    }
  }, 2000);
}

async function cancelShutdown() {
  try {
    const res = await fetch('/api/shutdown/cancel', { method: 'POST' });
    const data = await res.json();
    if (data.error) { alert(data.error); return; }
    document.getElementById('schedule-status-text').textContent = '✅ Đã huỷ tắt máy.';
  } catch (e) {
    console.error('Failed to cancel shutdown:', e);
  }
}

// ═══ Utility Actions ═══
async function editContent() {
  if (!selectedContent) return;
  try {
    await fetch(`/api/content/${encodeURIComponent(selectedContent)}/edit`, { method: 'POST' });
  } catch (e) { console.error(e); }
}

async function openAudioBg() {
  try {
    const res = await fetch('/api/audio-bg', { method: 'POST' });
    const data = await res.json();
    if (data.error) alert(data.error);
  } catch (e) { console.error(e); }
}

async function openOutput() {
  if (!selectedContent) return;
  try {
    await fetch(`/api/content/${encodeURIComponent(selectedContent)}/open-output`, { method: 'POST' });
  } catch (e) { console.error(e); }
}

async function openFolder() {
  if (!selectedContent) return;
  try {
    await fetch(`/api/content/${encodeURIComponent(selectedContent)}/open-folder`, { method: 'POST' });
  } catch (e) { console.error(e); }
}

// ═══ History ═══
async function refreshHistory() {
  try {
    const res = await fetch('/api/history');
    historyData = await res.json();
    renderHistory();
  } catch (e) {
    console.error('Failed to load history:', e);
  }
}

function renderHistory() {
  const tbody = document.getElementById('history-body');
  tbody.innerHTML = '';

  if (historyData.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" class="empty-table">Chưa có lịch sử chạy nào</td></tr>';
    return;
  }

  historyData.forEach((entry, i) => {
    const tr = document.createElement('tr');

    const statusClass = entry.status === 'success' ? 'success' :
                        entry.status === 'cancelled' ? 'cancelled' : 'fail';
    const statusText = entry.status === 'success' ? '✅ Thành công' :
                       entry.status === 'cancelled' ? '⏹ Đã huỷ' : '❌ Thất bại';

    tr.innerHTML = `
      <td>${i + 1}</td>
      <td>${entry.timestamp}</td>
      <td>${entry.content_name}</td>
      <td>${entry.steps_run || '—'}</td>
      <td><span class="status-tag ${statusClass}">${statusText}</span></td>
      <td>${entry.duration}</td>
      <td>${entry.output_count} files</td>
    `;
    tbody.appendChild(tr);
  });
}

async function clearHistory() {
  if (!confirm('Bạn có chắc muốn xoá toàn bộ lịch sử chạy?')) return;
  try {
    await fetch('/api/history', { method: 'DELETE' });
    refreshHistory();
    renderContentList();
  } catch (e) {
    console.error('Failed to clear history:', e);
  }
}

// ═══ Log ═══
function clearLog() {
  document.getElementById('log-content').innerHTML = '';
}


// ═══ Refresh All ═══
async function refreshAll() {
  await renderContentList();
  refreshHistory();
}

// ═══ Init ═══
document.addEventListener('DOMContentLoaded', () => {
  renderContentList();
  refreshHistory();
  initSchedule();
});

// ═══ Auto-refresh status if pipeline was running ═══
setInterval(async () => {
  if (statusTimer) return; // already polling
  try {
    const res = await fetch('/api/pipeline/status');
    const status = await res.json();
    if (status.running) {
      pollPipelineStatus();
      startSSE();
    }
  } catch (e) {}
}, 5000);
