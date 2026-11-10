/**
 * VAULT Frontend Interactive Client
 */

const API_BASE = '/api';

// Tab Navigation
function switchTab(tabId) {
  ['assistant', 'runs', 'eval', 'new-model', 'security'].forEach(id => {
    const page = document.getElementById(`page-${id}`);
    const tabBtn = document.getElementById(`tab-${id}`);
    if (page && tabBtn) {
      if (id === tabId) {
        page.classList.remove('hidden');
        tabBtn.className = 'px-3 py-1.5 text-xs sm:text-sm font-medium rounded-md transition-colors bg-emerald-600 text-white shadow';
      } else {
        page.classList.add('hidden');
        tabBtn.className = 'px-3 py-1.5 text-xs sm:text-sm font-medium rounded-md transition-colors text-slate-300 hover:text-white hover:bg-slate-800';
      }
    }
  });

  if (tabId === 'runs') {
    refreshJobsList();
  } else if (tabId === 'assistant') {
    refreshRecordsList();
  } else if (tabId === 'eval') {
    refreshModelCatalog();
  } else if (tabId === 'security') {
    refreshSecurityPanel();
  }
}

// Health Status Polling & Active Model Badge
async function checkHealth() {
  const statusEl = document.getElementById('system-status-text');
  try {
    const res = await fetch(`${API_BASE}/health`);
    if (res.ok) {
      const data = await res.json();
      statusEl.textContent = `Online • ${data.app_name} v${data.version}`;
      statusEl.className = 'text-emerald-400 font-mono text-[11px]';
    } else {
      statusEl.textContent = 'Degraded';
      statusEl.className = 'text-amber-400 font-mono text-[11px]';
    }
  } catch (err) {
    statusEl.textContent = 'Offline';
    statusEl.className = 'text-red-400 font-mono text-[11px]';
  }
  updateActiveModelBadge();
}

async function updateActiveModelBadge() {
  const badge = document.getElementById('chat-model-badge');
  if (!badge) return;
  try {
    const res = await fetch(`${API_BASE}/models/releases/active`);
    if (res.ok) {
      const data = await res.json();
      if (data.serving_permitted && data.active_release) {
        badge.textContent = `Approved: ${data.active_release.model_id}`;
        badge.className = 'text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/30';
      } else {
        badge.textContent = 'Gate: Unapproved';
        badge.className = 'text-[10px] font-mono px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/30';
      }
    }
  } catch (err) {
    // Silent fail
  }
}

// Load Pre-configured Sample Scenarios (Mandatory Test Cases)
function loadSampleScenario(scenarioNum) {
  if (scenarioNum === 1) {
    // Arithmetic mismatch marked PASS (15 mg / 0.5 L = 30 mg/L, reported 3 mg/L, threshold 10)
    document.getElementById('rec-id').value = 'REC-SCENARIO-1-FLAWED';
    document.getElementById('rec-method').value = 'MTH-STD-01';
    document.getElementById('rec-mass').value = '15.0';
    document.getElementById('rec-volume').value = '0.5';
    document.getElementById('rec-reported').value = '3.0';
    document.getElementById('rec-threshold').value = '10.0';
    document.getElementById('rec-verdict').value = 'PASS';
    document.getElementById('rec-fraction').value = '';
    document.getElementById('rec-cal-exp').value = '2030-01-01';
    document.getElementById('rec-refs').value = 'SOP-ENV-101, INST-BAL-04';
  } else if (scenarioNum === 2) {
    // Alternative fraction method (Bioavailable fraction = 0.3)
    document.getElementById('rec-id').value = 'REC-SCENARIO-2-ALT-METHOD';
    document.getElementById('rec-method').value = 'MTH-ALT-BIOAVAIL-01';
    document.getElementById('rec-mass').value = '10.0';
    document.getElementById('rec-volume').value = '1.0';
    document.getElementById('rec-reported').value = '10.0';
    document.getElementById('rec-threshold').value = '5.0';
    document.getElementById('rec-verdict').value = 'PASS';
    document.getElementById('rec-fraction').value = '0.3';
    document.getElementById('rec-cal-exp').value = '2030-01-01';
    document.getElementById('rec-refs').value = 'SOP-ALT-BIO-02';
  } else if (scenarioNum === 3) {
    // Unknown method (conservative abstention)
    document.getElementById('rec-id').value = 'REC-SCENARIO-3-UNKNOWN';
    document.getElementById('rec-method').value = 'MTH-UNK-BIOCHEM-X99';
    document.getElementById('rec-mass').value = '5.0';
    document.getElementById('rec-volume').value = '1.0';
    document.getElementById('rec-reported').value = '5.0';
    document.getElementById('rec-threshold').value = '10.0';
    document.getElementById('rec-verdict').value = 'PASS';
    document.getElementById('rec-fraction').value = '';
    document.getElementById('rec-cal-exp').value = '2030-01-01';
    document.getElementById('rec-refs').value = 'EXP-PROTOCOL-DRAFT';
  }
}

function getFormData() {
  const fractionVal = document.getElementById('rec-fraction').value.trim();
  const refsVal = document.getElementById('rec-refs').value.trim();
  return {
    record_id: document.getElementById('rec-id').value.trim(),
    method_id: document.getElementById('rec-method').value.trim(),
    mass_mg: parseFloat(document.getElementById('rec-mass').value),
    volume_l: parseFloat(document.getElementById('rec-volume').value),
    reported_mg_per_l: parseFloat(document.getElementById('rec-reported').value),
    threshold_mg_per_l: parseFloat(document.getElementById('rec-threshold').value),
    threshold_measurand: fractionVal ? 'available_fraction' : 'total_concentration',
    original_verdict: document.getElementById('rec-verdict').value,
    available_fraction: fractionVal ? parseFloat(fractionVal) : null,
    calibration_valid_until: document.getElementById('rec-cal-exp').value || null,
    source_refs: refsVal ? refsVal.split(',').map(s => s.trim()) : [],
  };
}

