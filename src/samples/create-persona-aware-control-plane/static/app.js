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
    overview:          { parent: 'overview',       tab: null },
    briefing:          { parent: 'overview',       tab: null },
    persona:           { parent: 'overview',       tab: null },
    series:            { parent: 'overview',       tab: null },
    workflow:          { parent: 'workflow',       tab: 'kpi' },
    actions:           { parent: 'workflow',       tab: 'kpi' },
    kpi:               { parent: 'workflow',       tab: 'kpi' },
    'agent-ideas':     { parent: 'workflow',       tab: 'kpi' },
    decisions:         { parent: 'decisions',      tab: 'access-requests' },
    'access-requests': { parent: 'decisions',      tab: 'access-requests' },
    'agent-requests':  { parent: 'decisions',      tab: 'agent-requests' },
    'evidence-main':   { parent: 'evidence-main',  tab: 'evidence-trail' },
    evidence:          { parent: 'evidence-main',  tab: 'evidence-trail' },
    'evidence-trail':  { parent: 'evidence-main',  tab: 'evidence-trail' },
    'signal-map':      { parent: 'evidence-main',  tab: 'signal-map' },
    access:            { parent: 'evidence-main',  tab: 'access' },
    digest:            { parent: 'evidence-main',  tab: 'digest' },
    registry:          { parent: 'evidence-main',  tab: 'registry' },
    settings:          { parent: 'settings',       tab: 'connectors' },
    integrations:      { parent: 'settings',       tab: 'connectors' },
    connectors:        { parent: 'settings',       tab: 'connectors' },
    tools:             { parent: 'settings',       tab: 'tools' },
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
    const hash = location.hash.replace('#', '') || 'overview';
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

    if (tab) activateTab(parent, tab);
    history.replaceState(null, '', `#${sectionId}`);
    document.getElementById('main').scrollTop = 0;
    lazyLoad(tab || parent);
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
      case 'overview':         loadOverview(); break;
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

  /** Convert snake_case or camelCase IDs to Title Case for display */
  function fmtId(id) {
    if (!id) return '';
    return String(id)
      .replace(/_/g, ' ')
      .replace(/([a-z])([A-Z])/g, '$1 $2')
      .replace(/\b\w/g, c => c.toUpperCase());
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

  // ── Section: Overview ─────────────────────────────────────────────────
  function loadOverview() {
    loadPersonas();
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
    const AUTH_LABELS = {
      none: 'None',
      api_key: 'API Key',
      oauth: 'OAuth',
      entra_client_credentials: 'Entra App',
      entra_delegated: 'Entra Delegated',
      workload_identity: 'Workload Identity',
      azure_default_credential: 'Azure Default Credential',
    };
    grid.innerHTML = connectors.map(c => {
      const authLabel = AUTH_LABELS[c.auth_type] || c.auth_type || 'None';
      const lastChecked = c.last_checked_at
        ? new Date(c.last_checked_at).toLocaleString('en-GB', { dateStyle: 'short', timeStyle: 'short' })
        : null;
      return `
      <div class="connector-card" id="cc-${esc(c.id)}">
        <div class="sc-header">
          <div class="sc-name">${esc(c.name)}</div>
          <div class="sc-badges">
            ${modeBadge(c.mode)}
            ${statusBadge(c.status)}
          </div>
        </div>
        <div class="sc-desc">${esc(c.description || '')}</div>
        <div class="sc-contract">
          <div class="sc-contract-label">Provided Signals</div>
          <div class="connector-signals">
            ${(c.supported_signal_types || []).map(s =>
              `<span class="tag">${esc(s)}</span>`
            ).join('')}
          </div>
        </div>
        <details class="disclosure">
          <summary>
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="6 9 12 15 18 9"/></svg>
            Technical Setup
          </summary>
          <div class="disclosure-body">
            <div class="connector-meta">
              <div class="connector-meta-row">
                <span class="connector-meta-label">Authentication</span>
                <span>${esc(authLabel)}</span>
              </div>
              <div class="connector-meta-row">
                <span class="connector-meta-label">Live proof</span>
                <span id="live-proof-${esc(c.id)}" class="text-dim">Not checked yet</span>
              </div>
              ${lastChecked ? `<div class="connector-meta-row">
                <span class="connector-meta-label">Last checked</span>
                <span>${esc(lastChecked)}</span>
              </div>` : ''}
              ${c.error_message ? `<div class="connector-meta-row">
                <span class="connector-meta-label" style="color:var(--red)">Error</span>
                <span style="color:var(--red)">${esc(c.error_message)}</span>
              </div>` : ''}
            </div>
            <div style="margin-top:10px;">
              <button class="btn btn-ghost btn-sm connector-live-proof-btn" data-id="${esc(c.id)}">Check Live Proof</button>
            </div>
          </div>
        </details>
        <div class="connector-actions" style="margin-top:12px;">
          <button class="btn btn-secondary btn-sm connector-configure-btn" data-id="${esc(c.id)}">Edit Settings</button>
          <button class="btn btn-ghost btn-sm connector-test-btn" data-id="${esc(c.id)}">Test Connection</button>
        </div>
      </div>
      `;
    }).join('');

    grid.querySelectorAll('.connector-configure-btn').forEach(btn => {
      btn.addEventListener('click', () => openConfigModal(btn.getAttribute('data-id'), connectors));
    });
    grid.querySelectorAll('.connector-test-btn').forEach(btn => {
      btn.addEventListener('click', () => testConnector(btn.getAttribute('data-id')));
    });
    grid.querySelectorAll('.connector-live-proof-btn').forEach(btn => {
      btn.addEventListener('click', () => checkLiveProof(btn.getAttribute('data-id')));
    });

    // Auto-populate proof for the two demo-critical connectors.
    connectors
      .filter(c => c.id === 'azure' || c.id === 'agent365')
      .forEach(c => { void checkLiveProof(c.id, { silent: true }); });
  }

  function _stageBadge(ok, label) {
    const cls = ok ? 'badge-ready' : 'badge-unknown';
    const text = ok ? `${label}: yes` : `${label}: no`;
    return `<span class="badge ${cls}" style="margin-right:6px;">${text}</span>`;
  }

  async function checkLiveProof(connectorId, options = {}) {
    const silent = !!options.silent;
    const target = document.getElementById(`live-proof-${connectorId}`);
    if (!target) return;

    target.innerHTML = '<span class="text-dim">Checking…</span>';
    try {
      const data = await API.get(`/api/connectors/${encodeURIComponent(connectorId)}/auth-status`);
      const stages = data.stages || {};
      target.innerHTML = [
        _stageBadge(!!stages.configured, 'configured'),
        _stageBadge(!!stages.authenticated, 'authenticated'),
        _stageBadge(!!stages.authorized, 'authorized'),
        _stageBadge(!!stages.live_data_received, 'live data'),
      ].join('');

      if (data.error) {
        target.innerHTML += `<div class="text-small" style="color:var(--red);margin-top:6px;">${esc(data.error)}</div>`;
      } else if (data.identity_summary) {
        target.innerHTML += `<div class="text-small text-dim" style="margin-top:6px;">${esc(data.identity_summary)}</div>`;
      }

      if (!silent) {
        const live = stages.live_data_received ? 'live data confirmed' : 'not live yet';
        toast(`${connectorId}: ${live}`, stages.live_data_received ? 'success' : 'info');
      }
    } catch (err) {
      target.innerHTML = `<span style="color:var(--red)">${esc(err.message)}</span>`;
      if (!silent) toast(`Live proof check failed: ${err.message}`, 'error');
    }
  }

  function openConfigModal(connectorId, connectors) {
    const c = connectors.find(x => x.id === connectorId);
    if (!c) return;
    document.getElementById('cfg-connector-id').value = connectorId;
    document.getElementById('config-modal-title').textContent = `Connection Settings — ${c.name}`;
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
      toast(`Signal contract updated for ${cid}.`, 'success');
      State.connectors = [];
      closeConfigModal();
      loadConnectors();
    } catch (err) {
      toast(`Configuration failed: ${err.message}`, 'error');
    }
  });

  async function testConnector(connectorId) {
    try {
      toast(`Running health check on ${connectorId}…`);
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
      wrap.innerHTML = '<div class="queue-empty">No registered capabilities. Configure at least one connector.</div>';
      return;
    }
    wrap.innerHTML = `
      <div class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>Capability</th>
              <th>Platform</th>
              <th>Signal Types</th>
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
          <div style="font-weight:600;font-size:13px;">${esc(t.name)}</div>
          <div class="text-small text-dim">${esc(t.description || t.id || '')}</div>
        </td>
        <td><span class="tag">${esc(t.platform_id)}</span></td>
        <td>${tags(t.signal_types)}</td>
        <td>${modeBadge(t.source_mode)}</td>
        <td>${t.enabled
          ? '<span class="badge badge-ready">Active</span>'
          : '<span class="badge badge-unknown">Inactive</span>'}</td>
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
    if (btn) { btn.disabled = false; btn.innerHTML = 'Assess this objective →'; }
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
    btn.innerHTML = '<span class="spinner"></span> Assessing…';
    try {
      const data = await API.post('/api/kpi-agent/challenge', {
        persona_id: State.persona.id,
        draft_kpi: draftKpi,
      });
      KpiStepper.sessionId = data.session_id;
      KpiStepper.challengeData = data;
      renderChallengeStep(data);
      setKpiStep(2);
      toast('Objective assessed — review the assessment below.', 'success');
    } catch (err) {
      toast(`Challenge failed: ${err.message}`, 'error');
    } finally {
      btn.disabled = false;
      btn.innerHTML = 'Assess this objective →';
    }
  });

  function renderChallengeStep(data) {
    // Maturity row
    const maturityMap = {
      vague:            ['badge-missing', 'Needs refinement — too broad for governance use'],
      usable:           ['badge-partial', 'Workable — answer the questions below to sharpen this objective'],
      well_articulated: ['badge-ready', 'Well defined — ready to confirm as a governance objective'],
      control_ready:    ['badge-ready', 'Governance ready'],
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
      missingEl.innerHTML = `<strong>Missing information</strong> ${missing.map(f => `<span class="tag">${esc(f)}</span>`).join(' ')}`;
    } else {
      missingEl.classList.add('hidden');
    }

    // Suggested KPI
    const suggested = data.suggested_formalized_kpi || {};
    const suggestedEl = document.getElementById('challenge-suggested');
    if (suggested.title || suggested.outcome_statement) {
      suggestedEl.classList.remove('hidden');
      suggestedEl.innerHTML = `
        <strong>Suggested governance objective</strong>
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
          placeholder="Optional — skip if not applicable" autocomplete="off">
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
    btn.innerHTML = '<span class="spinner"></span> Confirming…';
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
      toast('Objective confirmed.', 'success');
    } catch (err) {
      toast(`Formalization failed: ${err.message}`, 'error');
    } finally {
      btn.disabled = false;
      btn.innerHTML = 'Confirm Objective →';
    }
  });

  function renderFormalizedKpiCard(kpi, maturity, confidence) {
    const conf = Math.round((confidence || kpi?.confidence_score || 0) * 100);
    const confColor = conf >= 75 ? 'var(--green)' : conf >= 45 ? 'var(--amber)' : 'var(--red)';
    const maturityMap = {
      vague:            ['badge-missing', 'Needs Refinement'],
      usable:           ['badge-partial', 'Workable'],
      well_articulated: ['badge-ready', 'Well Defined'],
      control_ready:    ['badge-ready', 'Governance Ready'],
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
          <div class="fkpi-list-section-label">Governance Trade-offs</div>
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
        mode: 'hybrid',
      });
      KpiStepper.controlPackage = data.control_package;

      // Also run the legacy interpret endpoint so signal map, access and digest are populated
      const legacy = await API.post('/api/kpi-agent/interpret', {
        persona_id: State.persona.id,
        kpi: KpiStepper.formalizedKpi.title || null,
        mode: 'hybrid',
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
      toast('Governance requirements built.', 'success');
    } catch (err) {
      toast(`Composition failed: ${err.message}`, 'error');
    } finally {
      btn.disabled = false;
      btn.innerHTML = 'Build Governance Requirements →';
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
            What this provides
          </div>
          <ul class="control-item-list">
            ${whatYouGet.map(item => `<li>${esc(item)}</li>`).join('')}
          </ul>
        </div>
        <div class="control-package-column">
          <div class="control-column-title">
            <span class="col-icon" style="color:var(--amber)"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z"/></svg></span>
            What still needs to be configured
          </div>
          <ul class="control-item-list">
            ${whatYouNeed.map(item => `<li>${esc(item)}</li>`).join('')}
          </ul>
        </div>
      </div>

      <!-- Connector readiness -->
      <div class="cp-details-section">
        <div class="cp-details-title" onclick="this.nextElementSibling.classList.toggle('expanded')">
          Platform Connection Status
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="6 9 12 15 18 9"/></svg>
        </div>
        <div class="cp-details-body">
          ${Object.entries(connectorSummary).map(([plat, info]) => `
            <div class="cp-readiness-row">
              <span class="cp-readiness-name">${esc(plat)}</span>
              ${info.available
                ? `<span class="badge badge-ready">${info.tool_count} tool(s) ready</span>`
                : `<span class="badge badge-missing">Not yet connected</span>`}
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
              <span class="badge badge-ready">Access confirmed</span>
            </div>
          `).join('') : ''}
          ${missingConnectors.length ? missingConnectors.map(c => `
            <div class="cp-readiness-row">
              <span class="cp-readiness-name">${esc(c)}</span>
              <span class="badge badge-missing">Access not granted</span>
            </div>
          `).join('') : ''}
          ${!readyConnectors.length && !missingConnectors.length
            ? '<div class="text-dim text-small">No access check data.</div>' : ''}
        </div>
      </div>

      <!-- Required signals/tools/evidence behind view details -->
      <div class="cp-details-section">
        <div class="cp-details-title" onclick="this.nextElementSibling.classList.toggle('expanded')">
          Technical Details — Data Sources &amp; Requirements
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="6 9 12 15 18 9"/></svg>
        </div>
        <div class="cp-details-body">
          <div class="gap-meta-grid" style="font-size:12px;margin-top:8px;">
            <div>
              <div class="gap-meta-label">Data Requirements</div>
              <div class="tag-row mt-sm">${tags(pkg.required_signals, 'tag-accent')}</div>
            </div>
            <div>
              <div class="gap-meta-label">Required Platforms</div>
              <div class="tag-row mt-sm">${tags(pkg.required_connectors)}</div>
            </div>
            <div>
              <div class="gap-meta-label">Required Tools</div>
              <div class="tag-row mt-sm">${tags((pkg.required_tools || []).slice(0, 8))}</div>
            </div>
            <div>
              <div class="gap-meta-label">Evidence Standards</div>
              <ul style="margin:6px 0 0 16px;font-size:12px;color:var(--text-2);line-height:1.7;">
                ${(pkg.required_evidence || []).map(e => `<li>${esc(e)}</li>`).join('')}
              </ul>
            </div>
          </div>
          ${pkg.limitations?.length ? `
            <div style="margin-top:12px;">
              <div class="gap-meta-label" style="color:var(--amber)">Known Gaps &amp; Coverage Limitations</div>
              <ul style="margin:6px 0 0 16px;font-size:12px;color:var(--amber);line-height:1.7;">
                ${pkg.limitations.map(l => `<li>${esc(l)}</li>`).join('')}
              </ul>
            </div>` : ''}
        </div>
      </div>
    `;

    // Render live signal provenance section if provenance data is present
    renderSignalProvenance(pkg.signal_provenance || [], pkg.source_summary || {});
  }

  // ---------------------------------------------------------------------------
  // Live Signal Provenance rendering
  // ---------------------------------------------------------------------------

  function renderSignalProvenance(provenance, sourceSummary) {
    const section = document.getElementById('signal-provenance-section');
    if (!section) return;

    if (!provenance || provenance.length === 0) {
      section.classList.add('hidden');
      return;
    }

    section.classList.remove('hidden');
    renderSourceSummaryBanner(sourceSummary);
    renderProvenanceTable(provenance);
    renderProvenanceDrawer(provenance);

    // Wire up the drawer toggle
    const toggleBtn = document.getElementById('toggle-provenance-drawer-btn');
    const drawer = document.getElementById('provenance-drawer');
    if (toggleBtn && drawer) {
      toggleBtn.onclick = () => {
        const expanded = toggleBtn.getAttribute('aria-expanded') === 'true';
        toggleBtn.setAttribute('aria-expanded', String(!expanded));
        drawer.classList.toggle('hidden', expanded);
        drawer.setAttribute('aria-hidden', String(expanded));
      };
    }
  }

  function renderSourceSummaryBanner(summary) {
    const el = document.getElementById('source-summary-banner');
    if (!el) return;

    const live = summary.live_signals || 0;
    const mock = summary.mock_signals || 0;
    const errors = summary.error_signals || 0;
    const readiness = summary.readiness || 'not_ready';

    let cls = 'banner-mock';
    let icon = '';
    let text = '';

    if (readiness === 'ready' && live > 0) {
      cls = 'banner-live';
      icon = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"/></svg>';
      text = `${live} live data point${live !== 1 ? 's' : ''} retrieved from real platform connections — all data verified as current`;
    } else if (readiness === 'partially_ready') {
      cls = 'banner-partial';
      icon = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>';
      text = `${live} live data point${live !== 1 ? 's' : ''}, ${mock} from scenario defaults — partial live coverage. Review before making access decisions.`;
      if (errors > 0) text += ` ${errors} connection error${errors !== 1 ? 's' : ''}.`;
    } else if (errors > 0 && live === 0) {
      cls = 'banner-error';
      icon = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>';
      text = `${errors} platform connection error${errors !== 1 ? 's' : ''} — check platform configuration. Recommendations may not reflect current system state.`;
    } else {
      cls = 'banner-mock';
      icon = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="9" y1="9" x2="15" y2="15"/><line x1="15" y1="9" x2="9" y2="15"/></svg>';
      text = `${mock} scenario default${mock !== 1 ? 's' : ''} — no live platform connections are active. Recommendations are based on scenario data, not real system state.`;
    }

    el.className = `source-summary-banner ${cls}`;
    el.innerHTML = `${icon}<span>${esc(text)}</span>`;
  }

  function renderProvenanceTable(provenance) {
    const container = document.getElementById('provenance-table-container');
    if (!container) return;

    const rows = provenance.map(p => {
      const badgeCls = `source-badge source-badge-${p.source_mode || 'mock'}`;
      const badgeLabel = (p.source_mode || 'mock').toUpperCase();
      const usedBadge = p.used_in_composition
        ? '<span class="badge badge-ready" style="font-size:10px;">used</span>'
        : '<span class="badge badge-missing" style="font-size:10px;">not used</span>';
      const confPct = Math.round((p.confidence || 0) * 100);
      const ts = p.retrieved_at ? new Date(p.retrieved_at).toLocaleTimeString() : '—';

      return `<tr>
        <td class="td-signal">${esc(p.signal_name || '—')}</td>
        <td>${esc(p.platform_id || '—')}</td>
        <td><span class="${badgeCls}">${esc(badgeLabel)}</span></td>
        <td class="td-mono">${esc(p.tool_name || '—')}</td>
        <td>${confPct}%</td>
        <td>${usedBadge}</td>
        <td style="color:var(--text-3);font-size:11px;">${ts}</td>
      </tr>`;
    }).join('');

    container.innerHTML = `
      <table class="provenance-table" aria-label="Signal provenance">
        <thead>
          <tr>
            <th>Signal</th>
            <th>Platform</th>
            <th>Source</th>
            <th>Tool</th>
            <th>Confidence</th>
            <th>Used</th>
            <th>Retrieved</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>`;
  }

  function renderProvenanceDrawer(provenance) {
    const drawer = document.getElementById('provenance-drawer-content');
    if (!drawer) return;

    const items = provenance.map(p => {
      const badgeCls = `source-badge source-badge-${p.source_mode || 'mock'}`;
      const errorHtml = p.error
        ? `<div class="provenance-drawer-error">${esc(p.error)}</div>` : '';
      const endpointHtml = p.endpoint
        ? `<div class="provenance-drawer-endpoint">${esc(p.endpoint)}</div>` : '';
      const identityHtml = p.identity_summary
        ? `<div class="provenance-drawer-identity">Identity: ${esc(p.identity_summary)}</div>` : '';
      const queryHtml = p.query_summary
        ? `<div class="provenance-drawer-query">${esc(p.query_summary)}</div>` : '';

      return `<div class="provenance-drawer-item">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
          <span class="${badgeCls}">${esc((p.source_mode || 'mock').toUpperCase())}</span>
          <span class="provenance-drawer-tool">${esc(p.tool_name || '—')}</span>
        </div>
        ${queryHtml}
        ${endpointHtml}
        ${identityHtml}
        ${errorHtml}
      </div>`;
    }).join('');

    drawer.innerHTML = items || '<div class="text-dim text-small">No provenance data.</div>';
  }

  document.getElementById('kpi-back-to-formalize-btn').addEventListener('click', () => setKpiStep(3));

  // Step 4 → Step 5: Actions
  document.getElementById('kpi-to-actions-btn').addEventListener('click', () => {
    if (!KpiStepper.controlPackage) return;
    renderKpiActions(KpiStepper.controlPackage);
    setKpiStep(5);
  });

  function _sourceModePill(sourceSummary) {
    const s = sourceSummary || {};
    const readiness = s.readiness || 'not_ready';
    const live = s.live_signals || 0;
    const err  = s.error_signals || 0;
    // "Live" only when every tracked signal is live and there are no errors or missing connectors
    if (readiness === 'ready' && live > 0 && err === 0) {
      return '<span class="source-mode-pill pill-live" title="All signals were retrieved from live APIs">Live</span>';
    }
    // "Hybrid" when at least one live signal exists but some failed or connectors are mock-only
    if (live > 0) {
      return '<span class="source-mode-pill pill-hybrid" title="Mix of live and mock data — not all connectors have a live integration configured">Hybrid</span>';
    }
    return '<span class="source-mode-pill pill-mock" title="No live signals — recommendations are based on scenario data">Mock</span>';
  }

  function renderKpiActions(pkg) {
    const actions = pkg.recommended_actions || [];
    const agentIdeas = pkg.agent_ideas || [];
    const pill = _sourceModePill(pkg.source_summary);
    document.getElementById('kpi-actions-content').innerHTML = `
      <div class="section-heading-row"><h3>Required Actions</h3>${pill}</div>
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
        <div class="section-heading-row" style="margin-top:28px;"><h3>Candidate Agents</h3>${pill}</div>
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
                  Request this agent be built
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
            <div class="chain-body-title">Data Requirements (${signals.length})</div>
            <div class="chain-body-content tag-row">${tags(signals, 'tag-accent')}</div>
          </div>
        </div>

        <div class="signal-chain-step">
          <div class="chain-connector">
            <div class="chain-dot"></div>
            <div class="chain-line"></div>
          </div>
          <div class="chain-body">
            <div class="chain-body-title">Source Platforms (${platforms.length})</div>
            <div class="chain-body-content tag-row">${tags(platforms)}</div>
          </div>
        </div>

        <div class="signal-chain-step">
          <div class="chain-connector">
            <div class="chain-dot"></div>
            <div class="chain-line"></div>
          </div>
          <div class="chain-body">
            <div class="chain-body-title">Tools Used to Gather Data (${toolsUsed.length})</div>
            <div class="chain-body-content tag-row">${tags(toolsUsed)}</div>
          </div>
        </div>

        <div class="signal-chain-step">
          <div class="chain-connector">
            <div class="chain-dot" style="background:${gaps.length > 0 ? 'var(--red)' : 'var(--green)'}"></div>
          </div>
          <div class="chain-body" style="border-color:${gaps.length > 0 ? 'var(--red)' : 'var(--green)'};">
            <div class="chain-body-title">Required Permissions</div>
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
      content.innerHTML = '<div class="empty-state"><p>No KPI interpreted yet. Go to <a data-section="kpi">Governance Workflow</a> first.</p></div>';
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
          <div class="access-overview-label">Current Access Status</div>
          <div class="access-status-large mt-sm">
            ${overallAccessBadge(summary.overall_status || 'unknown')}
          </div>
        </div>
        <div class="access-stats" style="margin-left:auto;">
          <div class="access-stat">
            <div class="access-stat-num">${checks.length}</div>
            <div class="access-stat-label">Permissions Checked</div>
          </div>
          <div class="access-stat">
            <div class="access-stat-num" style="color:${gaps.length > 0 ? 'var(--red)' : 'var(--green)'}">${gaps.length}</div>
            <div class="access-stat-label">Missing Permissions</div>
          </div>
          <div class="access-stat">
            <div class="access-stat-num" style="color:${recommendations.length > 0 ? 'var(--amber)' : 'var(--green)'}">${recommendations.length}</div>
            <div class="access-stat-label">Requests to Submit</div>
          </div>
        </div>
      </div>

      ${gaps.length > 0 ? `
        <div class="warn-banner">
          This objective requires data that <strong>${esc(persona.name || 'this role')}</strong> does not currently have access to.
          Review the missing permissions below and submit least-privilege requests for the designated approver to action.
        </div>
      ` : '<div class="info-banner">All required access is available for this persona and KPI.</div>'}

      <!-- Per-signal checks -->
      <h3 style="font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--text-3);margin-bottom:12px;">
        Permission Verification Results
      </h3>
      <div class="access-check-list" id="access-check-list">
        ${checks.map(check => renderAccessCheckItem(check)).join('')}
      </div>

      ${gaps.length > 0 ? `
        <hr class="divider">
        <h3 style="font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--red);margin-bottom:12px;">
          Missing Permissions
        </h3>
        ${gaps.map(gap => renderGapCard(gap, recommendations)).join('')}
      ` : ''}

      ${recommendations.length > 0 ? `
        <hr class="divider">
        <h3 style="font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--amber);margin-bottom:12px;">
          Suggested Permission Requests
        </h3>
        <div class="info-banner">
          The control plane never auto-grants access.
          Each item below is a least-privilege recommendation. The designated approver must review and action each request before any access is granted.
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
          <span class="badge badge-missing">Missing Permission</span>
          <span style="font-weight:700;font-size:13px;">${esc(gap.platform_id)}</span>
        </div>
        <div class="gap-meta-grid">
          <div>
            <div class="gap-meta-label">What's Missing</div>
            <div class="gap-meta-value">${esc(gap.description)}</div>
          </div>
          <div>
            <div class="gap-meta-label">Impact if Not Resolved</div>
            <div class="gap-meta-value">${esc(gap.business_impact)}</div>
          </div>
          <div>
            <div class="gap-meta-label">Risk of Granting Access</div>
            <div class="gap-meta-value">${esc(gap.risk_if_granted)}</div>
          </div>
          <div>
            <div class="gap-meta-label">Risk of Declining Access</div>
            <div class="gap-meta-value">${esc(gap.risk_if_not_granted)}</div>
          </div>
          <div>
            <div class="gap-meta-label">Recommended Permission Level</div>
            <div class="gap-meta-value">${esc(gap.least_privilege_recommendation)}</div>
          </div>
          <div>
            <div class="gap-meta-label">Who Should Approve</div>
            <div class="gap-meta-value">${esc(gap.recommended_approver)}</div>
          </div>
          <div>
            <div class="gap-meta-label">Suggested Access Duration</div>
            <div class="gap-meta-value">${esc(gap.recommended_duration)}</div>
          </div>
        </div>
        <div class="gap-actions">
          ${reqData ? `<button class="btn btn-secondary btn-sm request-access-btn" data-req="${esc(reqData)}">
            Request Access →
          </button>` : ''}
          <button class="btn btn-ghost btn-sm" onclick="window.navigateTo('signal-map')">
            View Data Dependency Map
          </button>
        </div>
      </div>
    `;
  }

  function renderAccessRequestTemplate(req) {
    return `
      <div class="card mb-sm">
        <div class="card-title">
          <span class="badge badge-draft">Pending Submission</span>
          ${esc(req.platform_id)} — ${esc(req.requested_role)}
        </div>
        <div class="gap-meta-grid" style="font-size:12px;">
          <div>
            <div class="gap-meta-label">Role</div>
            <div class="gap-meta-value">${esc(fmtId(req.persona_id))}</div>
          </div>
          <div>
            <div class="gap-meta-label">Permission Scope</div>
            <div class="gap-meta-value"><code>${esc(req.requested_scope)}</code></div>
          </div>
          <div>
            <div class="gap-meta-label">Business Justification</div>
            <div class="gap-meta-value">${esc(req.justification)}</div>
          </div>
          <div>
            <div class="gap-meta-label">Expected Outcome</div>
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
      content.innerHTML = '<div class="queue-empty">No access requests have been submitted yet. Complete the Governance Workflow to identify missing permissions and generate requests for the designated approver to review.</div>';
      return;
    }
    content.innerHTML = `
      <div class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>Source Platform</th>
              <th>Role</th>
              <th>Permission Level</th>
              <th>Access Scope</th>
              <th>Objective</th>
              <th>Status</th>
              <th>Approving Role</th>
              <th>Submitted</th>
            </tr>
          </thead>
          <tbody>
            ${requests.map(req => `
              <tr>
                <td><span class="tag">${esc(req.platform_id)}</span></td>
                <td>${esc(fmtId(req.persona_id))}</td>
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
          <div class="digest-title">Governance Summary</div>
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
            <div class="digest-card-title">Identified Risks</div>
            <ul class="digest-card-list">
              ${digest.top_risks.map(r => `<li>${esc(r)}</li>`).join('')}
            </ul>
          </div>` : ''}

        ${digest.top_opportunities?.length ? `
          <div class="digest-card">
            <div class="digest-card-title">Identified Opportunities</div>
            <ul class="digest-card-list">
              ${digest.top_opportunities.map(o => `<li>${esc(o)}</li>`).join('')}
            </ul>
          </div>` : ''}

        ${actions.length ? `
          <div class="digest-card">
            <div class="digest-card-title">Required Actions</div>
            <ul class="digest-card-list">
              ${actions.map(a => `<li>${esc(typeof a === 'string' ? a : a.action || JSON.stringify(a))}</li>`).join('')}
            </ul>
          </div>` : ''}

        ${digest.evidence_gaps?.length ? `
          <div class="digest-card">
            <div class="digest-card-title" style="color:var(--amber)">Coverage Gaps</div>
            <ul class="digest-card-list">
              ${digest.evidence_gaps.map(g => `<li style="color:var(--amber)">${esc(g)}</li>`).join('')}
            </ul>
          </div>` : ''}

        ${digest.kpis_tracked?.length ? `
          <div class="digest-card">
            <div class="digest-card-title">Objectives Tracked</div>
            <ul class="digest-card-list">
              ${digest.kpis_tracked.map(k => `<li>${esc(typeof k === 'string' ? k : k.metric || k.title || JSON.stringify(k))}</li>`).join('')}
            </ul>
          </div>` : ''}

        <div class="digest-card">
          <div class="digest-card-title">Access Status</div>
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
            <div class="digest-card-title">Platforms Used</div>
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
          <strong>Governance Problem</strong>
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
            <strong>Tools Needed</strong>
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
            Request this agent be built
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
      content.innerHTML = '<div class="queue-empty">No agent build requests have been submitted yet. Complete the Governance Workflow to see candidate agents, then submit a build request for approval.</div>';
      return;
    }
    content.innerHTML = `
      <div class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>Proposed Agent</th>
              <th>Requested By Role</th>
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
      content.innerHTML = '<div class="queue-empty">No governance events have been recorded yet. Complete the Governance Workflow to begin building the accountability record for this role.</div>';
      return;
    }

    const EVENT_LABELS = {
      kpi_interpreted:              'Governance Objective Interpreted',
      signals_selected:             'Data Requirements Determined',
      tools_used:                   'Tools Used to Gather Data',
      insights_generated:           'Governance Insights Generated',
      agent_ideas_generated:        'Candidate Agents Identified',
      agent_request_submitted:      'Agent Build Request Submitted',
      access_checked:               'Access Permissions Verified',
      access_gap_detected:          'Missing Permission Detected',
      access_request_recommended:   'Permission Request Recommended',
      connector_access_insufficient:'Insufficient Platform Access',
      access_request_submitted:     'Permission Request Submitted',
      connector_configured:         'Platform Connection Updated',
      connector_health_check:       'Platform Connection Verified',
      connector_enabled:            'Platform Connection Enabled',
      connector_disabled:           'Platform Connection Disabled',
    };

    const EVENT_COLORS = {
      kpi_interpreted:              'var(--accent)',
      signals_selected:             'var(--accent)',
      tools_used:                   'var(--teal)',
      insights_generated:           'var(--green)',
      agent_ideas_generated:        'var(--green)',
      agent_request_submitted:      'var(--amber)',
      access_checked:               'var(--accent)',
      access_gap_detected:          'var(--red)',
      access_request_recommended:   'var(--amber)',
      connector_access_insufficient:'var(--red)',
      access_request_submitted:     'var(--amber)',
      connector_configured:         'var(--teal)',
      connector_health_check:       'var(--teal)',
    };

    function evidenceNarrative(ev) {
      const p = ev.payload || {};
      switch (ev.event_type) {
        case 'kpi_interpreted':
          return `Governance objective "${p.kpi_id || p.kpi || '—'}" interpreted for ${p.persona_id || ev.persona_id || 'role'}.`;
        case 'signals_selected':
          return `${(p.signals || []).length || 'Multiple'} data requirement(s) determined for this objective.`;
        case 'tools_used':
          return `${(p.tools || []).length || 'Multiple'} tool(s) used to gather data from connected platforms.`;
        case 'insights_generated':
          return `Governance insights produced — ${(p.insights || []).length || ''} recommendation(s) available.`;
        case 'agent_ideas_generated':
          return `${(p.ideas || []).length || ''} candidate agent(s) identified from governance signals.`;
        case 'agent_request_submitted':
          return `Agent build request submitted: "${p.agent_idea_id || '—'}".`;
        case 'access_checked':
          return `Access permissions verified for ${p.persona_id || ev.persona_id || 'role'} on ${p.connector_id || 'platform'}.`;
        case 'access_gap_detected':
          return `Missing permission on ${p.platform_id || p.connector_id || 'platform'} — this data point cannot be retrieved without additional access. Submit a permission request for the designated approver.`;
        case 'access_request_recommended':
          return `Least-privilege permission request recommended for ${p.platform_id || 'platform'}. Human approval required before any access is granted.`;
        case 'connector_configured':
          return `Platform connection "${p.connector_id || ''}" updated to ${p.mode || 'mock'} mode.`;
        case 'connector_health_check':
          return `Platform connection verified for "${p.connector_id || ''}" — status: ${p.health?.status || 'checked'}.`;
        case 'connector_enabled':
          return `Platform connection "${p.connector_id || ''}" enabled and available to the governance workflow.`;
        default:
          return ev.event_type.replace(/_/g, ' ');
      }
    }

    const reverse = [...events].reverse();
    content.innerHTML = `
      <div style="border-top:1px solid var(--border);">
        ${reverse.map((ev, idx) => {
          const color = EVENT_COLORS[ev.event_type] || 'var(--text-3)';
          const label = EVENT_LABELS[ev.event_type] || ev.event_type.replace(/_/g, ' ');
          const narrative = evidenceNarrative(ev);
          const ts = (ev.timestamp || '').slice(0, 19).replace('T', ' ');
          const isLast = idx === reverse.length - 1;
          return `
            <div class="ledger-entry">
              <div class="ledger-line">
                <div class="ledger-dot" style="background:${color}"></div>
                ${!isLast ? '<div class="ledger-rule"></div>' : ''}
              </div>
              <div class="ledger-content">
                <div class="ledger-event-label">${esc(label)}</div>
                <div class="ledger-narrative">${esc(narrative)}</div>
                <div class="ledger-meta">
                  ${ev.persona_id ? `${esc(fmtId(ev.persona_id))} &middot; ` : ''}${ts}
                </div>
              </div>
            </div>
          `;
        }).join('')}
      </div>
    `;

    // Filter
    document.getElementById('evidence-filter').addEventListener('input', e => {
      const text = e.target.value.toLowerCase();
      content.querySelectorAll('.ledger-entry').forEach(item => {
        const label = item.querySelector('.ledger-event-label')?.textContent || '';
        item.style.display = !text || label.toLowerCase().includes(text) ? '' : 'none';
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
                <div class="registry-col-label">Governance Recommendation</div>
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
