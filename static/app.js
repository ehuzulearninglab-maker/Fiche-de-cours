let SOUS_MATIERES = {};
let LAST_BASE_NAME = '';

document.addEventListener('DOMContentLoaded', () => {
    loadKBStats();
    loadSousMatieres();
    setupFileUploads();
    setupForm();
    setupProvidersStatus();
    setupAdmin();
    setupResultTabs();
    setupRegenerate();
});

// État des clés serveur par fournisseur ({ openai: { server_key: true }, ... })
let PROVIDER_STATUS = {};

function setupProvidersStatus() {
    const providerSelect = document.getElementById('provider');
    const apiKeyInput = document.getElementById('api_key');
    const optionalHint = document.getElementById('api_key_optional_hint');
    if (!providerSelect || !apiKeyInput) return;

    function applyStatus() {
        const pid = providerSelect.value;
        const hasServerKey = !!(PROVIDER_STATUS[pid] && PROVIDER_STATUS[pid].server_key);
        if (hasServerKey) {
            apiKeyInput.placeholder = 'Optionnel — la clé serveur sera utilisée';
            apiKeyInput.required = false;
            if (optionalHint) optionalHint.style.display = '';
        } else {
            apiKeyInput.placeholder = 'Entrez votre clé API…';
            apiKeyInput.required = true;
            if (optionalHint) optionalHint.style.display = 'none';
        }
    }

    fetch('/providers/status')
        .then(r => r.json())
        .then(data => {
            PROVIDER_STATUS = data || {};
            applyStatus();
        })
        .catch(() => {
            // En cas d'erreur, garde le comportement par défaut (clé requise)
            apiKeyInput.required = true;
        });

    providerSelect.addEventListener('change', applyStatus);
}

// ===== Admin (only active when token in URL/header) =====
function adminToken() {
    const params = new URLSearchParams(window.location.search);
    return params.get('admin') || '';
}

function isAdminActive() {
    return !!document.querySelector('.admin-section');
}

async function adminFetch(url, opts = {}) {
    const token = adminToken();
    const sep = url.includes('?') ? '&' : '?';
    const fullUrl = token ? `${url}${sep}admin=${encodeURIComponent(token)}` : url;
    return fetch(fullUrl, opts);
}

function setupAdmin() {
    if (!isAdminActive()) return;

    // Tabs
    const tabs = document.querySelectorAll('.admin-tab');
    const panels = document.querySelectorAll('.admin-panel');
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            tabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            const id = tab.getAttribute('data-tab');
            panels.forEach(p => {
                p.style.display = p.getAttribute('data-panel') === id ? '' : 'none';
            });
        });
    });
    if (tabs.length) tabs[0].click();

    // Doc upload + list
    document.querySelectorAll('.admin-panel input[type="file"][data-category]').forEach(input => {
        input.addEventListener('change', async (e) => {
            const file = e.target.files?.[0];
            const category = e.target.getAttribute('data-category');
            if (!file) return;
            const fd = new FormData();
            fd.append('category', category);
            fd.append('file', file);
            const r = await adminFetch('/admin/docs', { method: 'POST', body: fd });
            if (r.ok) refreshAdminDocs(category);
            else alert('Erreur upload: ' + (await r.text()));
            e.target.value = '';
        });
    });
    Object.keys(window.__admin_categories || {}).forEach(refreshAdminDocs);
    document.querySelectorAll('.admin-doc-list[data-list]').forEach(ul => {
        refreshAdminDocs(ul.getAttribute('data-list'));
    });

    // Instructions
    adminFetch('/admin/instructions').then(r => r.json()).then(d => {
        const ta = document.getElementById('admin_instructions');
        if (ta && typeof d.instructions === 'string') ta.value = d.instructions;
    });
    const saveBtn = document.getElementById('saveAdminInstructions');
    if (saveBtn) {
        saveBtn.addEventListener('click', async () => {
            const text = document.getElementById('admin_instructions').value;
            const status = document.getElementById('adminInstructionsStatus');
            status.textContent = 'Enregistrement…';
            const r = await adminFetch('/admin/instructions', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ instructions: text })
            });
            status.textContent = r.ok ? 'Enregistré' : 'Erreur';
            setTimeout(() => status.textContent = '', 2500);
        });
    }

    // API keys
    refreshAdminKeys();

    // Defaults (fournisseur/modèle par défaut pour les utilisateurs non-admins)
    setupAdminDefaults();
}