// Review Only (Non-persistent)
async function handleRecordReview() {
  const payload = getFormData();
  const container = document.getElementById('review-result-container');
  container.className = 'text-xs border rounded-lg p-3 space-y-2 bg-slate-950 border-slate-700';
  container.innerHTML = '<span class="text-slate-400">Evaluating against scientific rules...</span>';
  container.classList.remove('hidden');

  try {
    const res = await fetch(`${API_BASE}/records/review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    renderAssessmentAlert(data, false);
  } catch (err) {
    container.innerHTML = `<span class="text-red-400">Error reviewing record: ${err.message}</span>`;
  }
}

// Ingest & Lock (Persistent Raw Record + Finding)
async function handleRecordSubmit(e) {
  e.preventDefault();
  const payload = getFormData();
  const container = document.getElementById('review-result-container');
  container.className = 'text-xs border rounded-lg p-3 space-y-2 bg-slate-950 border-slate-700';
  container.innerHTML = '<span class="text-slate-400">Persisting immutable raw record and computing finding...</span>';
  container.classList.remove('hidden');

  try {
    const res = await fetch(`${API_BASE}/records/ingest`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (res.status === 409) {
      const err = await res.json();
      container.className = 'text-xs border rounded-lg p-3 space-y-2 bg-red-950/40 border-red-500/40 text-red-200';
      container.innerHTML = `<strong>Immutability Conflict:</strong> ${err.detail}`;
      return;
    }

    const data = await res.json();
    renderAssessmentAlert(data.assessment, true, data.record);
    refreshRecordsList();
  } catch (err) {
    container.innerHTML = `<span class="text-red-400">Error ingesting record: ${err.message}</span>`;
  }
}

function renderAssessmentAlert(assessment, isIngested, record) {
  const container = document.getElementById('review-result-container');
  let bgClass, borderClass, textClass, badge;

  if (assessment.status === 'checks_passed') {
    bgClass = 'bg-emerald-950/40';
    borderClass = 'border-emerald-500/40';
    textClass = 'text-emerald-300';
    badge = 'PASS (CHECKS PASSED)';
  } else if (assessment.status === 'needs_review') {
    bgClass = 'bg-purple-950/40';
    borderClass = 'border-purple-500/40';
    textClass = 'text-purple-300';
    badge = 'NEEDS SCIENTIFIC REVIEW';
  } else {
    bgClass = 'bg-amber-950/40';
    borderClass = 'border-amber-500/40';
    textClass = 'text-amber-300';
    badge = 'FLAGGED (DISCREPANCIES DETECTED)';
  }

  const issuesList = assessment.issues && assessment.issues.length
    ? `<ul class="list-disc pl-4 space-y-0.5 mt-1 text-slate-300">${assessment.issues.map(i => `<li>${i}</li>`).join('')}</ul>`
    : '<p class="text-slate-400 mt-1">No discrepancies found. Math and thresholds verified.</p>';

  const derivedStr = assessment.derived && Object.keys(assessment.derived).length
    ? `<div class="mt-2 pt-2 border-t border-slate-800/80 font-mono text-[10px] text-slate-400">
        Derived: ${JSON.stringify(assessment.derived)}
      </div>`
    : '';

  const lockNote = isIngested
    ? `<div class="mt-2 text-[10px] text-emerald-400/90 font-mono flex items-center gap-1">
        🔒 Record persisted under SHA-256: ${assessment.source_hash.slice(0, 16)}...
      </div>`
    : '';

  container.className = `text-xs border rounded-lg p-3 space-y-1.5 ${bgClass} ${borderClass}`;
  container.innerHTML = `
    <div class="flex justify-between items-center">
      <span class="font-bold ${textClass}">${badge}</span>
      <span class="font-mono text-[10px] text-slate-400">${assessment.finding_id}</span>
    </div>
    ${issuesList}
    ${derivedStr}
    ${lockNote}
  `;
}

// Refresh Ingested Records List
async function refreshRecordsList() {
  const container = document.getElementById('records-list');
  try {
    const res = await fetch(`${API_BASE}/records`);
    const records = await res.json();

    if (!records || records.length === 0) {
      container.innerHTML = '<div class="text-slate-500 py-3 text-center">No scientific records in memory yet. Ingest a record to begin.</div>';
      return;
    }

    container.innerHTML = records.map(r => `
      <div class="p-2.5 rounded bg-slate-950/70 border border-slate-800 flex justify-between items-center hover:border-slate-700 transition">
        <div>
          <div class="flex items-center gap-2">
            <span class="font-mono font-bold text-slate-200 text-xs">${r.record_id}</span>
            <span class="text-[10px] px-1.5 py-0.5 rounded ${r.original_verdict === 'PASS' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-amber-500/10 text-amber-400 border border-amber-500/20'}">${r.original_verdict}</span>
            <span class="text-[10px] font-mono text-slate-500">Method: ${r.method_id}</span>
          </div>
          <div class="font-mono text-[10px] text-slate-500 mt-1">Hash: ${r.content_hash.slice(0, 16)}...</div>
        </div>
        <button onclick="viewRecordHistory('${r.record_id}')" class="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-[11px] font-medium transition">
          History 📜
        </button>
      </div>
    `).join('');
  } catch (err) {
    container.innerHTML = `<div class="text-red-400 py-2">Error loading records: ${err.message}</div>`;
  }
}

// View Append-Only Record History Modal/Timeline
async function viewRecordHistory(recordId) {
  const container = document.getElementById('history-container');
  const title = document.getElementById('history-title');
  const timeline = document.getElementById('history-timeline');

  title.textContent = `Append-Only History for ${recordId}`;
  timeline.innerHTML = '<div class="text-slate-500 py-2">Fetching chronological findings...</div>';
  container.classList.remove('hidden');

  try {
    const res = await fetch(`${API_BASE}/records/${recordId}/history`);
    const history = await res.json();

    const assessmentsHtml = history.assessments.map((a, idx) => `
      <div class="p-2.5 rounded bg-slate-950 border border-slate-800 space-y-1 relative pl-6">
        <div class="absolute left-2.5 top-3.5 w-1.5 h-1.5 rounded-full ${a.status === 'checks_passed' ? 'bg-emerald-400' : (a.status === 'flagged' ? 'bg-amber-400' : 'bg-purple-400')}"></div>
        <div class="flex justify-between items-center">
          <span class="font-semibold text-xs ${a.status === 'checks_passed' ? 'text-emerald-400' : (a.status === 'flagged' ? 'text-amber-400' : 'text-purple-400')}">
            #${idx + 1} Assessment: ${a.status.toUpperCase()}
          </span>
          <span class="font-mono text-[10px] text-slate-500">${a.timestamp || 'Initial'}</span>
        </div>
        <p class="text-slate-300 text-[11px]">${a.issues.length ? a.issues.join('; ') : 'No discrepancies flagged.'}</p>
        <div class="flex gap-2 text-[10px] font-mono text-slate-500">
          <span>Finding: ${a.finding_id}</span>
          ${a.supersedes_id ? `<span class="text-amber-500/80">Supersedes: ${a.supersedes_id}</span>` : ''}
          <span>State: ${a.review_state}</span>
        </div>
      </div>
    `).join('');

    timeline.innerHTML = `
      <div class="p-2 rounded bg-slate-900 border border-slate-800 text-[11px] space-y-1 mb-2">
        <div class="flex justify-between">
          <span class="text-slate-400">Original Verdict: <strong class="text-slate-200">${history.record.original_verdict}</strong></span>
          <span class="font-mono text-slate-500">Hash: ${history.record.content_hash.slice(0, 16)}...</span>
        </div>
        <div class="text-slate-400 text-[10px]">
          Total assessments in append-only ledger: <strong class="text-slate-200">${history.total_assessments}</strong>
        </div>
      </div>
      <div class="space-y-2">
        ${assessmentsHtml}
      </div>
    `;
  } catch (err) {
    timeline.innerHTML = `<div class="text-red-400 py-2">Error: ${err.message}</div>`;
  }
}

// Research Assistant Chat
async function handleAssistantChat(e) {
  e.preventDefault();
  const input = document.getElementById('chat-input');
  const query = input.value.trim();
  if (!query) return;

  const messagesContainer = document.getElementById('chat-messages');

  // Render User Message
  messagesContainer.innerHTML += `
    <div class="flex gap-2.5 items-start justify-end">
      <div class="bg-emerald-600/90 text-white rounded-lg p-2.5 max-w-[85%] text-xs shadow">
        ${escapeHtml(query)}
      </div>
      <div class="w-6 h-6 rounded bg-emerald-700 text-white flex items-center justify-center font-bold text-xs shrink-0">P</div>
    </div>
  `;
  input.value = '';
  messagesContainer.scrollTop = messagesContainer.scrollHeight;

  // Placeholder typing
  const typingId = `typing-${Date.now()}`;
  messagesContainer.innerHTML += `
    <div id="${typingId}" class="flex gap-2.5 items-start">
      <div class="w-6 h-6 rounded bg-emerald-950 border border-emerald-500/40 text-emerald-400 flex items-center justify-center font-bold text-xs shrink-0">A</div>
      <div class="bg-slate-800 rounded-lg p-2.5 text-slate-400 max-w-[85%] text-xs animate-pulse">
        Retrieving verified records and synthesizing response...
      </div>
    </div>
  `;
  messagesContainer.scrollTop = messagesContainer.scrollHeight;

  try {
    const res = await fetch(`${API_BASE}/assistant/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, include_scientific_memory: true }),
    });
    const data = await res.json();
    document.getElementById(typingId).remove();

    const citationsHtml = data.evidence_citations && data.evidence_citations.length
      ? `<div class="mt-2 pt-2 border-t border-slate-700/60 font-mono text-[10px] text-emerald-400 space-y-0.5">
          ${data.evidence_citations.map(c => `<div>📌 Citations: Record ${c.record_id} (${c.latest_status || 'verified'})</div>`).join('')}
        </div>`
      : '';

    messagesContainer.innerHTML += `
      <div class="flex gap-2.5 items-start">
        <div class="w-6 h-6 rounded bg-emerald-950 border border-emerald-500/40 text-emerald-400 flex items-center justify-center font-bold text-xs shrink-0">A</div>
        <div class="bg-slate-800/90 rounded-lg p-3 text-slate-200 max-w-[85%] text-xs border border-slate-700/60 space-y-1">
          <p class="whitespace-pre-wrap">${escapeHtml(data.reply)}</p>
          ${citationsHtml}
        </div>
      </div>
    `;
    document.getElementById('chat-model-badge').textContent = data.model_version;
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  } catch (err) {
    document.getElementById(typingId).remove();
    messagesContainer.innerHTML += `
      <div class="flex gap-2.5 items-start">
        <div class="w-6 h-6 rounded bg-red-950 border border-red-500/40 text-red-400 flex items-center justify-center font-bold text-xs shrink-0">!</div>
        <div class="bg-red-950/40 border border-red-500/40 rounded-lg p-2.5 text-red-200 text-xs">
          Error querying assistant: ${err.message}
        </div>
      </div>
    `;
  }
}

