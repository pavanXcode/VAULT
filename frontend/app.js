/**
 * VAULT Frontend Interactive Client
 */

const API_BASE = '/api';

// Tab Navigation
function switchTab(tabId) {
  ['assistant', 'runs', 'eval', 'new-model'].forEach(id => {
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
  }
}

// Health Status Polling
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

// New Model Pipeline Job
async function handleNewModelSubmit(e) {
  e.preventDefault();
  const tool_name = document.getElementById('nm-tool').value;
  const action = document.getElementById('nm-action').value;
  const dataset = document.getElementById('nm-dataset').value;

  try {
    const res = await fetch(`${API_BASE}/jobs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        tool_name,
        input_parameters: { action, dataset, sample_count: 5 },
      }),
    });
    if (res.ok) {
      alert('Pipeline job created successfully!');
      switchTab('runs');
    } else {
      const err = await res.json();
      alert(`Job submission error: ${JSON.stringify(err)}`);
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

// Initialize on Load
document.addEventListener('DOMContentLoaded', () => {
  checkHealth();
  refreshRecordsList();
  setInterval(checkHealth, 15000);
});