async function setupAdminDefaults() {
    const sel = document.getElementById('default_provider');
    const inp = document.getElementById('default_model');
    const btn = document.getElementById('saveAdminDefaults');
    const status = document.getElementById('adminDefaultsStatus');
    if (!sel || !inp || !btn) return;
    try {
        const r = await adminFetch('/admin/settings');
        if (r.ok) {
            const d = await r.json();
            if (d.default_provider) sel.value = d.default_provider;
            if (d.default_model) inp.value = d.default_model;
        }
    } catch (_) {}
    btn.addEventListener('click', async () => {
        status.textContent = 'Enregistrement…';
        const r = await adminFetch('/admin/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                default_provider: sel.value,
                default_model: inp.value,
            })
        });
        status.textContent = r.ok ? 'Enregistré' : 'Erreur';
        setTimeout(() => status.textContent = '', 2500);
    });
}

function _formatMoney(v, unit) {
    if (typeof v !== 'number' || !isFinite(v)) return '';
    const u = unit === 'USD' ? '$' : (unit || '');
    return `${u}${v.toFixed(2)}`;
}

function renderQuotaDetails(info) {
    const q = info.quota;
    if (!q) {
        if (info.supports_quota && info.configured) {
            return '<span class="key-quota-sub">Solde non lu</span>';
        }
        return '';
    }
    const parts = [];
    if (typeof q.ratio_remaining === 'number') {
        const pct = Math.round(q.ratio_remaining * 100);
        parts.push(`<span class="key-quota-sub">Reste <strong>${pct}%</strong>`
            + (typeof q.remaining === 'number' ? ` (${escapeHtml(_formatMoney(q.remaining, q.unit))})` : '') + '</span>');
    } else if (typeof q.usage === 'number') {
        // Clé sans limite fixée (pay-as-you-go) : on affiche seulement la consommation.
        parts.push(`<span class="key-quota-sub">Consommé ${escapeHtml(_formatMoney(q.usage, q.unit))}</span>`);
    }
    return parts.join(' ');
}

function renderHealthBadge(info) {
    if (!info.configured) {
        return '<span class="key-health-unknown">—</span>';
    }
    const map = {
        ok: { cls: 'key-health-ok', label: 'OK' },
        almost_exhausted: { cls: 'key-health-warn-strong', label: 'Presque épuisée' },
        rate_limit: { cls: 'key-health-warn', label: 'Limite temporaire' },
        busy: { cls: 'key-health-warn', label: 'Service surchargé' },
        exhausted: { cls: 'key-health-bad', label: 'Quota épuisé' },
        invalid: { cls: 'key-health-bad', label: 'Clé invalide' },
        error: { cls: 'key-health-warn', label: 'Erreur' },
        unknown: { cls: 'key-health-unknown', label: 'Inconnu — testez' },
    };
    const h = info.health || 'unknown';
    const m = map[h] || map.unknown;
    let extra = '';
    if (info.health_message && (h === 'exhausted' || h === 'invalid' || h === 'error')) {
        extra = ` <span class="key-health-msg" title="${escapeHtml(info.health_message)}">ⓘ</span>`;
    }
    const quotaLine = renderQuotaDetails(info);
    return `<div class="key-health-line">`
        + `<span class="${m.cls}">${escapeHtml(m.label)}</span>${extra}`
        + `<button type="button" class="btn-key-test" title="Tester la clé maintenant">Tester</button>`
        + `</div>`
        + (quotaLine ? `<div class="key-health-line">${quotaLine}</div>` : '');
}