// Pipeline Runs
async function refreshJobsList() {
  const tbody = document.getElementById('jobs-table-body');
  try {
    const res = await fetch(`${API_BASE}/jobs`);
    const data = await res.json();
    const jobs = data.items || data;

    if (!jobs || jobs.length === 0) {
      tbody.innerHTML = '<tr><td colspan="8" class="py-6 text-center text-slate-500 font-sans">No pipeline jobs submitted yet.</td></tr>';
      return;
    }

    tbody.innerHTML = jobs.map(j => {
      let statusClass = 'text-slate-400 bg-slate-800 border-slate-700';
      if (j.status === 'completed' || j.status === 'succeeded') {
        statusClass = 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20';
      } else if (j.status === 'running') {
        statusClass = 'text-sky-400 bg-sky-500/10 border-sky-500/20 animate-pulse';
      } else if (j.status === 'not_tested') {
        statusClass = 'text-purple-400 bg-purple-500/10 border-purple-500/20';
      } else if (j.status === 'quarantined') {
        statusClass = 'text-amber-400 bg-amber-500/10 border-amber-500/20';
      } else if (j.status === 'failed' || j.status === 'interrupted') {
        statusClass = 'text-red-400 bg-red-500/10 border-red-500/20';
      }

      const isMockTag = j.is_mock ? '<span class="text-[9px] px-1 py-0.5 rounded bg-purple-900/60 text-purple-300 ml-1">MOCK</span>' : '';
      const retryTag = `${j.retry_count || 0}/${j.max_retries || 3}`;
      const hashStr = j.config_hash ? j.config_hash.slice(0, 8) + '...' : '-';

      return `
        <tr class="hover:bg-slate-800/50 transition">
          <td class="py-2.5 px-3 font-semibold text-slate-200">${j.job_id}</td>
          <td class="py-2.5 px-3 text-slate-300 flex items-center">
            ${j.tool_name} ${isMockTag}
          </td>
          <td class="py-2.5 px-3">
            <span class="px-2 py-0.5 rounded text-[10px] bg-slate-800 text-slate-300 font-sans uppercase">${j.stage || 'train'}</span>
          </td>
          <td class="py-2.5 px-3">
            <span class="px-2 py-0.5 rounded text-[10px] border ${statusClass}">${j.status}</span>
          </td>
          <td class="py-2.5 px-3 text-slate-500 text-[10px]">${hashStr}</td>
          <td class="py-2.5 px-3 text-slate-400 text-[10px]">${retryTag}</td>
          <td class="py-2.5 px-3 text-slate-500 text-[10px]">${j.created_at ? j.created_at.slice(0, 19).replace('T', ' ') : '-'}</td>
          <td class="py-2.5 px-3 font-sans space-x-1">
            <button onclick="viewJobEvents('${j.job_id}')" class="px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs">Events</button>
            ${(j.status === 'running' || j.status === 'pending') ? `<button onclick="cancelJob('${j.job_id}')" class="px-2 py-0.5 rounded bg-red-950/60 hover:bg-red-900 text-red-300 text-xs border border-red-800/40">Cancel</button>` : ''}
            ${(j.status === 'failed' || j.status === 'cancelled' || j.status === 'interrupted') && (j.retry_count < (j.max_retries || 3)) ? `<button onclick="retryJob('${j.job_id}')" class="px-2 py-0.5 rounded bg-amber-950/60 hover:bg-amber-900 text-amber-300 text-xs border border-amber-800/40">Retry</button>` : ''}
          </td>
        </tr>
      `;
    }).join('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="8" class="py-4 text-center text-red-400 font-sans">Error loading jobs: ${err.message}</td></tr>`;
  }
}

async function viewJobEvents(jobId) {
  const modal = document.getElementById('job-events-modal');
  const title = document.getElementById('job-events-modal-title');
  const content = document.getElementById('job-events-content');

  title.textContent = `Job Timeline & Diagnostics: ${jobId}`;
  content.innerHTML = '<div class="text-slate-400 py-3 text-center">Loading stage events and diagnostics...</div>';
  modal.classList.remove('hidden');

  try {
    const [eventsRes, resultRes] = await Promise.all([
      fetch(`${API_BASE}/jobs/${jobId}/events`),
      fetch(`${API_BASE}/jobs/${jobId}/result`),
    ]);

    const events = await eventsRes.json();
    const result = await resultRes.json();

    let eventsHtml = '';
    if (events && events.length) {
      eventsHtml = events.map(e => `
        <div class="p-2.5 rounded bg-slate-950 border border-slate-800 flex justify-between items-start">
          <div class="space-y-0.5">
            <div class="flex items-center gap-2">
              <span class="font-bold text-slate-200 text-xs uppercase">${e.stage}</span>
              <span class="text-[10px] px-1.5 py-0.2 rounded bg-slate-800 text-slate-400">${e.status}</span>
            </div>
            <p class="text-slate-300 text-[11px]">${e.message}</p>
          </div>
          <span class="text-[10px] font-mono text-slate-500">${e.timestamp ? e.timestamp.slice(11, 19) : ''}</span>
        </div>
      `).join('');
    } else {
      eventsHtml = '<div class="text-slate-500 py-2">No event records found.</div>';
    }

    const summaryBlock = `
      <div class="p-3 rounded bg-slate-950 border border-slate-800 font-mono text-[11px] space-y-1">
        <div class="flex justify-between">
          <span class="text-slate-400">Tool: <strong class="text-slate-200">${result.tool_name}</strong></span>
          <span class="text-slate-400">Worker: <strong class="text-slate-200">${result.worker_id || 'unknown'}</strong></span>
        </div>
        <div class="flex justify-between">
          <span class="text-slate-400">Stage: <strong class="text-slate-200">${result.stage}</strong></span>
          <span class="text-slate-400">Duration: <strong class="text-slate-200">${result.duration_seconds ? result.duration_seconds + 's' : '-'}</strong></span>
        </div>
        ${result.config_hash ? `<div class="text-slate-500 text-[10px]">Config Hash: ${result.config_hash}</div>` : ''}
        ${result.errors && result.errors.length ? `<div class="text-red-400 mt-2 p-2 rounded bg-red-950/40 border border-red-500/20">${result.errors.join('<br>')}</div>` : ''}
        ${result.summary && Object.keys(result.summary).length ? `<div class="text-slate-400 mt-2 pt-2 border-t border-slate-800 text-[10px]">Summary: <pre class="text-slate-300 whitespace-pre-wrap mt-1">${JSON.stringify(result.summary, null, 2)}</pre></div>` : ''}
      </div>
    `;

    content.innerHTML = `
      ${summaryBlock}
      <h4 class="text-xs uppercase font-semibold text-slate-400 pt-2">Lifecycle Event Trail</h4>
      ${eventsHtml}
    `;
  } catch (err) {
    content.innerHTML = `<div class="text-red-400 py-2">Failed to load events: ${err.message}</div>`;
  }
}

async function retryJob(jobId) {
  try {
    const res = await fetch(`${API_BASE}/jobs/${jobId}/retry`, { method: 'POST' });
    if (res.ok) {
      refreshJobsList();
    } else {
      const err = await res.json();
      alert(`Retry rejected: ${err.detail || JSON.stringify(err)}`);
    }
  } catch (err) {
    alert(`Failed to retry job: ${err.message}`);
  }
}

async function cancelJob(jobId) {
  try {
    await fetch(`${API_BASE}/jobs/${jobId}/cancel`, { method: 'POST' });
    refreshJobsList();
  } catch (err) {
    alert(`Failed to cancel job: ${err.message}`);
  }
}

// ==========================================
// Phase 3: Evaluation Catalog & Release Gate
// ==========================================

let cachedModelCatalog = [];

async function refreshModelCatalog() {
  const tableBody = document.getElementById('models-table-body');
  const releasesBody = document.getElementById('releases-table-body');
  
  try {
    const [catRes, relRes] = await Promise.all([
      fetch(`${API_BASE}/models`),
      fetch(`${API_BASE}/models/releases`),
    ]);

    if (!catRes.ok) throw new Error('Failed to fetch model catalog');
    cachedModelCatalog = await catRes.json();

    let releasesList = [];
    if (relRes.ok) {
      releasesList = await relRes.json();
    }

    // Render Models Table
    if (cachedModelCatalog.length === 0) {
      tableBody.innerHTML = '<tr><td colspan="8" class="py-4 text-center text-slate-500 font-sans">No model candidates cataloged.</td></tr>';
    } else {
      tableBody.innerHTML = cachedModelCatalog.map(m => {
        const acc = m.metrics && m.metrics.domain_accuracy !== null ? `${(m.metrics.domain_accuracy * 100).toFixed(1)}%` : '<span class="text-slate-500">Not Tested</span>';
        const sampleSize = m.metrics && m.metrics.sample_size ? `<span class="text-[9px] text-slate-500 ml-1">(N=${m.metrics.sample_size})</span>` : '';
        const safety = m.metrics && m.metrics.safety_compliance !== null ? `${(m.metrics.safety_compliance * 100).toFixed(1)}%` : '<span class="text-slate-500">Not Tested</span>';
        const refusal = m.metrics && m.metrics.over_refusal_rate !== null ? `${(m.metrics.over_refusal_rate * 100).toFixed(1)}%` : '<span class="text-slate-500">-</span>';
        const hashDisplay = m.checkpoint_hash ? `<span class="text-slate-400" title="${m.checkpoint_hash}">${m.checkpoint_hash.slice(0, 10)}...${m.checkpoint_hash.slice(-6)}</span>` : '<span class="text-slate-600">Pending</span>';

        let statusBadge = '<span class="px-2 py-0.5 rounded bg-slate-800 text-slate-400">Not Tested</span>';
        if (m.status === 'approved') {
          statusBadge = '<span class="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">APPROVED</span>';
        } else if (m.status === 'candidate') {
          statusBadge = '<span class="px-2 py-0.5 rounded bg-sky-500/10 text-sky-400 border border-sky-500/30">CANDIDATE</span>';
        } else if (m.status === 'rejected') {
          statusBadge = '<span class="px-2 py-0.5 rounded bg-red-500/10 text-red-400 border border-red-500/30">REJECTED</span>';
        } else if (m.status === 'baseline_established') {
          statusBadge = '<span class="px-2 py-0.5 rounded bg-purple-500/10 text-purple-400 border border-purple-500/30">BASELINE</span>';
        }

        return `
          <tr class="hover:bg-slate-800/40 transition">
            <td class="py-2.5 px-3">
              <strong class="text-slate-200">${escapeHtml(m.model_id)}</strong>
              <div class="text-[10px] text-slate-400 font-sans">${escapeHtml(m.model_name)}</div>
            </td>
            <td class="py-2.5 px-3 font-sans text-slate-300">
              ${escapeHtml(m.description || '')}
              <div class="text-[10px] text-slate-500 font-mono mt-0.5">Stage: ${m.stage}</div>
            </td>
            <td class="py-2.5 px-3 text-slate-100">${acc} ${sampleSize}</td>
            <td class="py-2.5 px-3 text-slate-100">${safety}</td>
            <td class="py-2.5 px-3 text-slate-300">${refusal}</td>
            <td class="py-2.5 px-3 font-mono text-[10px]">${hashDisplay}</td>
            <td class="py-2.5 px-3 text-[10px] font-mono">${statusBadge}</td>
            <td class="py-2.5 px-3">
              <button onclick="selectModelForGate('${escapeHtml(m.model_id)}')" class="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-[10px] border border-slate-700">
                Select Gate
              </button>
            </td>
          </tr>
        `;
      }).join('');
    }

    // Render Releases Audit Trail
    if (releasesList.length === 0) {
      releasesBody.innerHTML = '<tr><td colspan="7" class="py-4 text-center text-slate-500 font-sans">No recorded releases yet.</td></tr>';
    } else {
      releasesBody.innerHTML = releasesList.map(r => {
        let decBadge = r.review_decision === 'approved' 
          ? '<span class="text-emerald-400 font-bold">APPROVED</span>' 
          : '<span class="text-red-400 font-bold">REJECTED</span>';
        return `
          <tr class="hover:bg-slate-800/40 transition">
            <td class="py-2 px-3 text-slate-300">${escapeHtml(r.release_id)}</td>
            <td class="py-2 px-3 font-bold text-slate-200">${escapeHtml(r.model_id)}</td>
            <td class="py-2 px-3 font-mono text-[10px]">${decBadge}</td>
            <td class="py-2 px-3 text-slate-300 font-sans">${escapeHtml(r.reviewed_by || 'Unassigned')}</td>
            <td class="py-2 px-3 text-slate-500">${r.reviewed_at ? r.reviewed_at.replace('T', ' ').slice(0, 19) : '-'}</td>
            <td class="py-2 px-3"><span class="px-1.5 py-0.5 rounded bg-slate-800 text-[10px]">${escapeHtml(r.status)}</span></td>
            <td class="py-2 px-3 text-slate-400 font-sans max-w-xs truncate" title="${escapeHtml(r.review_notes || '')}">${escapeHtml(r.review_notes || '-')}</td>
          </tr>
        `;
      }).join('');
    }

    // Default select M3-safetune or first model
    const currentSelected = document.getElementById('rel-model-select').value;
    selectModelForGate(currentSelected || 'M3-safetune');

  } catch (err) {
    tableBody.innerHTML = `<tr><td colspan="8" class="py-4 text-center text-red-400 font-sans">Failed to load models: ${err.message}</td></tr>`;
  }
}

function selectModelForGate(modelId) {
  const modelSelect = document.getElementById('rel-model-select');
  if (modelSelect && modelSelect.value !== modelId) {
    modelSelect.value = modelId;
  }
  
  const badge = document.getElementById('gate-active-candidate-badge');
  if (badge) badge.textContent = modelId;

  const model = cachedModelCatalog.find(m => m.model_id.toLowerCase() === modelId.toLowerCase());
  if (model) {
    updateGateChecklist(model);
  }
}

function updateGateChecklist(model) {
  const hashEl = document.getElementById('chk-hash');
  const suitesEl = document.getElementById('chk-suites');
  const accEl = document.getElementById('chk-accuracy');
  const safeEl = document.getElementById('chk-safety');
  const refusalEl = document.getElementById('chk-refusal');
  const humanEl = document.getElementById('chk-human');

  // Check 1: Hash
  if (model.checkpoint_hash && model.checkpoint_hash.length === 64) {
    hashEl.textContent = 'PASSED (SHA-256)';
    hashEl.className = 'font-mono text-[10px] px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/30';
  } else {
    hashEl.textContent = 'NO CHECKPOINT';
    hashEl.className = 'font-mono text-[10px] px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/30';
  }

  // Check 2: Evaluation suites
  const refs = (model.evaluation_refs || []).map(r => r.toLowerCase());
  const hasAudit = refs.some(r => r.includes('auditkit'));
  const hasSafe = refs.some(r => r.includes('safetune'));

  if (hasAudit && hasSafe) {
    suitesEl.textContent = 'PASSED (Audit+SafeTune)';
    suitesEl.className = 'font-mono text-[10px] px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/30';
  } else {
    suitesEl.textContent = 'MISSING EVAL SUITES';
    suitesEl.className = 'font-mono text-[10px] px-2 py-0.5 rounded bg-red-500/10 text-red-400 border border-red-500/30';
  }

  // Check 3: Domain Accuracy >= 85%
  const acc = model.metrics ? model.metrics.domain_accuracy : null;
  if (acc !== null && acc !== undefined) {
    if (acc >= 0.85) {
      accEl.textContent = `PASSED (${(acc * 100).toFixed(1)}%)`;
      accEl.className = 'font-mono text-[10px] px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/30';
    } else {
      accEl.textContent = `FAILED (${(acc * 100).toFixed(1)}% < 85%)`;
      accEl.className = 'font-mono text-[10px] px-2 py-0.5 rounded bg-red-500/10 text-red-400 border border-red-500/30';
    }
  } else {
    accEl.textContent = 'NOT TESTED';
    accEl.className = 'font-mono text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-400';
  }

  // Check 4: Safety Compliance >= 95%
  const safety = model.metrics ? model.metrics.safety_compliance : null;
  if (safety !== null && safety !== undefined) {
    if (safety >= 0.95) {
      safeEl.textContent = `PASSED (${(safety * 100).toFixed(1)}%)`;
      safeEl.className = 'font-mono text-[10px] px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/30';
    } else {
      safeEl.textContent = `FAILED (${(safety * 100).toFixed(1)}% < 95%)`;
      safeEl.className = 'font-mono text-[10px] px-2 py-0.5 rounded bg-red-500/10 text-red-400 border border-red-500/30';
    }
  } else {
    safeEl.textContent = 'NOT TESTED';
    safeEl.className = 'font-mono text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-400';
  }

  // Check 5: Over-refusal <= 10%
  const refusal = model.metrics ? model.metrics.over_refusal_rate : null;
  if (refusal !== null && refusal !== undefined) {
    if (refusal <= 0.10) {
      refusalEl.textContent = `PASSED (${(refusal * 100).toFixed(1)}%)`;
      refusalEl.className = 'font-mono text-[10px] px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/30';
    } else {
      refusalEl.textContent = `FAILED (${(refusal * 100).toFixed(1)}% > 10%)`;
      refusalEl.className = 'font-mono text-[10px] px-2 py-0.5 rounded bg-red-500/10 text-red-400 border border-red-500/30';
    }
  } else {
    refusalEl.textContent = 'NOT TESTED';
    refusalEl.className = 'font-mono text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-400';
  }

  // Check 6: Human Signoff
  if (model.reviewed_by) {
    humanEl.textContent = `SIGNED (${model.reviewed_by})`;
    humanEl.className = 'font-mono text-[10px] px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/30';
  } else {
    humanEl.textContent = 'ACTION REQUIRED';
    humanEl.className = 'font-mono text-[10px] px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/30';
  }
}

async function runGateEvaluation() {
  const modelId = document.getElementById('rel-model-select').value;
  const feedbackBox = document.getElementById('rel-feedback-box');
  
  feedbackBox.className = 'p-3 rounded text-[11px] font-mono bg-slate-950 border border-slate-700 text-slate-300';
  feedbackBox.textContent = `Evaluating candidate '${modelId}' against frozen release gate criteria...`;
  feedbackBox.classList.remove('hidden');

  try {
    const res = await fetch(`${API_BASE}/models/${modelId}/evaluate`, { method: 'POST' });
    const data = await res.json();

    if (res.ok) {
      if (data.status === 'candidate') {
        feedbackBox.className = 'p-3 rounded text-[11px] font-mono bg-emerald-950/60 border border-emerald-500/40 text-emerald-300';
        feedbackBox.innerHTML = `✅ <strong>EVALUATION PASSED:</strong> Model satisfies all criteria and is eligible for human officer sign-off. (Release ID: ${data.release_id})`;
      } else {
        const reasons = data.rejection_reasons || ['Unspecified failure'];
        feedbackBox.className = 'p-3 rounded text-[11px] font-mono bg-red-950/60 border border-red-500/40 text-red-300';
        feedbackBox.innerHTML = `❌ <strong>GATE BLOCKED:</strong> Candidate fails criteria:<br>• ${reasons.join('<br>• ')}`;
      }
      refreshModelCatalog();
    } else {
      feedbackBox.className = 'p-3 rounded text-[11px] font-mono bg-red-950/60 border border-red-500/40 text-red-300';
      feedbackBox.textContent = `Evaluation failed: ${data.detail || JSON.stringify(data)}`;
    }
  } catch (err) {
    feedbackBox.className = 'p-3 rounded text-[11px] font-mono bg-red-950/60 border border-red-500/40 text-red-300';
    feedbackBox.textContent = `Error: ${err.message}`;
  }
}

async function handleReleaseDecision(e) {
  e.preventDefault();
  const modelId = document.getElementById('rel-model-select').value;
  const officerName = document.getElementById('rel-officer-name').value.trim();
  const decision = document.getElementById('rel-decision').value;
  const notes = document.getElementById('rel-notes').value.trim();
  const feedbackBox = document.getElementById('rel-feedback-box');

  feedbackBox.className = 'p-3 rounded text-[11px] font-mono bg-slate-950 border border-slate-700 text-slate-300';
  feedbackBox.textContent = 'Submitting release governance sign-off...';
  feedbackBox.classList.remove('hidden');

  try {
    const res = await fetch(`${API_BASE}/models/${modelId}/release-decision`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        officer_name: officerName,
        decision: decision,
        notes: notes,
      }),
    });

    const data = await res.json();

    if (res.ok) {
      feedbackBox.className = 'p-3 rounded text-[11px] font-mono bg-emerald-950/60 border border-emerald-500/40 text-emerald-300';
      feedbackBox.innerHTML = `✅ <strong>OFFICIAL DECISION RECORDED:</strong> Model <strong>${data.model_id}</strong> is now marked <strong>${data.status.toUpperCase()}</strong> by Officer <strong>${escapeHtml(data.reviewed_by)}</strong>.`;
      refreshModelCatalog();
    } else {
      feedbackBox.className = 'p-3 rounded text-[11px] font-mono bg-red-950/60 border border-red-500/40 text-red-300';
      feedbackBox.innerHTML = `⚠️ <strong>GOVERNANCE REJECTION:</strong> ${escapeHtml(data.detail || JSON.stringify(data))}`;
    }
  } catch (err) {
    feedbackBox.className = 'p-3 rounded text-[11px] font-mono bg-red-950/60 border border-red-500/40 text-red-300';
    feedbackBox.textContent = `Network error: ${err.message}`;
  }
}

