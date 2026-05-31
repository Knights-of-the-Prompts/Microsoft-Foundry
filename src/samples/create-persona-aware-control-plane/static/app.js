/* eslint-disable */
/**
 * Universal Control Plane — Frontend Application
 * Consumes the FastAPI backend. All data comes from backend APIs.
 * No hardcoded mock data except the static Demo Agent Registry.
 */
(function () {
  'use strict';

  // ── State ────────────────────────────────────────────────────────────
  const State = {
    persona: null,       // { id, name, description, relevant_platforms, default_kpis }
    kpiResult: null,     // last KPI Agent response
    accessResult: null,  // last Access Readiness response (embedded in kpiResult)
    connectors: [],      // loaded once
    tools: [],           // loaded once
  };

  // ── API helpers ──────────────────────────────────────────────────────
  const API = {
    base: '',

    async get(path) {
      const r = await fetch(this.base + path);
      if (!r.ok) {
        const body = await r.text();
        throw new Error(`GET ${path} → ${r.status}: ${body}`);
      }
      return r.json();
    },

    async post(path, data) {
      const r = await fetch(this.base + path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      if (!r.ok) {
        const body = await r.text();
        throw new Error(`POST ${path} → ${r.status}: ${body}`);
      }
      return r.json();
    },
  };

  // ── Toast notifications ──────────────────────────────────────────────
  function toast(msg, type = 'info') {
    const el = document.createElement('div');
    el.className = `toast toast-${type}`;
    el.textContent = msg;
    document.getElementById('toast-container').appendChild(el);
    setTimeout(() => el.remove(), 3500);
  }

  // ── Section → tab mapping (supports old deep-link IDs) ──────────────
  const SECTION_MAP = {
    briefing:          { parent: 'briefing',      tab: 'persona' },
    persona:           { parent: 'briefing',      tab: 'persona' },
    series:            { parent: 'briefing',      tab: 'series' },
    digest:            { parent: 'briefing',      tab: 'digest' },
    integrations:      { parent: 'integrations',  tab: 'connectors' },
    connectors:        { parent: 'integrations',  tab: 'connectors' },
    tools:             { parent: 'integrations',  tab: 'tools' },
    actions:           { parent: 'actions',       tab: 'kpi' },
    kpi:               { parent: 'actions',       tab: 'kpi' },
    'signal-map':      { parent: 'actions',       tab: 'signal-map' },
    access:            { parent: 'actions',       tab: 'access' },
    'access-requests': { parent: 'actions',       tab: 'access-requests' },
    'agent-ideas':     { parent: 'actions',       tab: 'agent-ideas' },
    'agent-requests':  { parent: 'actions',       tab: 'agent-requests' },
    evidence:          { parent: 'evidence',      tab: 'evidence-trail' },
    'evidence-trail':  { parent: 'evidence',      tab: 'evidence-trail' },
    registry:          { parent: 'evidence',      tab: 'registry' },
  };

  // ── Navigation ───────────────────────────────────────────────────────
  function initNav() {
    document.querySelectorAll('.nav-item[data-section]').forEach(link => {
      link.addEventListener('click', e => {
        e.preventDefault();
        navigateTo(link.getAttribute('data-section'));
      });
    });
    document.querySelectorAll('.tab-btn[data-tab]').forEach(btn => {
      btn.addEventListener('click', () => {
        const parentId = btn.closest('.section').id.replace('section-', '');
        const tabId    = btn.getAttribute('data-tab');
        activateTab(parentId, tabId);
        history.replaceState(null, '', `#${tabId}`);
        lazyLoad(tabId);
      });
    });
    const hash = location.hash.replace('#', '') || 'persona';
    navigateTo(hash);
  }

  function navigateTo(sectionId) {
    const entry = SECTION_MAP[sectionId];
    if (!entry) return;
    const { parent, tab } = entry;

    document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
    const parentEl = document.getElementById(`section-${parent}`);
    if (parentEl) parentEl.classList.add('active');

    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    const navLink = document.querySelector(`.nav-item[data-section="${parent}"]`);
    if (navLink) navLink.classList.add('active');

    activateTab(parent, tab);
    history.replaceState(null, '', `#${sectionId}`);
    document.getElementById('main').scrollTop = 0;
    lazyLoad(tab);
  }

  function activateTab(parentSection, tabId) {
    const parentEl = document.getElementById(`section-${parentSection}`);
    if (!parentEl) return;
    parentEl.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    const panel = document.getElementById(`section-${tabId}`);
    if (panel) panel.classList.add('active');
    parentEl.querySelectorAll('.tab-btn').forEach(b => {
      b.classList.toggle('active', b.getAttribute('data-tab') === tabId);
    });
  }

  function lazyLoad(tabId) {
    switch (tabId) {
      case 'persona':          loadPersonas(); break;
      case 'kpi':              resetKpiStepper(); break;
      case 'connectors':       loadConnectors(); break;
      case 'tools':            loadTools(); break;
      case 'access-requests':  loadAccessRequests(); break;
      case 'agent-requests':   loadAgentRequests(); break;
      case 'evidence-trail':   loadEvidence(); break;
      case 'registry':         renderRegistry(); break;
    }
  }

  // Handle links inside content (data-section attributes)
  document.addEventListener('click', e => {
    const link = e.target.closest('[data-section]');
    if (link && !link.classList.contains('nav-item')) {
      e.preventDefault();
      navigateTo(link.getAttribute('data-section'));
    }
  });

  // ── Badge helpers ────────────────────────────────────────────────────
  function modeBadge(mode) {
    const m = (mode || 'mock').toLowerCase();
    const cls = { mock: 'badge-mock', live: 'badge-live', hybrid: 'badge-hybrid' }[m] || 'badge-unknown';
    return `<span class="badge ${cls}">${m.toUpperCase()}</span>`;
  }

  function statusBadge(status) {
    const s = (status || '').toLowerCase().replace(/ /g, '_');
    const map = {
      ready: 'badge-ready',
      partially_ready: 'badge-partial',
      blocked: 'badge-missing',
      connected: 'badge-live',
      configured: 'badge-configured',
      not_configured: 'badge-unknown',
      error: 'badge-error',
      unavailable: 'badge-error',
    };
    const cls = map[s] || 'badge-unknown';
    const label = {
      ready: 'Ready',
      partially_ready: 'Partially Ready',
      blocked: 'Blocked',
      connected: 'Connected',
      configured: 'Configured',
      not_configured: 'Not Configured',
      error: 'Error',
      unavailable: 'Unavailable',
    }[s] || status;
    return `<span class="badge ${cls}">${label}</span>`;
  }

  function accessCheckBadge(status) {
    const s = (status || '').toLowerCase();
    const map = {
      allowed: ['badge-ready', 'Ready'],
      partially_allowed: ['badge-partial', 'Partial'],
      missing_access: ['badge-missing', 'Missing Access'],
      connector_not_configured: ['badge-unknown', 'Not Configured'],
      unknown: ['badge-unknown', 'Unknown'],
    };
    const [cls, label] = map[s] || ['badge-unknown', status];
    return `<span class="badge ${cls}">${label}</span>`;
  }

  function overallAccessBadge(status) {
    const s = (status || '').toLowerCase();
    const map = {
      ready: ['badge-ready', 'Ready'],
      partially_ready: ['badge-partial', 'Partially Ready'],
      blocked: ['badge-missing', 'Blocked'],
    };
    const [cls, label] = map[s] || ['badge-unknown', status];
    return `<span class="badge ${cls}" style="font-size:14px;padding:4px 14px;">${label}</span>`;
  }

  function maturityBadge(level) {
    const map = {
      vague: ['badge-missing', 'Vague'],
      usable: ['badge-partial', 'Usable'],
      well_articulated: ['badge-ready', 'Well Articulated'],
    };
    const [cls, label] = map[(level || '').toLowerCase()] || ['badge-unknown', level];
    return `<span class="badge ${cls}">${label}</span>`;
  }

  function riskBadge(level) {
    const map = {
      low:    ['badge-ready',   'Low Risk'],
      medium: ['badge-partial', 'Medium Risk'],
      high:   ['badge-missing', 'High Risk'],
    };
    const [cls, label] = map[(level || '').toLowerCase()] || ['badge-unknown', level];
    return `<span class="badge ${cls}">${label}</span>`;
  }

  function complexityBadge(level) {
    const map = {
      low:    ['badge-ready',   'Low Complexity'],
      medium: ['badge-partial', 'Medium Complexity'],
      high:   ['badge-missing', 'High Complexity'],
    };
    const [cls, label] = map[(level || '').toLowerCase()] || ['badge-unknown', level];
    return `<span class="badge ${cls}">${label}</span>`;
  }

  function tags(arr, cls = '') {
    if (!arr || !arr.length) return '<span class="text-dim">—</span>';
    return arr.map(t => `<span class="tag ${cls}">${esc(t)}</span>`).join('');
  }

  function esc(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function sensitivityBadge(level) {
    const map = {
      none:       ['badge-ready',   'None'],
      low:        ['badge-mock',    'Low'],
      medium:     ['badge-partial', 'Medium'],
      high:       ['badge-missing', 'High'],
      restricted: ['badge-error',   'Restricted'],
    };
    const [cls, label] = map[(level || '').toLowerCase()] || ['badge-unknown', level];
    return `<span class="badge ${cls}">${label}</span>`;
  }

  // ── Section: Persona ─────────────────────────────────────────────────
  async function loadPersonas() {
    const grid = document.getElementById('persona-cards');
    grid.innerHTML = '<div class="loading-placeholder"><span class="spinner"></span> Loading personas…</div>';
    try {
      const personas = await API.get('/api/personas');
      renderPersonaGrid(personas);
    } catch (err) {
      grid.innerHTML = `<div class="warn-banner">Failed to load personas: ${esc(err.message)}</div>`;
    }
  }

  function renderPersonaGrid(personas) {
    const grid = document.getElementById('persona-cards');
    const ACCOUNTABILITY = {
      compliance_officer: 'Ensures no agent operates outside its approved regulatory and policy scope.',
      cfo:                'Governs agent cost, revenue impact and financial risk at an enterprise level.',
      cto:                'Accountable for platform stability, deployment quality and AI infrastructure.',
      it_manager:         'Responsible for service health, incident resolution and platform reliability.',
      security_officer:   'Owns the threat posture of every agent, integration and data pipeline.',
      business_owner:     'Accountable for agent-driven business outcomes and opportunity conversion.',
      product_owner:      'Governs agent feature delivery, change control and product health.',
      service_owner:      'Responsible for service-level agreements and customer resolution quality.',
    };

    grid.innerHTML = personas.map(p => `
      <div class="persona-card" data-persona-id="${esc(p.id || p.persona_id)}">
        <div class="persona-card-title">${esc(p.name)}</div>
        <div class="persona-card-desc">${esc(p.description || '')}</div>
        <div class="persona-card-platforms">
          ${(p.relevant_platforms || []).map(pl =>
            `<span class="tag">${esc(pl)}</span>`
          ).join('')}
        </div>
      </div>
    `).join('');

    grid.querySelectorAll('.persona-card').forEach(card => {
      card.addEventListener('click', () => {
        const pid = card.getAttribute('data-persona-id');
        const p = personas.find(x => (x.id || x.persona_id) === pid);
        if (p) selectPersona(p, ACCOUNTABILITY);
      });
    });

    // Re-select if we already have a persona
    if (State.persona) {
      const sel = grid.querySelector(`[data-persona-id="${State.persona.id}"]`);
      if (sel) sel.classList.add('selected');
    }
  }

  function selectPersona(p, accountability) {
    State.persona = {
      id: p.id || p.persona_id,
      name: p.name,
      description: p.description,
      relevant_platforms: p.relevant_platforms || [],
      default_kpis: p.default_kpis || [],
    };

    // Mark selected card
    document.querySelectorAll('.persona-card').forEach(c => c.classList.remove('selected'));
    const card = document.querySelector(`[data-persona-id="${State.persona.id}"]`);
    if (card) card.classList.add('selected');

    // Update sidebar chip
    const userIcon = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" style="flex-shrink:0"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>`;
    document.getElementById('sidebar-persona-chip').innerHTML =
      `<span class="persona-chip-label" style="display:flex;align-items:center;gap:6px">${userIcon} ${esc(State.persona.name)}</span>`;

    // Show detail
    showPersonaDetail(State.persona, accountability || {});

    // Update KPI workspace persona label
    document.getElementById('kpi-persona-label').textContent = State.persona.name;

    // Reset the KPI stepper so previous run data is cleared
    resetKpiStepper();

    // Populate KPI examples
    populateKpiExamples();
  }

  function showPersonaDetail(p, accountability) {
    document.getElementById('persona-cards').classList.add('hidden');
    const detail = document.getElementById('persona-detail');
    detail.classList.remove('hidden');

    document.getElementById('pd-name').textContent = p.name;
    document.getElementById('pd-desc').textContent = p.description || '';
    document.getElementById('pd-accountability').textContent =
      accountability[p.id] || p.description || '';

    const kpiList = document.getElementById('pd-kpis');
    kpiList.innerHTML = (p.default_kpis || []).map(k => `
      <li>
        <strong>${esc(k.title || k.kpi_id)}</strong>
        ${k.description ? `<br><span class="text-small">${esc(k.description)}</span>` : ''}
      </li>
    `).join('') || '<li class="text-dim">No default KPIs defined.</li>';

    document.getElementById('pd-platforms').innerHTML =
      (p.relevant_platforms || []).map(pl =>
        `<span class="tag tag-accent">${esc(pl)}</span>`
      ).join('') || '<span class="text-dim">—</span>';
  }

  document.getElementById('pd-change-btn').addEventListener('click', () => {
    document.getElementById('persona-cards').classList.remove('hidden');
    document.getElementById('persona-detail').classList.add('hidden');
  });

  document.getElementById('pd-proceed-btn').addEventListener('click', () => {
    navigateTo('kpi');
  });

  // ── Section: Connectors ──────────────────────────────────────────────
  async function loadConnectors() {
    const grid = document.getElementById('connector-cards');
    if (State.connectors.length > 0) { renderConnectorCards(State.connectors); return; }
    grid.innerHTML = '<div class="loading-placeholder"><span class="spinner"></span> Loading connectors…</div>';
    try {
      const data = await API.get('/api/connectors');
      State.connectors = data;
      renderConnectorCards(data);
    } catch (err) {
      grid.innerHTML = `<div class="warn-banner">Failed to load connectors: ${esc(err.message)}</div>`;
    }
  }

  function renderConnectorCards(connectors) {
    const grid = document.getElementById('connector-cards');
    grid.innerHTML = connectors.map(c => `
      <div class="connector-card" id="cc-${esc(c.id)}">
        <div class="connector-card-header">
          <div class="connector-card-title">${esc(c.name)}</div>
          <div style="display:flex;gap:6px;">
            ${modeBadge(c.mode)}
            ${statusBadge(c.status)}
          </div>
        </div>
        <div class="connector-card-desc">${esc(c.description || '')}</div>
        <div class="connector-meta">
          <div class="connector-meta-row">
            <span class="connector-meta-label">Auth type</span>
            <code>${esc(c.auth_type || 'none')}</code>
          </div>
          ${c.last_checked_at ? `<div class="connector-meta-row">
            <span class="connector-meta-label">Last checked</span>
            <span>${esc(c.last_checked_at)}</span>
          </div>` : ''}
          ${c.error_message ? `<div class="connector-meta-row">
            <span class="connector-meta-label" style="color:var(--red)">Error</span>
            <span style="color:var(--red)">${esc(c.error_message)}</span>
          </div>` : ''}
        </div>
        <div class="connector-signals">
          ${(c.supported_signal_types || []).map(s =>
            `<span class="tag">${esc(s)}</span>`
          ).join('')}
        </div>
        <div class="connector-actions">
          <button class="btn btn-secondary btn-sm connector-configure-btn" data-id="${esc(c.id)}">Configure</button>
          <button class="btn btn-ghost btn-sm connector-test-btn" data-id="${esc(c.id)}">Test</button>
        </div>
      </div>
    `).join('');

    grid.querySelectorAll('.connector-configure-btn').forEach(btn => {
      btn.addEventListener('click', () => openConfigModal(btn.getAttribute('data-id'), connectors));
    });
    grid.querySelectorAll('.connector-test-btn').forEach(btn => {
      btn.addEventListener('click', () => testConnector(btn.getAttribute('data-id')));
    });
  }

  function openConfigModal(connectorId, connectors) {
    const c = connectors.find(x => x.id === connectorId);
    if (!c) return;
    document.getElementById('cfg-connector-id').value = connectorId;
    document.getElementById('config-modal-title').textContent = `Configure — ${c.name}`;
    document.getElementById('cfg-mode').value = c.mode || 'mock';
    document.getElementById('cfg-base-url').value = c.base_url || '';
    document.getElementById('config-modal').classList.remove('hidden');
  }

  document.getElementById('config-modal-close').addEventListener('click', closeConfigModal);
  document.getElementById('config-cancel').addEventListener('click', closeConfigModal);
  document.querySelector('.modal-backdrop').addEventListener('click', closeConfigModal);

  function closeConfigModal() {
    document.getElementById('config-modal').classList.add('hidden');
  }

  document.getElementById('config-form').addEventListener('submit', async e => {
    e.preventDefault();
    const cid = document.getElementById('cfg-connector-id').value;
    const payload = {
      mode:     document.getElementById('cfg-mode').value,
      base_url: document.getElementById('cfg-base-url').value || null,
      tenant_id:document.getElementById('cfg-tenant-id').value || null,
      client_id:document.getElementById('cfg-client-id').value || null,
    };
    try {
      await API.post(`/api/connectors/${encodeURIComponent(cid)}/configure`, payload);
      toast(`Connector ${cid} configured.`, 'success');
      State.connectors = [];
      closeConfigModal();
      loadConnectors();
    } catch (err) {
      toast(`Configuration failed: ${err.message}`, 'error');
    }
  });

  async function testConnector(connectorId) {
    try {
      toast(`Testing ${connectorId}…`);
      const result = await API.post(`/api/connectors/${encodeURIComponent(connectorId)}/test`, {});
      toast(`${connectorId}: ${result.status || 'ok'}`, 'success');
      State.connectors = [];
      loadConnectors();
    } catch (err) {
      toast(`Test failed: ${err.message}`, 'error');
    }
  }

  // ── Section: Tools ───────────────────────────────────────────────────
  async function loadTools() {
    const wrap = document.getElementById('tools-table-wrap');
    if (State.tools.length > 0) { renderToolsTable(State.tools); return; }
    wrap.innerHTML = '<div class="loading-placeholder"><span class="spinner"></span> Loading tools…</div>';
    try {
      const tools = await API.get('/api/tools');
      State.tools = tools;

      // Populate platform filter
      const sel = document.getElementById('tool-platform-filter');
      const platforms = [...new Set(tools.map(t => t.platform_id))].sort();
      platforms.forEach(p => {
        const opt = document.createElement('option');
        opt.value = p; opt.textContent = p;
        sel.appendChild(opt);
      });

      renderToolsTable(tools);
    } catch (err) {
      wrap.innerHTML = `<div class="warn-banner">Failed to load tools: ${esc(err.message)}</div>`;
    }
  }

  function renderToolsTable(tools) {
    const wrap = document.getElementById('tools-table-wrap');
    if (!tools.length) {
      wrap.innerHTML = '<div class="queue-empty">No tools available. Configure at least one connector.</div>';
      return;
    }
    wrap.innerHTML = `
      <div class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>Tool</th>
              <th>Platform</th>
              <th>Signal Types</th>
              <th>Required Scopes</th>
              <th>Required Roles</th>
              <th>Actions</th>
              <th>Sensitivity</th>
              <th>Mode</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody id="tools-tbody">
          </tbody>
        </table>
      </div>`;
    renderToolsBody(tools);

    document.getElementById('tool-filter').addEventListener('input', filterTools);
    document.getElementById('tool-platform-filter').addEventListener('change', filterTools);
  }

  function filterTools() {
    const text = (document.getElementById('tool-filter').value || '').toLowerCase();
    const platform = document.getElementById('tool-platform-filter').value;
    const filtered = State.tools.filter(t => {
      const matchText = !text ||
        t.name.toLowerCase().includes(text) ||
        (t.platform_id || '').toLowerCase().includes(text) ||
        (t.signal_types || []).some(s => s.toLowerCase().includes(text));
      const matchPlatform = !platform || t.platform_id === platform;
      return matchText && matchPlatform;
    });
    renderToolsBody(filtered);
  }

  function renderToolsBody(tools) {
    const tbody = document.getElementById('tools-tbody');
    if (!tbody) return;
    tbody.innerHTML = tools.map(t => `
      <tr>
        <td>
          <div style="font-weight:700;">${esc(t.name)}</div>
          <div class="text-small">${esc(t.id)}</div>
        </td>
        <td><span class="tag">${esc(t.platform_id)}</span></td>
        <td>${tags(t.signal_types)}</td>
        <td>${tags(t.required_scopes, 'tag-accent')}</td>
        <td>${tags(t.required_roles, 'tag-accent')}</td>
        <td>${tags(t.supported_actions)}</td>
        <td>${sensitivityBadge(t.sensitive_data_level)}</td>
        <td>${modeBadge(t.source_mode)}</td>
        <td>${t.enabled
          ? '<span class="badge badge-ready">Enabled</span>'
          : '<span class="badge badge-unknown">Disabled</span>'}</td>
      </tr>
    `).join('');
  }

  // ── Section: KPI Workspace (Stepper) ────────────────────────────────

  // Stepper state
  const KpiStepper = {
    currentStep: 1,
    sessionId: null,
    challengeData: null,
    formalizedKpi: null,
    controlPackage: null,
  };

  function resetKpiStepper() {
    KpiStepper.currentStep = 1;
    KpiStepper.sessionId = null;
    KpiStepper.challengeData = null;
    KpiStepper.formalizedKpi = null;
    KpiStepper.controlPackage = null;
    // Clear rendered content
    const clearIds = [
      'challenge-maturity-row', 'challenge-missing', 'challenge-suggested',
      'challenge-questions-form', 'formalized-kpi-card',
      'control-package-content', 'kpi-actions-content',
    ];
    clearIds.forEach(id => {
      const el = document.getElementById(id);
      if (el) el.innerHTML = '';
    });
    // Reset draft input
    const draft = document.getElementById('kpi-draft-input');
    if (draft) draft.value = '';
    // Reset challenge button state
    const btn = document.getElementById('kpi-challenge-btn');
    if (btn) { btn.disabled = false; btn.innerHTML = 'Challenge KPI →'; }
    setKpiStep(1);
  }

  function setKpiStep(step) {
    KpiStepper.currentStep = step;
    // Update step panels
    for (let i = 1; i <= 5; i++) {
      const panel = document.getElementById(`kpi-step-${i}`);
      if (panel) panel.classList.toggle('active', i === step);
    }
    // Update stepper indicators
    document.querySelectorAll('.kpi-step').forEach(el => {
      const n = parseInt(el.getAttribute('data-step'), 10);
      el.classList.remove('active', 'completed');
      if (n === step) el.classList.add('active');
      else if (n < step) el.classList.add('completed');
    });
    document.querySelectorAll('.kpi-step-connector').forEach((el, i) => {
      el.classList.remove('active', 'completed');
      if (i + 1 < step) el.classList.add('completed');
      else if (i + 1 === step - 1) el.classList.add('active');
    });
  }

  function populateKpiExamples() {
    if (!State.persona) return;
    const examples = State.persona.default_kpis || [];
    const row = document.getElementById('kpi-examples');
    if (!row) return;
    row.innerHTML = examples.slice(0, 4).map(k =>
      `<span class="tag tag-clickable" data-kpi="${esc(k.title || k.description || '')}">
        ${esc(k.title || k.description || k.kpi_id)}
      </span>`
    ).join('') || '<span class="text-dim">Select a persona to see examples.</span>';

    row.querySelectorAll('[data-kpi]').forEach(el => {
      el.addEventListener('click', () => {
        const input = document.getElementById('kpi-draft-input');
        if (input) input.value = el.getAttribute('data-kpi');
      });
    });
  }

  // Step 1 → Step 2: Challenge
  document.getElementById('kpi-challenge-btn').addEventListener('click', async () => {
    if (!State.persona) {
      toast('Select a persona first.', 'error');
      navigateTo('persona');
      return;
    }
    const draftInput = document.getElementById('kpi-draft-input');
    const draftKpi = (draftInput?.value || '').trim();
    if (!draftKpi) {
      toast('Enter a draft KPI first.', 'error');
      return;
    }
    const btn = document.getElementById('kpi-challenge-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Challenging…';
    try {
      const data = await API.post('/api/kpi-agent/challenge', {
        persona_id: State.persona.id,
        draft_kpi: draftKpi,
      });
      KpiStepper.sessionId = data.session_id;
      KpiStepper.challengeData = data;
      renderChallengeStep(data);
      setKpiStep(2);
      toast('KPI challenged — review the assessment below.', 'success');
    } catch (err) {
      toast(`Challenge failed: ${err.message}`, 'error');
    } finally {
      btn.disabled = false;
      btn.innerHTML = 'Challenge KPI →';
    }
  });

  function renderChallengeStep(data) {
    // Maturity row
    const maturityMap = {
      vague:            ['badge-missing', 'Vague — insufficient for control plane use'],
      usable:           ['badge-partial', 'Usable — address the questions below to strengthen it'],
      well_articulated: ['badge-ready', 'Well Articulated — ready for formalization'],
      control_ready:    ['badge-ready', 'Control Ready'],
    };
    const [cls, label] = maturityMap[(data.maturity_level || '').toLowerCase()] || ['badge-unknown', data.maturity_level];
    const conf = Math.round((data.confidence_score || 0) * 100);
    document.getElementById('challenge-maturity-row').innerHTML = `
      <span class="badge ${cls}">${esc(label)}</span>
      <span class="text-small" style="color:var(--text-3)">Confidence: ${conf}%</span>
    `;

    // Missing fields
    const missing = data.missing_fields || [];
    const missingEl = document.getElementById('challenge-missing');
    if (missing.length) {
      missingEl.classList.remove('hidden');
      missingEl.innerHTML = `<strong>Missing fields</strong> ${missing.map(f => `<span class="tag">${esc(f)}</span>`).join(' ')}`;
    } else {
      missingEl.classList.add('hidden');
    }

    // Suggested KPI
    const suggested = data.suggested_formalized_kpi || {};
    const suggestedEl = document.getElementById('challenge-suggested');
    if (suggested.title || suggested.outcome_statement) {
      suggestedEl.classList.remove('hidden');
      suggestedEl.innerHTML = `
        <strong>Suggested formalized KPI</strong>
        <p>${esc(suggested.outcome_statement || suggested.title || '')}</p>
      `;
    } else {
      suggestedEl.classList.add('hidden');
    }

    // Questions form
    const questions = data.challenge_questions || [];
    const form = document.getElementById('challenge-questions-form');
    form.innerHTML = questions.map((q, i) => `
      <div class="challenge-question-item">
        <label for="cq-${i}">${esc(q)}</label>
        <input type="text" id="cq-${i}" data-question-index="${i}"
          placeholder="Your answer (optional)" autocomplete="off">
      </div>
    `).join('');
  }

  document.getElementById('kpi-back-to-draft-btn').addEventListener('click', () => setKpiStep(1));

  // Step 2 → Step 3: Formalize
  document.getElementById('kpi-formalize-btn').addEventListener('click', async () => {
    if (!State.persona || !KpiStepper.sessionId) return;
    const draftKpi = document.getElementById('kpi-draft-input')?.value?.trim() || '';
    const questions = KpiStepper.challengeData?.challenge_questions || [];

    // Collect answers from form inputs
    const answers = {};
    const answerMap = {
      0: 'business_outcome', 1: 'metric', 2: 'target', 3: 'timeframe',
      4: 'scope', 5: 'evidence_standard', 6: 'risk_tolerance',
    };
    questions.forEach((_, i) => {
      const el = document.getElementById(`cq-${i}`);
      if (el && el.value.trim()) {
        const key = answerMap[i] || `answer_${i}`;
        answers[key] = el.value.trim();
      }
    });

    const btn = document.getElementById('kpi-formalize-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Formalizing…';
    try {
      const data = await API.post('/api/kpi-agent/formalize', {
        session_id: KpiStepper.sessionId,
        persona_id: State.persona.id,
        draft_kpi: draftKpi,
        answers,
      });
      KpiStepper.formalizedKpi = data.formalized_kpi;
      renderFormalizedKpiCard(data.formalized_kpi, data.maturity_level, data.confidence_score);
      setKpiStep(3);
      toast('KPI formalized.', 'success');
    } catch (err) {
      toast(`Formalization failed: ${err.message}`, 'error');
    } finally {
      btn.disabled = false;
      btn.innerHTML = 'Formalize KPI →';
    }
  });

  function renderFormalizedKpiCard(kpi, maturity, confidence) {
    const conf = Math.round((confidence || kpi?.confidence_score || 0) * 100);
    const confColor = conf >= 75 ? 'var(--green)' : conf >= 45 ? 'var(--amber)' : 'var(--red)';
    const maturityMap = {
      vague:            ['badge-missing', 'Vague'],
      usable:           ['badge-partial', 'Usable'],
      well_articulated: ['badge-ready', 'Well Articulated'],
      control_ready:    ['badge-ready', 'Control Ready'],
    };
    const [mCls, mLabel] = maturityMap[(maturity || '').toLowerCase()] || ['badge-unknown', maturity];
    const successCriteria = kpi?.success_criteria || [];
    const tradeoffs = kpi?.tradeoffs || [];
    document.getElementById('formalized-kpi-card').innerHTML = `
      <div class="fkpi-title">${esc(kpi?.title || '—')}</div>
      <div class="fkpi-outcome">${esc(kpi?.outcome_statement || '—')}</div>
      <div class="fkpi-grid">
        <div class="fkpi-field"><div class="fkpi-field-label">Metric</div><div class="fkpi-field-value">${esc(kpi?.metric || '—')}</div></div>
        <div class="fkpi-field"><div class="fkpi-field-label">Target</div><div class="fkpi-field-value">${esc(kpi?.target || '—')}</div></div>
        <div class="fkpi-field"><div class="fkpi-field-label">Timeframe</div><div class="fkpi-field-value">${esc(kpi?.timeframe || '—')}</div></div>
        <div class="fkpi-field"><div class="fkpi-field-label">Scope</div><div class="fkpi-field-value">${esc(kpi?.scope || '—')}</div></div>
        <div class="fkpi-field"><div class="fkpi-field-label">Evidence Standard</div><div class="fkpi-field-value">${esc(kpi?.evidence_standard || '—')}</div></div>
        <div class="fkpi-field"><div class="fkpi-field-label">Risk Tolerance</div><div class="fkpi-field-value">${esc(kpi?.risk_tolerance || '—')}</div></div>
      </div>
      ${successCriteria.length ? `
        <div class="fkpi-list-section">
          <div class="fkpi-list-section-label">Success Criteria</div>
          <ul>${successCriteria.map(c => `<li>${esc(c)}</li>`).join('')}</ul>
        </div>` : ''}
      ${tradeoffs.length ? `
        <div class="fkpi-list-section" style="margin-top:10px;">
          <div class="fkpi-list-section-label">Trade-offs</div>
          <ul>${tradeoffs.map(t => `<li>${esc(t)}</li>`).join('')}</ul>
        </div>` : ''}
      <div class="fkpi-confidence">
        <span class="badge ${mCls}">${mLabel}</span>
        <span style="color:${confColor};font-weight:600;">${conf}% confidence</span>
      </div>
    `;
  }

  document.getElementById('kpi-back-to-challenge-btn').addEventListener('click', () => setKpiStep(2));

  // Step 3 → Step 4: Compose Control Package
  document.getElementById('kpi-compose-btn').addEventListener('click', async () => {
    if (!State.persona || !KpiStepper.formalizedKpi) return;
    const btn = document.getElementById('kpi-compose-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Composing…';
    try {
      const data = await API.post('/api/kpi-agent/control-package', {
        persona_id: State.persona.id,
        formalized_kpi: KpiStepper.formalizedKpi,
        mode: 'mock',
      });
      KpiStepper.controlPackage = data.control_package;

      // Also run the legacy interpret endpoint so signal map, access and digest are populated
      const legacy = await API.post('/api/kpi-agent/interpret', {
        persona_id: State.persona.id,
        kpi: KpiStepper.formalizedKpi.title || null,
        mode: 'mock',
      });
      State.kpiResult = legacy;
      State.accessResult = {
        overall_status: legacy.access_readiness_summary?.overall_status,
        access_check_results: legacy.access_check_results || [],
        access_gaps: legacy.access_gaps || [],
        recommended_access_requests: legacy.recommended_access_requests || [],
      };
      renderSignalMap(legacy);
      renderAccess(legacy);
      renderDigest(legacy);
      renderAgentIdeas(legacy);

      renderControlPackage(data.control_package);
      setKpiStep(4);
      toast('Control package composed.', 'success');
    } catch (err) {
      toast(`Composition failed: ${err.message}`, 'error');
    } finally {
      btn.disabled = false;
      btn.innerHTML = 'Compose Control Package →';
    }
  });

  function renderControlPackage(pkg) {
    const whatYouGet = pkg.what_you_get || [];
    const whatYouNeed = pkg.what_you_need || [];
    const conf = Math.round((pkg.confidence_score || 0) * 100);
    const confColor = conf >= 75 ? 'var(--green)' : conf >= 45 ? 'var(--amber)' : 'var(--red)';

    const accessSummary = pkg.access_readiness_summary || {};
    const connectorSummary = pkg.connector_readiness_summary || {};

    const missingConnectors = accessSummary.missing_connectors || [];
    const readyConnectors = accessSummary.ready_connectors || [];

    document.getElementById('control-package-content').innerHTML = `
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:20px;flex-wrap:wrap;">
        <span class="badge badge-mock" style="font-size:12px;padding:4px 12px;">Control Package</span>
        <span style="font-size:12px;color:${confColor};font-weight:600;">${conf}% confidence</span>
        ${overallAccessBadge(accessSummary.overall_status || 'unknown')}
      </div>

      <div class="control-package-columns">
        <div class="control-package-column">
          <div class="control-column-title">
            <span class="col-icon"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg></span>
            What you will get
          </div>
          <ul class="control-item-list">
            ${whatYouGet.map(item => `<li>${esc(item)}</li>`).join('')}
          </ul>
        </div>
        <div class="control-package-column">
          <div class="control-column-title">
            <span class="col-icon" style="color:var(--amber)"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z"/></svg></span>
            What you need
          </div>
          <ul class="control-item-list">
            ${whatYouNeed.map(item => `<li>${esc(item)}</li>`).join('')}
          </ul>
        </div>
      </div>

      <!-- Connector readiness -->
      <div class="cp-details-section">
        <div class="cp-details-title" onclick="this.nextElementSibling.classList.toggle('expanded')">
          Connector Readiness
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="6 9 12 15 18 9"/></svg>
        </div>
        <div class="cp-details-body">
          ${Object.entries(connectorSummary).map(([plat, info]) => `
            <div class="cp-readiness-row">
              <span class="cp-readiness-name">${esc(plat)}</span>
              ${info.available
                ? `<span class="badge badge-ready">${info.tool_count} tool(s) available</span>`
                : `<span class="badge badge-missing">Not configured</span>`}
            </div>
          `).join('') || '<div class="text-dim text-small">No connector data.</div>'}
        </div>
      </div>

      <!-- Access readiness -->
      <div class="cp-details-section">
        <div class="cp-details-title" onclick="this.nextElementSibling.classList.toggle('expanded')">
          Access Readiness
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="6 9 12 15 18 9"/></svg>
        </div>
        <div class="cp-details-body">
          ${readyConnectors.length ? readyConnectors.map(c => `
            <div class="cp-readiness-row">
              <span class="cp-readiness-name">${esc(c)}</span>
              <span class="badge badge-ready">Access available</span>
            </div>
          `).join('') : ''}
          ${missingConnectors.length ? missingConnectors.map(c => `
            <div class="cp-readiness-row">
              <span class="cp-readiness-name">${esc(c)}</span>
              <span class="badge badge-missing">Access missing</span>
            </div>
          `).join('') : ''}
          ${!readyConnectors.length && !missingConnectors.length
            ? '<div class="text-dim text-small">No access check data.</div>' : ''}
        </div>
      </div>

      <!-- Required signals/tools/evidence behind view details -->
      <div class="cp-details-section">
        <div class="cp-details-title" onclick="this.nextElementSibling.classList.toggle('expanded')">
          View Details — Signals, Tools &amp; Evidence
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="6 9 12 15 18 9"/></svg>
        </div>
        <div class="cp-details-body">
          <div class="gap-meta-grid" style="font-size:12px;margin-top:8px;">
            <div>
              <div class="gap-meta-label">Required Signals</div>
              <div class="tag-row mt-sm">${tags(pkg.required_signals, 'tag-accent')}</div>
            </div>
            <div>
              <div class="gap-meta-label">Required Connectors</div>
              <div class="tag-row mt-sm">${tags(pkg.required_connectors)}</div>
            </div>
            <div>
              <div class="gap-meta-label">Required Tools</div>
              <div class="tag-row mt-sm">${tags((pkg.required_tools || []).slice(0, 8))}</div>
            </div>
            <div>
              <div class="gap-meta-label">Required Evidence</div>
              <ul style="margin:6px 0 0 16px;font-size:12px;color:var(--text-2);line-height:1.7;">
                ${(pkg.required_evidence || []).map(e => `<li>${esc(e)}</li>`).join('')}
              </ul>
            </div>
          </div>
          ${pkg.limitations?.length ? `
            <div style="margin-top:12px;">
              <div class="gap-meta-label" style="color:var(--amber)">Limitations / Evidence Gaps</div>
              <ul style="margin:6px 0 0 16px;font-size:12px;color:var(--amber);line-height:1.7;">
                ${pkg.limitations.map(l => `<li>${esc(l)}</li>`).join('')}
              </ul>
            </div>` : ''}
        </div>
      </div>
    `;
  }

  document.getElementById('kpi-back-to-formalize-btn').addEventListener('click', () => setKpiStep(3));

  // Step 4 → Step 5: Actions
  document.getElementById('kpi-to-actions-btn').addEventListener('click', () => {
    if (!KpiStepper.controlPackage) return;
    renderKpiActions(KpiStepper.controlPackage);
    setKpiStep(5);
  });

  function renderKpiActions(pkg) {
    const actions = pkg.recommended_actions || [];
    const agentIdeas = pkg.agent_ideas || [];
    document.getElementById('kpi-actions-content').innerHTML = `
      <h3 style="font-size:14px;font-weight:700;margin-bottom:18px;">Recommended Actions</h3>
      <div class="action-cards">
        ${actions.map(a => `
          <div class="action-card">
            <div class="action-card-header">
              <div class="action-card-title">${esc(a.action || a)}</div>
              ${a.risk ? `<span class="badge ${riskBadgeClass(a.risk)}" title="${esc(a.risk)}">${esc((a.risk || '').split(/[\s—–-]/)[0])} risk</span>` : ''}
            </div>
            <div class="action-card-body">
              ${a.why ? `<div class="action-meta-field"><div class="action-meta-label">Why</div><div class="action-meta-value">${esc(a.why)}</div></div>` : ''}
              ${a.impact ? `<div class="action-meta-field"><div class="action-meta-label">Expected Impact</div><div class="action-meta-value">${esc(a.impact)}</div></div>` : ''}
              ${a.approver ? `<div class="action-meta-field"><div class="action-meta-label">Required Approver</div><div class="action-meta-value">${esc(a.approver)}</div></div>` : ''}
              ${a.evidence_created ? `<div class="action-meta-field"><div class="action-meta-label">Evidence Created</div><div class="action-meta-value"><code>${esc(a.evidence_created)}</code></div></div>` : ''}
            </div>
          </div>
        `).join('')}
      </div>
      ${agentIdeas.length ? `
        <h3 style="font-size:14px;font-weight:700;margin:28px 0 14px;">Agent Ideas</h3>
        <div class="idea-cards">
          ${agentIdeas.map(idea => `
            <div class="idea-card">
              <div class="idea-card-header">
                <div class="idea-card-title">${esc(idea.title)}</div>
                <span class="badge ${riskBadgeClass(idea.risk_level)}">${esc(idea.risk_level)} risk</span>
              </div>
              <div class="idea-card-section"><strong>Problem</strong> ${esc(idea.problem_statement || '—')}</div>
              <div class="idea-card-section"><strong>Expected Value</strong> ${esc(idea.expected_value || '—')}</div>
              <div class="idea-card-footer">
                <button class="btn btn-primary btn-sm idea-request-btn"
                  data-idea="${esc(encodeURIComponent(JSON.stringify({ id: idea.id, title: idea.title })))}">
                  Request this agent
                </button>
              </div>
            </div>
          `).join('')}
        </div>` : ''}
    `;

    document.getElementById('kpi-actions-content').querySelectorAll('.idea-request-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const idea = JSON.parse(decodeURIComponent(btn.getAttribute('data-idea')));
        submitAgentRequest(idea);
      });
    });
  }

  function riskBadgeClass(level) {
    // Risk strings may contain extra context after a dash e.g. "High — token revocation…"
    const first = (level || '').toLowerCase().split(/[\s—–-]/)[0].trim();
    const map = { low: 'badge-ready', medium: 'badge-partial', high: 'badge-missing' };
    return map[first] || 'badge-unknown';
  }

  document.getElementById('kpi-back-to-package-btn').addEventListener('click', () => setKpiStep(4));
  document.getElementById('kpi-view-access-btn').addEventListener('click', () => navigateTo('access'));
  document.getElementById('kpi-view-digest-btn').addEventListener('click', () => navigateTo('digest'));

  // ── Section: KPI Workspace (Legacy interpret — kept for Signal Map etc.) ──
  // runKPI is called internally after control package composition to populate
  // signal map, access and digest panels.
  async function runKPI(kpiText) {
    if (!State.persona) return;
    try {
      const result = await API.post('/api/kpi-agent/interpret', {
        persona_id: State.persona.id,
        kpi: kpiText || null,
        mode: 'mock',
      });
      State.kpiResult = result;
      State.accessResult = {
        overall_status: result.access_readiness_summary?.overall_status,
        access_check_results: result.access_check_results || [],
        access_gaps: result.access_gaps || [],
        recommended_access_requests: result.recommended_access_requests || [],
      };
      renderKPIResult(result);
      renderSignalMap(result);
      renderAccess(result);
      renderDigest(result);
      renderAgentIdeas(result);
    } catch (err) {
      // non-fatal — stepper continues
    }
  }

  function renderKPIResult(r) {
    document.getElementById('kpi-result').classList.remove('hidden');

    // Maturity
    document.getElementById('kpi-maturity-badge').innerHTML = maturityBadge(r.maturity_level);

    // Vague warning
    const vague = r.maturity_level === 'vague';
    document.getElementById('kpi-vague-warning').classList.toggle('hidden', !vague);

    // Normalized KPI
    const nk = r.normalized_kpi || {};
    document.getElementById('kpi-normalized').innerHTML = `
      <div style="font-size:14px;font-weight:600;margin-bottom:6px;">${esc(nk.metric || r.original_kpi || '—')}</div>
      ${nk.target ? `<div class="text-small">Target: ${esc(nk.target)}</div>` : ''}
      ${nk.time_frame ? `<div class="text-small">Time frame: ${esc(nk.time_frame)}</div>` : ''}
    `;

    // Confidence
    const conf = Math.round((r.confidence_score || 0) * 100);
    const confColor = conf >= 75 ? 'var(--green)' : conf >= 45 ? 'var(--amber)' : 'var(--red)';
    document.getElementById('kpi-confidence').innerHTML = `
      <div class="confidence-label" style="color:${confColor}">${conf}%</div>
      <div class="confidence-bar">
        <div class="confidence-fill" style="width:${conf}%;background:${confColor}"></div>
      </div>
    `;

    // Clarifications
    const clarifications = r.clarification_questions || [];
    const clarifBlock = document.getElementById('kpi-clarifications');
    clarifBlock.classList.toggle('hidden', !clarifications.length);
    document.getElementById('kpi-clarification-list').innerHTML =
      clarifications.map(q => `<li>${esc(q)}</li>`).join('');

    // Signals & platforms
    document.getElementById('kpi-signals').innerHTML = tags(r.required_signals, 'tag-accent');
    document.getElementById('kpi-platforms').innerHTML = tags(r.selected_platforms);

    // Tools used
    const toolsUsed = (r.available_tools_used || []).map(t =>
      typeof t === 'string' ? t : (t.name || t.id || JSON.stringify(t))
    );
    document.getElementById('kpi-tools-used').innerHTML = tags(toolsUsed);

    // Access summary
    const summary = r.access_readiness_summary || {};
    const statusStr = summary.overall_status || 'unknown';
    document.getElementById('kpi-access-summary').innerHTML = `
      <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
        ${overallAccessBadge(statusStr)}
        <span class="text-small">${summary.checked_signals || 0} signals checked · ${summary.access_gaps_count || 0} gap(s) · ${summary.recommended_requests_count || 0} request(s) recommended</span>
      </div>
      ${summary.access_gaps_count > 0
        ? `<div class="warn-banner mt-sm" style="margin-bottom:0">This KPI requires signals that are not available with your current access.</div>`
        : ''}
    `;
  }

  // ── Section: Signal Map ──────────────────────────────────────────────
  function renderSignalMap(r) {
    const content = document.getElementById('signal-map-content');
    if (!r) {
      content.innerHTML = '<div class="empty-state"><p>No KPI interpreted yet.</p></div>';
      return;
    }
    const signals = r.required_signals || [];
    const platforms = r.selected_platforms || [];
    const toolsUsed = (r.available_tools_used || []).map(t =>
      typeof t === 'string' ? t : (t.name || t.id || ''));
    const gaps = (r.access_gaps || []).map(g => g.platform_id);

    content.innerHTML = `
      <div class="signal-map-chain">
        <div class="signal-chain-step">
          <div class="chain-connector">
            <div class="chain-dot"></div>
            <div class="chain-line"></div>
          </div>
          <div class="chain-body">
            <div class="chain-body-title">KPI</div>
            <div class="chain-body-content" style="font-weight:600;">
              ${esc(r.normalized_kpi?.metric || r.original_kpi || '—')}
            </div>
          </div>
        </div>

        <div class="signal-chain-step">
          <div class="chain-connector">
            <div class="chain-dot"></div>
            <div class="chain-line"></div>
          </div>
          <div class="chain-body">
            <div class="chain-body-title">Required Signals (${signals.length})</div>
            <div class="chain-body-content tag-row">${tags(signals, 'tag-accent')}</div>
          </div>
        </div>

        <div class="signal-chain-step">
          <div class="chain-connector">
            <div class="chain-dot"></div>
            <div class="chain-line"></div>
          </div>
          <div class="chain-body">
            <div class="chain-body-title">Platform Connectors (${platforms.length})</div>
            <div class="chain-body-content tag-row">${tags(platforms)}</div>
          </div>
        </div>

        <div class="signal-chain-step">
          <div class="chain-connector">
            <div class="chain-dot"></div>
            <div class="chain-line"></div>
          </div>
          <div class="chain-body">
            <div class="chain-body-title">Tools Used (${toolsUsed.length})</div>
            <div class="chain-body-content tag-row">${tags(toolsUsed)}</div>
          </div>
        </div>

        <div class="signal-chain-step">
          <div class="chain-connector">
            <div class="chain-dot" style="background:${gaps.length > 0 ? 'var(--red)' : 'var(--green)'}"></div>
          </div>
          <div class="chain-body" style="border-color:${gaps.length > 0 ? 'var(--red)' : 'var(--green)'};">
            <div class="chain-body-title">Required Access</div>
            <div class="chain-body-content">
              ${overallAccessBadge(r.access_readiness_summary?.overall_status || 'unknown')}
              ${gaps.length > 0
                ? `<div class="mt-sm text-small" style="color:var(--red)">
                    Access gaps on: ${gaps.map(g => `<code>${esc(g)}</code>`).join(', ')}
                   </div>`
                : '<div class="mt-sm text-small" style="color:var(--green)">All required access is available.</div>'}
              <button class="btn btn-secondary btn-sm mt-sm" onclick="window.navigateTo('access')">
                View Access Readiness Details →
              </button>
            </div>
          </div>
        </div>
      </div>
    `;
  }

  // expose navigateTo for inline onclick
  window.navigateTo = navigateTo;

  // ── Section: Access Readiness ────────────────────────────────────────
  function renderAccess(r) {
    const content = document.getElementById('access-content');
    if (!r || !r.access_check_results) {
      content.innerHTML = '<div class="empty-state"><p>No KPI interpreted yet. Go to <a data-section="kpi">KPI Workspace</a> first.</p></div>';
      return;
    }

    const summary = r.access_readiness_summary || {};
    const checks = r.access_check_results || [];
    const gaps = r.access_gaps || [];
    const recommendations = r.recommended_access_requests || [];
    const persona = State.persona || {};

    content.innerHTML = `
      <!-- Overview -->
      <div class="access-overview">
        <div>
          <div class="access-overview-label">Overall Access Status</div>
          <div class="access-status-large mt-sm">
            ${overallAccessBadge(summary.overall_status || 'unknown')}
          </div>
        </div>
        <div class="access-stats" style="margin-left:auto;">
          <div class="access-stat">
            <div class="access-stat-num">${checks.length}</div>
            <div class="access-stat-label">Signals Checked</div>
          </div>
          <div class="access-stat">
            <div class="access-stat-num" style="color:${gaps.length > 0 ? 'var(--red)' : 'var(--green)'}">${gaps.length}</div>
            <div class="access-stat-label">Access Gaps</div>
          </div>
          <div class="access-stat">
            <div class="access-stat-num" style="color:${recommendations.length > 0 ? 'var(--amber)' : 'var(--green)'}">${recommendations.length}</div>
            <div class="access-stat-label">Requests Recommended</div>
          </div>
        </div>
      </div>

      ${gaps.length > 0 ? `
        <div class="warn-banner">
          This KPI requires signals that are not available with <strong>${esc(persona.name || 'this persona')}</strong>'s current access.
          Review the access gaps below and request the minimum permissions required.
        </div>
      ` : '<div class="info-banner">All required access is available for this persona and KPI.</div>'}

      <!-- Per-signal checks -->
      <h3 style="font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--text-3);margin-bottom:12px;">
        Access Check Results
      </h3>
      <div class="access-check-list" id="access-check-list">
        ${checks.map(check => renderAccessCheckItem(check)).join('')}
      </div>

      ${gaps.length > 0 ? `
        <hr class="divider">
        <h3 style="font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--red);margin-bottom:12px;">
          Access Gaps
        </h3>
        ${gaps.map(gap => renderGapCard(gap, recommendations)).join('')}
      ` : ''}

      ${recommendations.length > 0 ? `
        <hr class="divider">
        <h3 style="font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--amber);margin-bottom:12px;">
          Recommended Access Requests
        </h3>
        <div class="info-banner">
          The control plane never auto-grants access.
          The following are least-privilege request recommendations for human review and approval.
        </div>
        ${recommendations.map(req => renderAccessRequestTemplate(req)).join('')}
      ` : ''}
    `;

    // Attach request buttons
    content.querySelectorAll('.request-access-btn').forEach(btn => {
      btn.addEventListener('click', () => submitAccessRequest(
        JSON.parse(decodeURIComponent(btn.getAttribute('data-req')))
      ));
    });
  }

  function renderAccessCheckItem(check) {
    const missingScopes   = check.missing_scopes   || [];
    const missingRoles    = check.missing_roles    || [];
    const missingActions  = check.missing_actions  || [];
    const hasMissing = missingScopes.length || missingRoles.length || missingActions.length;

    return `
      <div class="access-check-item">
        <div class="access-check-header">
          ${accessCheckBadge(check.status)}
          <span class="access-check-name">${esc(check.tool_name || check.connector_id)}</span>
          <span class="tag">${esc(check.platform_id)}</span>
          ${sensitivityBadge(check.required_access?.sensitive_data_level || 'low')}
        </div>
        <div class="access-check-detail">${esc(check.explanation || '')}</div>
        ${hasMissing ? `
          <div class="access-check-missing">
            ${missingScopes.map(s => `<span class="missing-item">scope: ${esc(s)}</span>`).join('')}
            ${missingRoles.map(r => `<span class="missing-item">role: ${esc(r)}</span>`).join('')}
            ${missingActions.map(a => `<span class="missing-item">action: ${esc(a)}</span>`).join('')}
          </div>
        ` : ''}
      </div>
    `;
  }

  function renderGapCard(gap, recommendations) {
    const req = recommendations.find(r => r.platform_id === gap.platform_id);
    const reqData = req ? encodeURIComponent(JSON.stringify(req)) : null;

    return `
      <div class="gap-card">
        <div class="gap-card-header">
          <span class="badge badge-missing">Access Gap</span>
          <span style="font-weight:700;font-size:13px;">${esc(gap.platform_id)}</span>
        </div>
        <div class="gap-meta-grid">
          <div>
            <div class="gap-meta-label">Description</div>
            <div class="gap-meta-value">${esc(gap.description)}</div>
          </div>
          <div>
            <div class="gap-meta-label">Business Impact</div>
            <div class="gap-meta-value">${esc(gap.business_impact)}</div>
          </div>
          <div>
            <div class="gap-meta-label">Risk if Granted</div>
            <div class="gap-meta-value">${esc(gap.risk_if_granted)}</div>
          </div>
          <div>
            <div class="gap-meta-label">Risk if Not Granted</div>
            <div class="gap-meta-value">${esc(gap.risk_if_not_granted)}</div>
          </div>
          <div>
            <div class="gap-meta-label">Least-Privilege Recommendation</div>
            <div class="gap-meta-value">${esc(gap.least_privilege_recommendation)}</div>
          </div>
          <div>
            <div class="gap-meta-label">Recommended Approver</div>
            <div class="gap-meta-value">${esc(gap.recommended_approver)}</div>
          </div>
          <div>
            <div class="gap-meta-label">Recommended Duration</div>
            <div class="gap-meta-value">${esc(gap.recommended_duration)}</div>
          </div>
        </div>
        <div class="gap-actions">
          ${reqData ? `<button class="btn btn-secondary btn-sm request-access-btn" data-req="${esc(reqData)}">
            Request Access →
          </button>` : ''}
          <button class="btn btn-ghost btn-sm" onclick="window.navigateTo('signal-map')">
            View Signal Map
          </button>
        </div>
      </div>
    `;
  }

  function renderAccessRequestTemplate(req) {
    return `
      <div class="card mb-sm">
        <div class="card-title">
          <span class="badge badge-draft">Draft Request</span>
          ${esc(req.platform_id)} — ${esc(req.requested_role)}
        </div>
        <div class="gap-meta-grid" style="font-size:12px;">
          <div>
            <div class="gap-meta-label">Persona</div>
            <div class="gap-meta-value">${esc(req.persona_id)}</div>
          </div>
          <div>
            <div class="gap-meta-label">Requested Scope</div>
            <div class="gap-meta-value"><code>${esc(req.requested_scope)}</code></div>
          </div>
          <div>
            <div class="gap-meta-label">Justification</div>
            <div class="gap-meta-value">${esc(req.justification)}</div>
          </div>
          <div>
            <div class="gap-meta-label">Business Outcome</div>
            <div class="gap-meta-value">${esc(req.business_outcome)}</div>
          </div>
          <div>
            <div class="gap-meta-label">Approver</div>
            <div class="gap-meta-value">${esc(req.recommended_approver)}</div>
          </div>
        </div>
        <div class="gap-actions mt-sm">
          <button class="btn btn-primary btn-sm request-access-btn"
            data-req="${esc(encodeURIComponent(JSON.stringify(req)))}">
            Submit Access Request →
          </button>
        </div>
      </div>
    `;
  }

  async function submitAccessRequest(req) {
    if (!State.persona) { toast('Select a persona first.', 'error'); return; }
    try {
      const payload = {
        persona_id:          req.persona_id || State.persona.id,
        kpi_id:              req.kpi_id || 'kpi_01',
        connector_id:        req.connector_id || req.platform_id,
        platform_id:         req.platform_id,
        requested_scope:     req.requested_scope,
        requested_role:      req.requested_role,
        requested_permission:req.requested_permission || 'read',
        requested_actions:   req.requested_actions || [],
        justification:       req.justification,
        business_outcome:    req.business_outcome,
        recommended_approver:req.recommended_approver,
      };
      await API.post('/api/access/requests', payload);
      toast('Access request submitted.', 'success');
      loadAccessRequests();
      navigateTo('access-requests');
    } catch (err) {
      toast(`Failed to submit request: ${err.message}`, 'error');
    }
  }

  // ── Section: Access Request Queue ────────────────────────────────────
  async function loadAccessRequests() {
    const content = document.getElementById('access-requests-content');
    content.innerHTML = '<div class="loading-placeholder"><span class="spinner"></span> Loading…</div>';
    try {
      const requests = await API.get('/api/access/requests');
      renderAccessRequestQueue(requests);
    } catch (err) {
      content.innerHTML = `<div class="warn-banner">Failed to load: ${esc(err.message)}</div>`;
    }
  }

  function renderAccessRequestQueue(requests) {
    const content = document.getElementById('access-requests-content');
    if (!requests.length) {
      content.innerHTML = '<div class="queue-empty">No access requests yet. Use the Access Readiness panel to request access.</div>';
      return;
    }
    content.innerHTML = `
      <div class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>Platform</th>
              <th>Persona</th>
              <th>Role Requested</th>
              <th>Scope</th>
              <th>KPI</th>
              <th>Status</th>
              <th>Approver</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            ${requests.map(req => `
              <tr>
                <td><span class="tag">${esc(req.platform_id)}</span></td>
                <td>${esc(req.persona_id)}</td>
                <td>${esc(req.requested_role)}</td>
                <td><code>${esc(req.requested_scope)}</code></td>
                <td class="text-small">${esc(req.kpi_id)}</td>
                <td>${renderReqStatus(req.status)}</td>
                <td class="text-small">${esc(req.recommended_approver || '—')}</td>
                <td class="text-small">${esc((req.created_at || '').slice(0, 19).replace('T', ' '))}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    `;
  }

  function renderReqStatus(status) {
    const map = {
      draft:        ['badge-draft',     'Draft'],
      submitted:    ['badge-submitted', 'Submitted'],
      under_review: ['badge-partial',   'Under Review'],
      approved:     ['badge-approved',  'Approved'],
      rejected:     ['badge-error',     'Rejected'],
    };
    const [cls, label] = map[(status || '').toLowerCase()] || ['badge-unknown', status];
    return `<span class="badge ${cls}">${label}</span>`;
  }

  document.getElementById('refresh-access-requests-btn').addEventListener('click', loadAccessRequests);

  // ── Section: Weekly Digest ───────────────────────────────────────────
  function renderDigest(r) {
    const content = document.getElementById('digest-content');
    if (!r) {
      content.innerHTML = '<div class="empty-state"><p>No KPI interpreted yet.</p></div>';
      return;
    }
    const digest = r.weekly_digest || {};
    const insights = r.control_insights || [];
    const actions = r.recommended_actions || [];
    const summary = r.access_readiness_summary || {};

    const execSummary = insights.find(i => i.type === 'executive_summary')?.insight
      || digest.executive_summary || '';

    content.innerHTML = `
      <div class="digest-header">
        <div>
          <div class="digest-title">Weekly Control Briefing</div>
          <div class="digest-meta">
            <span class="text-small">Persona: <strong>${esc(State.persona?.name || '—')}</strong></span>
            ${modeBadge(r.source_mode_summary ? Object.keys(r.source_mode_summary)[0] : 'mock')}
            ${r.confidence_score ? `<span class="badge badge-mock">Confidence: ${Math.round(r.confidence_score * 100)}%</span>` : ''}
          </div>
        </div>
      </div>

      <div class="digest-grid">
        <div class="digest-card digest-full-width">
          <div class="digest-card-title">Executive Summary</div>
          <div class="digest-card-content">${esc(execSummary) || '<span class="text-dim">No summary available.</span>'}</div>
        </div>

        ${digest.top_risks?.length ? `
          <div class="digest-card">
            <div class="digest-card-title">Top Risks</div>
            <ul class="digest-card-list">
              ${digest.top_risks.map(r => `<li>${esc(r)}</li>`).join('')}
            </ul>
          </div>` : ''}

        ${digest.top_opportunities?.length ? `
          <div class="digest-card">
            <div class="digest-card-title">Top Opportunities</div>
            <ul class="digest-card-list">
              ${digest.top_opportunities.map(o => `<li>${esc(o)}</li>`).join('')}
            </ul>
          </div>` : ''}

        ${actions.length ? `
          <div class="digest-card">
            <div class="digest-card-title">Recommended Actions</div>
            <ul class="digest-card-list">
              ${actions.map(a => `<li>${esc(typeof a === 'string' ? a : a.action || JSON.stringify(a))}</li>`).join('')}
            </ul>
          </div>` : ''}

        ${digest.evidence_gaps?.length ? `
          <div class="digest-card">
            <div class="digest-card-title" style="color:var(--amber)">Evidence Gaps</div>
            <ul class="digest-card-list">
              ${digest.evidence_gaps.map(g => `<li style="color:var(--amber)">${esc(g)}</li>`).join('')}
            </ul>
          </div>` : ''}

        ${digest.kpis_tracked?.length ? `
          <div class="digest-card">
            <div class="digest-card-title">KPIs Tracked</div>
            <ul class="digest-card-list">
              ${digest.kpis_tracked.map(k => `<li>${esc(typeof k === 'string' ? k : k.metric || k.title || JSON.stringify(k))}</li>`).join('')}
            </ul>
          </div>` : ''}

        <div class="digest-card">
          <div class="digest-card-title">Access Readiness Summary</div>
          <div class="digest-card-content">
            <div style="display:flex;gap:10px;align-items:center;margin-bottom:8px;">
              ${overallAccessBadge(summary.overall_status || 'unknown')}
            </div>
            <div class="text-small">
              ${summary.checked_signals || 0} signal(s) checked ·
              ${summary.access_gaps_count || 0} gap(s) ·
              ${summary.recommended_requests_count || 0} request(s) recommended
            </div>
            ${(summary.access_gaps_count || 0) > 0
              ? `<div class="warn-banner mt-sm" style="margin-bottom:0;font-size:11px;">
                  Incomplete access reduces confidence in this briefing.
                  <a data-section="access" style="color:var(--amber);cursor:pointer;">View gaps →</a>
                 </div>`
              : ''}
          </div>
        </div>

        ${digest.connectors_used?.length ? `
          <div class="digest-card">
            <div class="digest-card-title">Connectors Used</div>
            <div class="tag-row">${tags(digest.connectors_used)}</div>
          </div>` : ''}
      </div>
    `;
  }

  // ── Section: Agent Ideas ─────────────────────────────────────────────
  function renderAgentIdeas(r) {
    const content = document.getElementById('agent-ideas-content');
    const ideas = r?.agent_ideas || [];
    if (!ideas.length) {
      content.innerHTML = '<div class="empty-state"><p>No agent ideas generated yet. Run a KPI interpretation first.</p></div>';
      return;
    }
    content.innerHTML = `<div class="idea-cards">${ideas.map(idea => renderIdeaCard(idea)).join('')}</div>`;

    content.querySelectorAll('.request-agent-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const idea = JSON.parse(decodeURIComponent(btn.getAttribute('data-idea')));
        submitAgentRequest(idea);
      });
    });
  }

  function renderIdeaCard(idea) {
    const improves = Array.isArray(idea.improves)
      ? idea.improves.map(i => typeof i === 'string' ? i : (i.value || i))
      : [];

    const IMPROVES_COLOR = {
      value: 'tag-green', cost: 'tag-amber', reporting: 'tag-accent',
      risk: 'tag-red', compliance: 'tag-red', operations: '',
      evidence: 'tag-accent',
    };

    return `
      <div class="idea-card">
        <div class="idea-card-header">
          <div class="idea-card-title">${esc(idea.title)}</div>
          <div style="display:flex;gap:6px;">
            ${riskBadge(idea.risk_level)}
          </div>
        </div>
        <div class="idea-card-section">
          <strong>Problem</strong>
          ${esc(idea.problem_statement || idea.description || '—')}
        </div>
        <div class="idea-card-section">
          <strong>Proposed Capability</strong>
          ${esc(idea.proposed_capability || '—')}
        </div>
        <div class="idea-card-section">
          <strong>Expected Value</strong>
          ${esc(idea.expected_value || '—')}
        </div>
        <div class="idea-meta-row">
          ${complexityBadge(idea.implementation_complexity)}
        </div>
        ${idea.required_tools?.length ? `
          <div class="idea-card-section">
            <strong>Required Tools</strong>
            <div class="tag-row">${tags(idea.required_tools)}</div>
          </div>` : ''}
        ${idea.governance_notes ? `
          <div class="idea-card-section">
            <strong>Governance Notes</strong>
            ${esc(idea.governance_notes)}
          </div>` : ''}
        <div class="idea-card-footer">
          <div class="improves-tags">
            ${improves.map(i => `<span class="tag ${IMPROVES_COLOR[i] || ''}">${esc(i)}</span>`).join('')}
          </div>
          <button class="btn btn-primary btn-sm request-agent-btn"
            data-idea="${esc(encodeURIComponent(JSON.stringify({ id: idea.id, title: idea.title })))}">
            Request this agent
          </button>
        </div>
      </div>
    `;
  }

  async function submitAgentRequest(idea) {
    if (!State.persona) { toast('Select a persona first.', 'error'); return; }
    const kpiId = State.kpiResult?.normalized_kpi?.metric
      || State.kpiResult?.original_kpi
      || 'kpi_01';
    try {
      await API.post('/api/agent-requests', {
        agent_idea_id:       idea.id || idea.title,
        requested_by_persona:State.persona.id,
        linked_kpi_id:       kpiId,
        rationale:           `Requested from KPI workspace: ${kpiId}`,
      });
      toast(`Agent request submitted for "${idea.title}".`, 'success');
      loadAgentRequests();
      navigateTo('agent-requests');
    } catch (err) {
      toast(`Failed to submit agent request: ${err.message}`, 'error');
    }
  }

  // ── Section: Agent Request Queue ─────────────────────────────────────
  async function loadAgentRequests() {
    const content = document.getElementById('agent-requests-content');
    content.innerHTML = '<div class="loading-placeholder"><span class="spinner"></span> Loading…</div>';
    try {
      const requests = await API.get('/api/agent-requests');
      renderAgentRequestQueue(requests);
    } catch (err) {
      content.innerHTML = `<div class="warn-banner">Failed to load: ${esc(err.message)}</div>`;
    }
  }

  function renderAgentRequestQueue(requests) {
    const content = document.getElementById('agent-requests-content');
    if (!requests.length) {
      content.innerHTML = '<div class="queue-empty">No agent requests yet. Use Agent Ideas to request an agent.</div>';
      return;
    }
    content.innerHTML = `
      <div class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>Agent Idea</th>
              <th>Requested By</th>
              <th>KPI</th>
              <th>Status</th>
              <th>Rationale</th>
              <th>Submitted</th>
            </tr>
          </thead>
          <tbody>
            ${requests.map(req => `
              <tr>
                <td style="font-weight:600;">${esc(req.agent_idea_id)}</td>
                <td>${esc(req.requested_by_persona)}</td>
                <td class="text-small">${esc(req.linked_kpi_id)}</td>
                <td>${renderReqStatus(req.status)}</td>
                <td class="text-small" style="max-width:200px;">${esc(req.rationale)}</td>
                <td class="text-small">${esc((req.submitted_at || req.created_at || '').slice(0, 19).replace('T', ' '))}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    `;
  }

  document.getElementById('refresh-agent-requests-btn').addEventListener('click', loadAgentRequests);

  // ── Section: Evidence Trail ──────────────────────────────────────────
  async function loadEvidence() {
    const content = document.getElementById('evidence-content');
    content.innerHTML = '<div class="loading-placeholder"><span class="spinner"></span> Loading evidence…</div>';
    try {
      const personaParam = State.persona ? `?persona_id=${encodeURIComponent(State.persona.id)}` : '';
      const events = await API.get(`/api/evidence${personaParam}`);
      renderEvidenceTrail(events);
    } catch (err) {
      content.innerHTML = `<div class="warn-banner">Failed to load evidence: ${esc(err.message)}</div>`;
    }
  }

  function renderEvidenceTrail(events) {
    const content = document.getElementById('evidence-content');
    if (!events.length) {
      content.innerHTML = '<div class="queue-empty">No evidence events recorded yet. Run a KPI interpretation to generate evidence.</div>';
      return;
    }

    const EVENT_COLORS = {
      kpi_interpreted:             'var(--accent)',
      signals_selected:            'var(--accent)',
      tools_used:                  'var(--teal)',
      insights_generated:          'var(--green)',
      agent_ideas_generated:       'var(--green)',
      agent_request_submitted:     'var(--amber)',
      access_checked:              'var(--accent)',
      access_gap_detected:         'var(--red)',
      access_request_recommended:  'var(--amber)',
      connector_access_insufficient:'var(--red)',
      access_request_submitted:    'var(--amber)',
    };

    const reverse = [...events].reverse();
    content.innerHTML = `
      <div style="background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius);padding:16px 20px;">
        ${reverse.map(ev => {
          const color = EVENT_COLORS[ev.event_type] || 'var(--text-3)';
          const payload = ev.payload || {};
          return `
            <div class="evidence-item">
              <div class="evidence-dot" style="background:${color}"></div>
              <div style="flex:1;">
                <div class="evidence-type" style="color:${color}">${esc(ev.event_type)}</div>
                <div class="evidence-meta">
                  ${ev.persona_id ? `persona: <code>${esc(ev.persona_id)}</code> · ` : ''}
                  ${ev.kpi_id ? `kpi: <code>${esc(ev.kpi_id)}</code> · ` : ''}
                  <code>${esc((ev.timestamp || '').slice(0, 19).replace('T', ' '))}</code>
                </div>
                ${Object.keys(payload).length ? `
                  <div class="evidence-payload">${esc(JSON.stringify(payload, null, 2))}</div>
                ` : ''}
              </div>
            </div>
          `;
        }).join('')}
      </div>
    `;

    // Filter
    document.getElementById('evidence-filter').addEventListener('input', e => {
      const text = e.target.value.toLowerCase();
      content.querySelectorAll('.evidence-item').forEach(item => {
        const type = item.querySelector('.evidence-type')?.textContent || '';
        item.style.display = !text || type.includes(text) ? '' : 'none';
      });
    });
  }

  document.getElementById('refresh-evidence-btn').addEventListener('click', loadEvidence);

  // ── Section: Demo Agent Registry ─────────────────────────────────────
  const DEMO_AGENTS = [
    {
      name: 'Invoice Recovery Agent',
      owner: 'CFO / Finance',
      lifecycle: 'Production',
      risk_tier: 'medium',
      value: 'Recovers overdue invoices via automated payment reminders.',
      cost: '~£0.04/invocation',
      evidence_coverage: 'high',
      recommendation: 'Maintain current access. Quarterly cost review recommended.',
    },
    {
      name: 'Refund Approval Agent',
      owner: 'Business Owner',
      lifecycle: 'Production',
      risk_tier: 'high',
      value: 'Reduces refund processing time from 5 days to 4 hours.',
      cost: '~£0.09/invocation',
      evidence_coverage: 'medium',
      recommendation: 'Governance review required: high-risk financial decisions with partial evidence coverage.',
    },
    {
      name: 'Customer Support Triage Agent',
      owner: 'Service Owner',
      lifecycle: 'Staging',
      risk_tier: 'low',
      value: 'Routes support tickets to the correct team with 92% accuracy.',
      cost: '~£0.02/invocation',
      evidence_coverage: 'high',
      recommendation: 'Promote to production. Evidence coverage is sufficient for accountability.',
    },
    {
      name: 'Policy Research Agent',
      owner: 'Compliance Officer',
      lifecycle: 'Development',
      risk_tier: 'medium',
      value: 'Summarises regulatory changes and flags policy breaches.',
      cost: '~£0.06/invocation',
      evidence_coverage: 'low',
      recommendation: 'Block promotion. Evidence coverage is insufficient. Add audit logging.',
    },
    {
      name: 'Shadow Analyst Agent',
      owner: 'CTO',
      lifecycle: 'Retired',
      risk_tier: 'high',
      value: 'Used for internal R&D telemetry analysis. Replaced by Foundry.',
      cost: '—',
      evidence_coverage: 'none',
      recommendation: 'Decommissioned. Ensure all data retained for compliance period.',
    },
  ];

  const LIFECYCLE_BADGE = {
    Production:  ['badge-live',    'Production'],
    Staging:     ['badge-partial', 'Staging'],
    Development: ['badge-mock',    'Development'],
    Retired:     ['badge-unknown', 'Retired'],
  };

  const EVIDENCE_BADGE = {
    high:   ['badge-ready',   'High'],
    medium: ['badge-partial', 'Medium'],
    low:    ['badge-missing', 'Low'],
    none:   ['badge-error',   'None'],
  };

  function renderRegistry() {
    const content = document.getElementById('registry-content');
    if (content.querySelector('.registry-cards')) return; // already rendered

    content.innerHTML = `
      <div class="registry-cards">
        ${DEMO_AGENTS.map(agent => {
          const [lcCls, lcLabel] = LIFECYCLE_BADGE[agent.lifecycle] || ['badge-unknown', agent.lifecycle];
          const [evCls, evLabel] = EVIDENCE_BADGE[agent.evidence_coverage] || ['badge-unknown', agent.evidence_coverage];
          return `
            <div class="registry-card">
              <div>
                <div class="registry-col-label">Agent</div>
                <div class="registry-name">${esc(agent.name)}</div>
                <div class="registry-owner">${esc(agent.owner)}</div>
              </div>
              <div>
                <div class="registry-col-label">Lifecycle</div>
                <span class="badge ${lcCls}">${lcLabel}</span>
              </div>
              <div>
                <div class="registry-col-label">Risk Tier</div>
                ${riskBadge(agent.risk_tier)}
              </div>
              <div>
                <div class="registry-col-label">Evidence Coverage</div>
                <span class="badge ${evCls}">${evLabel}</span>
              </div>
              <div>
                <div class="registry-col-label">Control Recommendation</div>
                <div class="registry-recommendation">${esc(agent.recommendation)}</div>
              </div>
            </div>
          `;
        }).join('')}
      </div>
    `;
  }

  // ── Boot ──────────────────────────────────────────────────────────────
  function boot() {
    initNav();
    loadPersonas();
  }

  document.addEventListener('DOMContentLoaded', boot);

})();