function updateKeysHealthBanner(data) {
    const banner = document.getElementById('adminKeysHealthBanner');
    if (!banner) return;
    const exhausted = [];
    const almost = [];
    const invalid = [];
    Object.entries(data).forEach(([pid, info]) => {
        if (!info.configured) return;
        if (info.health === 'exhausted') exhausted.push(info.name || pid);
        else if (info.health === 'invalid') invalid.push(info.name || pid);
        else if (info.health === 'almost_exhausted') almost.push(info.name || pid);
    });
    if (!exhausted.length && !invalid.length && !almost.length) {
        banner.style.display = 'none';
        banner.innerHTML = '';
        banner.className = 'admin-keys-banner';
        return;
    }
    const parts = [];
    if (exhausted.length) {
        parts.push(`<strong>Quota épuisé :</strong> ${exhausted.map(escapeHtml).join(', ')}. Pensez à renouveler ou recharger ces clés API.`);
    }
    if (invalid.length) {
        parts.push(`<strong>Clé invalide :</strong> ${invalid.map(escapeHtml).join(', ')}. Vérifiez la valeur ou regénérez la clé.`);
    }
    if (almost.length) {
        parts.push(`<strong>Presque épuisée :</strong> ${almost.map(escapeHtml).join(', ')}. Anticipez le renouvellement avant épuisement total.`);
    }
    banner.innerHTML = parts.join('<br>');
    // Rouge si épuisé/invalide, orange si seulement presque épuisé.
    banner.className = (exhausted.length || invalid.length)
        ? 'admin-keys-banner admin-keys-banner-critical'
        : 'admin-keys-banner admin-keys-banner-warn';
    banner.style.display = 'block';
}

async function refreshAdminKeys() {
    const tbody = document.getElementById('adminKeysBody');
    if (!tbody) return;
    const r = await adminFetch('/admin/api_keys');
    if (!r.ok) return;
    const data = await r.json();
    updateKeysHealthBanner(data);
    const rows = Object.entries(data).map(([pid, info]) => `
        <tr data-pid="${escapeHtml(pid)}">
            <td>${escapeHtml(info.name || pid)}</td>
            <td>${info.configured
                ? `<span class="key-ok">configurée</span> <code>${escapeHtml(info.masked || '')}</code>`
                : '<span class="key-ko">non configurée</span>'}</td>
            <td class="admin-key-health">${renderHealthBadge(info)}</td>
            <td><input type="password" class="admin-key-input" placeholder="Coller la clé…"></td>
            <td>
                <button type="button" class="btn-key-save">Enregistrer</button>
                ${info.configured ? '<button type="button" class="btn-key-del">Supprimer</button>' : ''}
            </td>
        </tr>
    `).join('');
    tbody.innerHTML = rows;
    tbody.querySelectorAll('.btn-key-test').forEach(btn => {
        btn.addEventListener('click', async () => {
            const tr = btn.closest('tr');
            const pid = tr.getAttribute('data-pid');
            const status = document.getElementById('adminKeysStatus');
            const cell = tr.querySelector('.admin-key-health');
            if (cell) cell.innerHTML = '<span class="key-health-unknown">Test en cours…</span>';
            if (status) status.textContent = `Test ${pid}…`;
            try {
                const r = await adminFetch(`/admin/api_keys/${encodeURIComponent(pid)}/test`, { method: 'POST' });
                if (!r.ok) throw new Error('HTTP ' + r.status);
                if (status) status.textContent = '';
            } catch (e) {
                if (status) status.textContent = 'Erreur de test : ' + e.message;
            }
            await refreshAdminKeys();
        });
    });
    tbody.querySelectorAll('.btn-key-save').forEach(btn => {
        btn.addEventListener('click', async () => {
            const tr = btn.closest('tr');
            const pid = tr.getAttribute('data-pid');
            const input = tr.querySelector('.admin-key-input');
            const key = (input.value || '').trim();
            if (!key) { alert('Colle une clé non vide.'); return; }
            const status = document.getElementById('adminKeysStatus');
            status.textContent = 'Enregistrement…';
            const r = await adminFetch('/admin/api_keys', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ provider: pid, api_key: key })
            });
            if (r.ok) {
                status.textContent = 'Clé enregistrée';
                input.value = '';
                await refreshAdminKeys();
                // Rafraîchit aussi l'état côté formulaire utilisateur (si on est sur /formulaire).
                refreshFormProviderStatus();
            } else {
                status.textContent = 'Erreur';
            }
            setTimeout(() => status.textContent = '', 3000);
        });
    });
    tbody.querySelectorAll('.btn-key-del').forEach(btn => {
        btn.addEventListener('click', async () => {
            const tr = btn.closest('tr');
            const pid = tr.getAttribute('data-pid');
            if (!confirm(`Supprimer la clé ${pid} ?`)) return;
            const r = await adminFetch('/admin/api_keys', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ provider: pid, api_key: '' })
            });
            if (r.ok) {
                await refreshAdminKeys();
                refreshFormProviderStatus();
            }
        });
    });
}