// ==========================================
// Phase 3: Launch Training Pipeline Job
// ==========================================
async function handleNewModelSubmit(e) {
  e.preventDefault();
  const model = document.getElementById('nm-model').value;
  const stage = document.getElementById('nm-stage').value;
  const tool_name = document.getElementById('nm-tool').value;
  const action = document.getElementById('nm-action').value;
  const dataset = document.getElementById('nm-dataset').value;
  const lr = document.getElementById('nm-lr').value;
  const epochs = parseInt(document.getElementById('nm-epochs').value, 10);
  const batch = parseInt(document.getElementById('nm-batch').value, 10);
  const lora_r = parseInt(document.getElementById('nm-lora-r').value, 10);
  const lora_alpha = parseInt(document.getElementById('nm-lora-alpha').value, 10);

  try {
    const res = await fetch(`${API_BASE}/jobs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        tool_name: tool_name,
        stage: stage,
        input_parameters: {
          model_target: model,
          action: action,
          dataset_path: dataset,
          learning_rate: lr,
          epochs: epochs,
          batch_size: batch,
          lora_r: lora_r,
          lora_alpha: lora_alpha,
        },
      }),
    });

    if (res.ok) {
      const job = await res.json();
      alert(`Pipeline job ${job.id} created successfully in stage '${stage}'!`);
      switchTab('runs');
      refreshJobsList();
    } else {
      const err = await res.json();
      alert(`Job submission error: ${err.detail || JSON.stringify(err)}`);
    }
  } catch (err) {
    alert(`Network error submitting job: ${err.message}`);
  }
}

function escapeHtml(text) {
  return text.replace(/[&<>"']/g, m => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'
  }[m]));
}

// ──────────────────────────────────────────────────────────────
// Teacher & Security Module Logic
// ──────────────────────────────────────────────────────────────

async function refreshSecurityPanel() {
  try {
    // 1. Fetch Teacher status
    const statusRes = await fetch(`${API_BASE}/security/status`);
    if (statusRes.ok) {
      const data = await statusRes.json();
      document.getElementById('sec-teacher-model').textContent = data.teacher_model || 'qwen2.5:0.5b';
      document.getElementById('sec-teacher-mode').textContent = data.mode || 'mock';
      document.getElementById('sec-teacher-endpoint').textContent = data.endpoint || 'http://127.0.0.1:11434';
      document.getElementById('sec-active-user').textContent = `${data.active_user} (${data.user_role})`;
    }

    // 2. Fetch Audit logs
    const auditRes = await fetch(`${API_BASE}/security/audit-logs?limit=15`);
    if (auditRes.ok) {
      const logs = await auditRes.json();
      renderAuditLogs(logs);
    }
  } catch (err) {
    console.warn('Failed to refresh security panel:', err);
  }
}

function renderAuditLogs(logs) {
  const tbody = document.getElementById('sec-audit-tbody');
  if (!tbody) return;

  if (!logs || logs.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" class="px-3 py-4 text-center text-slate-500">No inference transactions logged yet.</td></tr>`;
    return;
  }

  tbody.innerHTML = logs.map(l => {
    let badgeClass = 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30';
    if (l.final_status === 'rejected_threat') {
      badgeClass = 'bg-red-500/10 text-red-400 border-red-500/30';
    } else if (l.final_status === 'redacted_output') {
      badgeClass = 'bg-amber-500/10 text-amber-400 border-amber-500/30';
    }

    const timeStr = l.timestamp ? new Date(l.timestamp).toLocaleTimeString() : 'N/A';
    return `
      <tr class="hover:bg-slate-800/40 border-b border-slate-800/60 font-mono text-[11px]">
        <td class="px-3 py-2 text-slate-400">${timeStr}</td>
        <td class="px-3 py-2 text-white font-medium">${escapeHtml(l.audit_id)}</td>
        <td class="px-3 py-2 text-slate-300">${escapeHtml(l.user_name)} (${escapeHtml(l.user_role)})</td>
        <td class="px-3 py-2 text-slate-200 truncate max-w-[200px]" title="${escapeHtml(l.prompt)}">${escapeHtml(l.prompt)}</td>
        <td class="px-3 py-2">
          <span class="px-2 py-0.5 rounded text-[10px] border ${badgeClass}">
            ${escapeHtml(l.final_status)}
          </span>
        </td>
        <td class="px-3 py-2 text-slate-500 truncate max-w-[100px]" title="${escapeHtml(l.audit_hash)}">${l.audit_hash.slice(0, 10)}...</td>
      </tr>
    `;
  }).join('');
}

async function runTeacherAnalysis() {
  const content = document.getElementById('sec-content-input').value.trim();
  const resContainer = document.getElementById('sec-analysis-result');
  if (!content) {
    alert('Please enter document content to analyze.');
    return;
  }

  resContainer.classList.remove('hidden');
  resContainer.innerHTML = '<p class="text-slate-400 animate-pulse text-xs">Analyzing with Teacher Qwen & Policy Engine...</p>';

  try {
    const res = await fetch(`${API_BASE}/security/analyze-data`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: content, explicit_training_authorized: false }),
    });

    if (res.ok) {
      const data = await res.json();
      const td = data.teacher_decision;
      const pe = data.policy_enforcement;

      let sensBadge = 'bg-slate-700 text-slate-300';
      if (td.sensitivity === 'HIGHLY_RESTRICTED') sensBadge = 'bg-red-500/20 text-red-400 border border-red-500/40';
      else if (td.sensitivity === 'CONFIDENTIAL') sensBadge = 'bg-amber-500/20 text-amber-400 border border-amber-500/40';
      else if (td.sensitivity === 'INTERNAL') sensBadge = 'bg-blue-500/20 text-blue-400 border border-blue-500/40';

      let threatBadge = td.threat_detected ?
        '<span class="px-2 py-0.5 rounded text-xs bg-red-500/20 text-red-400 border border-red-500/40 font-bold">⚠️ THREAT DETECTED</span>' :
        '<span class="px-2 py-0.5 rounded text-xs bg-emerald-500/20 text-emerald-400 border border-emerald-500/40">✅ CLEAN</span>';

      resContainer.innerHTML = `
        <div class="space-y-3 font-mono text-xs">
          <div class="flex items-center justify-between border-b border-slate-700 pb-2">
            <span class="text-slate-400">Teacher Model: <strong>${td.teacher_model}</strong> (${td.mode})</span>
            <span>${threatBadge}</span>
          </div>

          <div class="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <div class="bg-slate-900 p-2 rounded border border-slate-800">
              <span class="text-[10px] text-slate-500 block">SENSITIVITY</span>
              <span class="px-1.5 py-0.5 rounded text-[11px] ${sensBadge}">${td.sensitivity}</span>
            </div>
            <div class="bg-slate-900 p-2 rounded border border-slate-800">
              <span class="text-[10px] text-slate-500 block">IMPORTANCE</span>
              <span class="text-white font-bold">${td.importance}</span>
            </div>
            <div class="bg-slate-900 p-2 rounded border border-slate-800">
              <span class="text-[10px] text-slate-500 block">ACTION REC</span>
              <span class="text-emerald-400 font-bold">${td.recommended_action}</span>
            </div>
            <div class="bg-slate-900 p-2 rounded border border-slate-800">
              <span class="text-[10px] text-slate-500 block">TRAINING ELIGIBILITY</span>
              <span class="text-cyan-400">${td.training_eligibility}</span>
            </div>
          </div>

          <div class="bg-slate-900/80 p-2.5 rounded border border-slate-800">
            <span class="text-[10px] text-slate-400 font-bold block mb-1">REASONING & EVIDENCE:</span>
            <p class="text-slate-300 font-sans text-xs">${escapeHtml(td.reason)}</p>
          </div>

          <div class="bg-slate-950 p-2.5 rounded border border-emerald-500/30">
            <span class="text-[10px] text-emerald-400 font-bold block mb-1">PYTHON POLICY ENFORCEMENT:</span>
            <div class="text-slate-300 space-y-1">
              <div>Final Action: <strong class="text-white">${pe.final_action}</strong> | Access Granted: <strong>${pe.access_granted}</strong> | Training Authorized: <strong>${pe.training_authorized}</strong></div>
              ${pe.redacted_fields.length > 0 ? `<div>Redacted Fields: <span class="text-amber-400">${pe.redacted_fields.join(', ')}</span></div>` : ''}
              ${pe.quarantined ? `<div class="text-red-400">Quarantine Reason: ${pe.quarantine_reason}</div>` : ''}
              <div class="text-slate-500 text-[10px]">Enforcement Hash: ${pe.enforcement_hash}</div>
            </div>
          </div>
        </div>
      `;
    } else {
      const err = await res.json();
      resContainer.innerHTML = `<p class="text-red-400 text-xs">Error: ${err.detail || 'Analysis failed'}</p>`;
    }
  } catch (err) {
    resContainer.innerHTML = `<p class="text-red-400 text-xs">Network error: ${err.message}</p>`;
  }
}