// Rafraîchit l'état du select #provider sur le formulaire utilisateur.
// No-op sur la page /admin (qui n'a pas ce select) — évite un TypeError.
function refreshFormProviderStatus() {
    return fetch('/providers/status')
        .then(x => x.json())
        .then(d => {
            PROVIDER_STATUS = d || {};
            const provEl = document.getElementById('provider');
            if (provEl) provEl.dispatchEvent(new Event('change'));
        })
        .catch(() => {});
}

async function refreshAdminDocs(category) {
    const ul = document.querySelector(`.admin-doc-list[data-list="${category}"]`);
    if (!ul) return;
    const r = await adminFetch(`/admin/docs?category=${encodeURIComponent(category)}`);
    if (!r.ok) return;
    const docs = await r.json();
    if (!Array.isArray(docs) || docs.length === 0) {
        ul.innerHTML = '<li class="admin-doc-empty">Aucun document chargé.</li>';
        return;
    }
    ul.innerHTML = docs.map(d => `
        <li class="admin-doc-item">
            <span class="admin-doc-name">${escapeHtml(d.name)}</span>
            <span class="admin-doc-date">${escapeHtml(d.uploaded_at || '')}</span>
            <button type="button" class="btn-doc-del" data-cat="${escapeHtml(category)}" data-name="${escapeHtml(d.name)}">Supprimer</button>
        </li>
    `).join('');
    ul.querySelectorAll('.btn-doc-del').forEach(btn => {
        btn.addEventListener('click', async () => {
            if (!confirm(`Supprimer ${btn.getAttribute('data-name')} ?`)) return;
            const cat = btn.getAttribute('data-cat');
            const name = btn.getAttribute('data-name');
            const r = await adminFetch(`/admin/docs?category=${encodeURIComponent(cat)}&name=${encodeURIComponent(name)}`, { method: 'DELETE' });
            if (r.ok) refreshAdminDocs(cat);
        });
    });
}

function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

// ===== Result tabs (Aperçu / Modifier) =====
function setupResultTabs() {
    document.querySelectorAll('.result-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.result-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            const id = tab.getAttribute('data-tab');
            document.getElementById('fichePreview').style.display = id === 'preview' ? '' : 'none';
            document.getElementById('ficheEdit').style.display = id === 'edit' ? '' : 'none';
        });
    });
}

function setupRegenerate() {
    const btn = document.getElementById('regenerateBtn');
    if (!btn) return;
    btn.addEventListener('click', async () => {
        const content = document.getElementById('ficheEditTextarea').value;
        const status = document.getElementById('regenerateStatus');
        const btnText = btn.querySelector('.btn-text');
        const btnLoading = btn.querySelector('.btn-loading');
        btn.disabled = true; btnText.style.display = 'none'; btnLoading.style.display = 'inline';
        try {
            const r = await fetch('/regenerate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content, base_name: LAST_BASE_NAME })
            });
            const data = await r.json();
            if (data.error) { status.textContent = 'Erreur : ' + data.error; return; }
            updateDownloadButtons(data);
            // Refresh preview from edited content
            document.getElementById('fichePreview').innerHTML = renderFicheHTML(content);
            status.textContent = 'Word/PDF régénérés depuis votre édition';
            setTimeout(() => status.textContent = '', 4000);
        } catch (e) {
            status.textContent = 'Erreur : ' + e.message;
        } finally {
            btn.disabled = false; btnText.style.display = 'inline'; btnLoading.style.display = 'none';
        }
    });
}

function updateDownloadButtons(data) {
    if (data.base_name) LAST_BASE_NAME = data.base_name;
    const mdBtn = document.getElementById('downloadMd');
    if (mdBtn && data.md_file) {
        mdBtn.href = `/download/${data.md_file}`;
        mdBtn.setAttribute('download', data.md_file);
        mdBtn.style.display = 'inline-block';
    }
    const docxBtn = document.getElementById('downloadDocx');
    if (docxBtn && data.docx_file) {
        docxBtn.href = `/download/${data.docx_file}`;
        docxBtn.setAttribute('download', data.docx_file);
        docxBtn.style.display = 'inline-block';
    }
    const pdfBtn = document.getElementById('downloadPdf');
    if (pdfBtn) {
        if (data.pdf_available && data.pdf_file) {
            pdfBtn.href = `/download/${data.pdf_file}`;
            pdfBtn.setAttribute('download', data.pdf_file);
            pdfBtn.style.display = 'inline-block';
        } else {
            pdfBtn.style.display = 'none';
        }
    }
}