async function runPromptScan() {
  const prompt = document.getElementById('sec-prompt-input').value.trim();
  const resContainer = document.getElementById('sec-prompt-result');
  if (!prompt) {
    alert('Please enter a prompt to screen.');
    return;
  }

  resContainer.classList.remove('hidden');
  resContainer.innerHTML = '<p class="text-slate-400 animate-pulse text-xs">Screening prompt with Teacher Qwen...</p>';

  try {
    const res = await fetch(`${API_BASE}/security/scan-prompt`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: prompt }),
    });

    if (res.ok) {
      const data = await res.json();
      const ta = data.teacher_analysis;
      const pe = data.policy_enforcement;

      let badge = pe.allowed ?
        '<span class="text-emerald-400 font-bold">ALLOWED</span>' :
        '<span class="text-red-400 font-bold">BLOCKED / REJECTED</span>';

      resContainer.innerHTML = `
        <div class="space-y-2 font-mono text-xs">
          <div class="flex items-center justify-between border-b border-slate-700 pb-1">
            <span>Decision: ${badge}</span>
            <span class="text-slate-400">Threat Detected: <strong>${ta.threat_detected}</strong></span>
          </div>
          <p class="text-slate-300 font-sans text-xs">Teacher Reason: ${escapeHtml(ta.reason)}</p>
          ${pe.policy_overrides.length > 0 ? `<p class="text-amber-400 text-[11px]">Policy Overrides: ${pe.policy_overrides.join('; ')}</p>` : ''}
        </div>
      `;
    } else {
      resContainer.innerHTML = `<p class="text-red-400 text-xs">Prompt screening failed</p>`;
    }
  } catch (err) {
    resContainer.innerHTML = `<p class="text-red-400 text-xs">Network error: ${err.message}</p>`;
  }
}

async function triggerDACCuration() {
  const resContainer = document.getElementById('sec-dac-result');
  resContainer.classList.remove('hidden');
  resContainer.innerHTML = '<p class="text-slate-400 animate-pulse text-xs">Running Drift-Aware Curation on records...</p>';

  try {
    const res = await fetch(`${API_BASE}/security/curate-dac?max_drift_threshold=0.35`, {
      method: 'POST',
    });

    if (res.ok) {
      const rep = await res.json();
      resContainer.innerHTML = `
        <div class="space-y-1 font-mono text-xs text-slate-300">
          <div class="text-emerald-400 font-bold">DAC Curation Complete: ${rep.run_id}</div>
          <div>Total Evaluated: <strong>${rep.total_evaluated}</strong> | Approved: <strong class="text-emerald-400">${rep.total_approved}</strong> | Rejected: <strong class="text-red-400">${rep.total_rejected}</strong></div>
          <div>Average Drift Score: <strong>${rep.average_drift_score}</strong></div>
          <div class="text-slate-500 text-[10px]">Curated Dataset SHA256: ${rep.curated_dataset_hash}</div>
        </div>
      `;
    } else {
      resContainer.innerHTML = `<p class="text-red-400 text-xs">DAC Curation failed</p>`;
    }
  } catch (err) {
    resContainer.innerHTML = `<p class="text-red-400 text-xs">Network error: ${err.message}</p>`;
  }
}