function loadSousMatieres() {
    fetch('/matieres')
        .then(r => r.json())
        .then(data => {
            SOUS_MATIERES = data || {};
            const matiere = document.getElementById('matiere');
            matiere.addEventListener('change', updateSousMatiereOptions);
            updateSousMatiereOptions();
        })
        .catch(() => {
            // keep sous-matière hidden if the endpoint fails
        });
}

function updateSousMatiereOptions() {
    const matiere = document.getElementById('matiere').value;
    const group = document.getElementById('sous_matiere_group');
    const select = document.getElementById('sous_matiere');
    const options = SOUS_MATIERES[matiere] || [];

    // Reset options
    select.innerHTML = '<option value="">— Aucune —</option>';
    if (options.length === 0) {
        group.style.display = 'none';
        select.value = '';
        return;
    }
    for (const name of options) {
        const opt = document.createElement('option');
        opt.value = name;
        opt.textContent = name;
        select.appendChild(opt);
    }
    group.style.display = '';
}

function loadKBStats() {
    const container = document.getElementById('kb_status');
    if (!container) return;
    fetch('/kb/stats')
        .then(r => r.json())
        .then(data => {
            container.innerHTML = `
                <span class="kb-badge">${data.total_documents} documents chargés</span>
                <div class="kb-list">
                    ${data.documents.map(d => `<span class="kb-tag">${d.filename} (${d.pages}p)</span>`).join('')}
                </div>
            `;
        })
        .catch(() => {
            container.innerHTML =
                '<span class="kb-badge" style="background:#E53935;">Base non disponible</span>';
        });
}

function setupFileUploads() {
    document.querySelectorAll('.file-upload').forEach(zone => {
        const input = zone.querySelector('input[type="file"]');

        zone.addEventListener('dragover', e => {
            e.preventDefault();
            zone.classList.add('dragover');
        });
        zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
        zone.addEventListener('drop', e => {
            e.preventDefault();
            zone.classList.remove('dragover');
            if (e.dataTransfer.files.length) {
                input.files = e.dataTransfer.files;
                updateFileLabel(zone, input);
            }
        });

        input.addEventListener('change', () => updateFileLabel(zone, input));
    });
}

function updateFileLabel(zone, input) {
    const label = zone.querySelector('.file-upload-label');
    if (input.files.length > 0) {
        zone.classList.add('has-file');
        const names = Array.from(input.files).map(f => f.name).join(', ');
        label.innerHTML = `
            <span class="file-icon">&#9989;</span>
            <span>${names}</span>
            <span class="file-hint">${input.files.length} fichier(s) sélectionné(s)</span>
        `;
    }
}

function setupForm() {
    const form = document.getElementById('ficheForm');
    if (!form) return;
    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        const btn = document.getElementById('generateBtn');
        const btnText = btn.querySelector('.btn-text');
        const btnLoading = btn.querySelector('.btn-loading');

        btn.disabled = true;
        btnText.style.display = 'none';
        btnLoading.style.display = 'inline';

        const formData = new FormData(form);

        try {
            const resp = await fetch('/generate', {
                method: 'POST',
                body: formData,
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            });

            // Connexion requise : redirige vers la page de login en gardant le
            // formulaire courant en mémoire (l'utilisateur reviendra sur /formulaire?classe=...).
            if (resp.status === 401) {
                const nxt = window.location.pathname + window.location.search;
                window.location.href = '/login?next=' + encodeURIComponent(nxt);
                return;
            }

            // Le serveur peut renvoyer une page HTML d'erreur (502/504 du
            // proxy Render, 413 quand un upload dépasse la limite, etc.).
            // On détecte ce cas pour afficher un message lisible au lieu
            // de "Unexpected token '<'" issu d'un .json() qui plante.
            const ct = resp.headers.get('content-type') || '';
            if (!ct.includes('application/json')) {
                let detail = `Le serveur a répondu HTTP ${resp.status}`;
                if (resp.status === 413) {
                    detail = 'Document trop volumineux (limite côté serveur). Réduisez la taille des PDFs joints.';
                } else if (resp.status === 502 || resp.status === 503 || resp.status === 504) {
                    detail = `Le serveur a mis trop de temps à répondre (HTTP ${resp.status}). Le LLM a peut-être saturé — réessayez dans quelques secondes, ou changez de fournisseur dans l'admin.`;
                } else if (resp.status >= 500) {
                    detail = `Erreur serveur (HTTP ${resp.status}). Réessayez ou contactez l'admin.`;
                }
                showError(detail);
                return;
            }

            const data = await resp.json();

            if (data.error) {
                showError(data.error);
            } else {
                showResults(data);
            }
        } catch (err) {
            showError('Erreur de connexion: ' + err.message);
        } finally {
            btn.disabled = false;
            btnText.style.display = 'inline';
            btnLoading.style.display = 'none';
        }
    });
}

function showError(message) {
    const results = document.getElementById('results');
    results.style.display = 'block';
    results.innerHTML = `<div class="error-msg">Erreur : ${message}</div>`;
    results.scrollIntoView({ behavior: 'smooth' });
}

function showResults(data) {
    const results = document.getElementById('results');
    results.style.display = 'block';

    updateDownloadButtons(data);

    // Render preview
    document.getElementById('fichePreview').innerHTML = renderFicheHTML(data.content);

    // Populate edit textarea with raw markdown
    const ta = document.getElementById('ficheEditTextarea');
    if (ta) ta.value = data.content || '';

    // Reset to preview tab
    document.querySelectorAll('.result-tab').forEach(t => t.classList.toggle('active', t.getAttribute('data-tab') === 'preview'));
    document.getElementById('fichePreview').style.display = '';
    document.getElementById('ficheEdit').style.display = 'none';

    results.scrollIntoView({ behavior: 'smooth' });
}

function renderFicheHTML(content) {
    // Convert markdown-like content to HTML for preview
    let html = '';
    const lines = content.split('\n');
    let inTable = false;
    let tableRows = [];

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i].trim();

        if (line.startsWith('|') && line.includes('|')) {
            // Check if separator line
            if (/^\|[\s\-:|]+\|$/.test(line)) continue;

            if (!inTable) {
                inTable = true;
                tableRows = [];
            }

            const cells = line.split('|').filter((_, idx, arr) => idx > 0 && idx < arr.length - 1)
                .map(c => c.trim());
            tableRows.push(cells);
        } else {
            if (inTable) {
                html += renderTable(tableRows);
                inTable = false;
                tableRows = [];
            }

            if (!line) {
                html += '<br>';
            } else if (line.startsWith('# ')) {
                html += `<h2 style="text-align:center;color:#1B5E20;">${line.substring(2)}</h2>`;
            } else if (line.startsWith('## ')) {
                html += `<h3 style="color:#1B5E20;">${line.substring(3)}</h3>`;
            } else if (line.startsWith('### ')) {
                html += `<h4>${line.substring(4)}</h4>`;
            } else {
                // Handle bold
                let processed = line.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
                html += `<div>${processed}</div>`;
            }
        }
    }

    if (inTable) {
        html += renderTable(tableRows);
    }

    return html;
}

function renderTable(rows) {
    if (rows.length === 0) return '';

    let html = '<table>';

    // First row as header
    html += '<tr>';
    rows[0].forEach(cell => {
        html += `<th>${cell.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')}</th>`;
    });
    html += '</tr>';

    // Data rows
    for (let i = 1; i < rows.length; i++) {
        const isHeader = rows[i][0] && (
            rows[i][0].startsWith('**') ||
            rows[i][0].toUpperCase().includes('PRÉLIMINAIRES') ||
            rows[i][0].toUpperCase().includes('INTRODUCTION') ||
            rows[i][0].toUpperCase().includes('RÉALISATION') ||
            rows[i][0].toUpperCase().includes('RETOUR') ||
            rows[i][0].toUpperCase().includes('MISE EN SITUATION') ||
            rows[i][0].toUpperCase().includes('PROPOSITION') ||
            rows[i][0].toUpperCase().includes('PROBLÉMATIQUE') ||
            rows[i][0].toUpperCase().includes('OBJECTIVATION') ||
            rows[i][0].toUpperCase().includes('ÉVALUATION') ||
            rows[i][0].toUpperCase().includes('PROJECTION') ||
            rows[i][0].toUpperCase().includes('ACTIVITÉS')
        );

        const cls = isHeader ? ' class="section-header"' : '';
        html += `<tr${cls}>`;
        rows[i].forEach(cell => {
            let processed = cell.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
            html += `<td>${processed}</td>`;
        });
        html += '</tr>';
    }

    html += '</table>';
    return html;
}