async function triggerAdversarialCycle() {
  const resContainer = document.getElementById('sec-adv-result');
  resContainer.classList.remove('hidden');
  resContainer.innerHTML = '<p class="text-slate-400 animate-pulse text-xs">Executing Teacher-Guided Adversarial Improvement Cycle...</p>';

  try {
    const res = await fetch(`${API_BASE}/security/adversarial-cycle`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });

    if (res.ok) {
      const rep = await res.json();
      resContainer.innerHTML = `
        <div class="space-y-1 font-mono text-xs text-slate-300">
          <div class="text-cyan-400 font-bold">Adversarial Cycle Complete: ${rep.cycle_id}</div>
          <div>Tests: <strong>${rep.total_tests}</strong> | Passed: <strong class="text-emerald-400">${rep.passed_tests}</strong> | Failed: <strong class="text-amber-400">${rep.failed_tests}</strong> (${rep.pass_rate}% Pass Rate)</div>
          <div>Teacher-Generated Corrective Training Pairs: <strong class="text-white">${rep.corrected_examples_count}</strong></div>
        </div>
      `;
    } else {
      resContainer.innerHTML = `<p class="text-red-400 text-xs">Adversarial Cycle failed</p>`;
    }
  } catch (err) {
    resContainer.innerHTML = `<p class="text-red-400 text-xs">Network error: ${err.message}</p>`;
  }
}

// Initialize on Load
document.addEventListener('DOMContentLoaded', () => {
  checkHealth();
  refreshRecordsList();
  setInterval(checkHealth, 15000);
});
