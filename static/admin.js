// Admin assistants UI : liste + édition + upload PDFs par classe.
// S'exécute en complément de app.js (qui gère les autres onglets admin).

document.addEventListener('DOMContentLoaded', () => {
    if (!document.querySelector('.admin-section')) return;
    setupAssistantsAdmin();
});

let CURRENT_ASSISTANT_ID = null;

async function setupAssistantsAdmin() {
    const root = document.getElementById('assistantsList');
    if (!root) return;
    await refreshAssistantsList();
    setupAssistantModal();
}

async function refreshAssistantsList() {
    const root = document.getElementById('assistantsList');
    if (!root) return;
    root.innerHTML = '<p class="admin-status">Chargement…</p>';
    let data;
    try {
        const r = await fetch('/admin/assistants', {
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
        });
        if (r.status === 401) { window.location.href = '/login?next=/admin'; return; }
        if (!r.ok) throw new Error(await r.text());
        data = await r.json();
    } catch (e) {
        root.innerHTML = `<p class="admin-status admin-status-err">Erreur : ${escapeHtml(e.message)}</p>`;
        return;
    }
    const list = (data && data.assistants) || [];
    if (!list.length) {
        root.innerHTML = '<p class="admin-status">Aucun assistant. Applique la migration 003.</p>';
        return;
    }
    root.innerHTML = list.map(a => {
        const cls = a.classe || '—';
        const active = !!a.is_active;
        return `
            <article class="assistant-admin-card ${active ? '' : 'assistant-admin-card-off'}">
                <header>
                    <span class="assistant-classe">${escapeHtml(cls)}</span>
                    <span class="assistant-status ${active ? 'assistant-status-on' : 'assistant-status-off'}">
                        ${active ? 'Actif' : 'Désactivé'}
                    </span>
                </header>
                <h4>${escapeHtml(a.name || '')}</h4>
                <p>${escapeHtml(a.description || '')}</p>
                <div class="assistant-admin-actions">
                    <button type="button" class="btn-primary btn-edit-assistant" data-id="${escapeHtml(a.id)}">Éditer</button>
                    <button type="button" class="btn-ghost btn-toggle-assistant"
                            data-id="${escapeHtml(a.id)}" data-active="${active ? '1' : '0'}">
                        ${active ? 'Désactiver' : 'Activer'}
                    </button>
                </div>
            </article>
        `;
    }).join('');

    root.querySelectorAll('.btn-edit-assistant').forEach(btn => {
        btn.addEventListener('click', () => openAssistantModal(btn.getAttribute('data-id')));
    });
    root.querySelectorAll('.btn-toggle-assistant').forEach(btn => {
        btn.addEventListener('click', async () => {
            const id = btn.getAttribute('data-id');
            const wasActive = btn.getAttribute('data-active') === '1';
            const r = await fetch(`/admin/assistants/${encodeURIComponent(id)}`, {
                method: 'PATCH',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest',
                },
                body: JSON.stringify({ is_active: !wasActive }),
            });
            if (r.ok) await refreshAssistantsList();
            else alert('Erreur : ' + (await r.text()));
        });
    });
}

function setupAssistantModal() {
    const close = document.getElementById('assistantEditClose');
    const overlay = document.getElementById('assistantEditOverlay');
    const save = document.getElementById('assistantEditSave');
    const docInput = document.getElementById('assistant_doc_input');
    if (close) close.addEventListener('click', closeAssistantModal);
    if (overlay) {
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) closeAssistantModal();
        });
    }
    if (save) save.addEventListener('click', saveAssistantFromModal);
    if (docInput) {
        docInput.addEventListener('change', uploadAssistantDoc);
    }
}

async function openAssistantModal(assistantId) {
    CURRENT_ASSISTANT_ID = assistantId;
    const overlay = document.getElementById('assistantEditOverlay');
    const status = document.getElementById('assistantEditStatus');
    if (status) status.textContent = '';
    overlay.style.display = 'flex';

    let data;
    try {
        const r = await fetch(`/admin/assistants/${encodeURIComponent(assistantId)}`, {
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
        });
        if (!r.ok) throw new Error(await r.text());
        data = await r.json();
    } catch (e) {
        if (status) status.textContent = 'Erreur : ' + e.message;
        return;
    }
    const a = data.assistant || {};
    document.getElementById('assistantEditTitle').textContent = `Éditer — ${a.name || ''}`;
    setVal('assistant_classe', a.classe || '');
    setVal('assistant_name', a.name || '');
    setVal('assistant_description', a.description || '');
    setVal('assistant_instructions', a.instructions || '');
    document.getElementById('assistant_is_active').checked = !!a.is_active;
    renderAssistantDocs(data.documents || []);
}

function closeAssistantModal() {
    const overlay = document.getElementById('assistantEditOverlay');
    if (overlay) overlay.style.display = 'none';
    CURRENT_ASSISTANT_ID = null;
}

async function saveAssistantFromModal() {
    if (!CURRENT_ASSISTANT_ID) return;
    const status = document.getElementById('assistantEditStatus');
    status.textContent = 'Enregistrement…';
    const payload = {
        name: getVal('assistant_name'),
        description: getVal('assistant_description'),
        instructions: getVal('assistant_instructions'),
        is_active: document.getElementById('assistant_is_active').checked,
    };
    const r = await fetch(`/admin/assistants/${encodeURIComponent(CURRENT_ASSISTANT_ID)}`, {
        method: 'PATCH',
        headers: {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
        },
        body: JSON.stringify(payload),
    });
    if (r.ok) {
        status.textContent = 'Enregistré';
        await refreshAssistantsList();
        setTimeout(() => { status.textContent = ''; }, 2000);
    } else {
        status.textContent = 'Erreur : ' + (await r.text());
    }
}

function _formatBytes(n) {
    if (n < 1024) return n + ' o';
    if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' Ko';
    return (n / (1024 * 1024)).toFixed(1) + ' Mo';
}

function _renderProgress(percent, loaded, total, label) {
    const status = document.getElementById('assistantEditStatus');
    if (!status) return;
    const pct = Math.max(0, Math.min(100, Math.round(percent)));
    const sizeStr = total ? `${_formatBytes(loaded)} / ${_formatBytes(total)}` : _formatBytes(loaded);
    status.innerHTML = `
        <span class="upload-label">${escapeHtml(label)} — ${pct}% (${escapeHtml(sizeStr)})</span>
        <span class="upload-bar"><span class="upload-bar-fill" style="width:${pct}%"></span></span>
    `.trim();
}

function _uploadWithProgress(url, formData, onProgress) {
    return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open('POST', url, true);
        xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
        xhr.responseType = 'text';
        if (xhr.upload && onProgress) {
            xhr.upload.addEventListener('progress', (ev) => {
                if (ev.lengthComputable) {
                    onProgress(ev.loaded, ev.total);
                }
            });
        }
        xhr.onload = () => {
            let payload = null;
            try { payload = JSON.parse(xhr.responseText); } catch (_) {}
            resolve({ status: xhr.status, ok: xhr.status >= 200 && xhr.status < 300, payload, raw: xhr.responseText });
        };
        xhr.onerror = () => reject(new Error('Erreur réseau pendant l\'upload.'));
        xhr.ontimeout = () => reject(new Error('Délai d\'attente dépassé.'));
        xhr.send(formData);
    });
}

async function uploadAssistantDoc(e) {
    if (!CURRENT_ASSISTANT_ID) return;
    const files = Array.from(e.target.files || []);
    if (!files.length) return;
    const status = document.getElementById('assistantEditStatus');
    const assistantId = CURRENT_ASSISTANT_ID;
    const totalBytes = files.reduce((acc, f) => acc + (f.size || 0), 0);
    const baseLabel = files.length === 1
        ? `Upload de ${files[0].name}`
        : `Upload de ${files.length} fichiers (${_formatBytes(totalBytes)})`;
    _renderProgress(0, 0, totalBytes, baseLabel);

    const fd = new FormData();
    files.forEach(f => fd.append('file', f));

    let result;
    try {
        result = await _uploadWithProgress(
            `/admin/assistants/${encodeURIComponent(assistantId)}/documents`,
            fd,
            (loaded, total) => {
                const safeTotal = total || totalBytes || 1;
                _renderProgress((loaded / safeTotal) * 100, loaded, safeTotal, baseLabel);
                // Une fois l'upload réseau fini, le serveur extrait le texte
                // des PDFs (PyMuPDF) — ça peut prendre plusieurs secondes voire
                // minutes sur de gros fichiers. On affiche un message dédié.
                if (loaded >= safeTotal) {
                    status.textContent = 'Traitement côté serveur — extraction du texte, lecture IA des PDFs scannés (peut prendre plusieurs minutes pour les gros PDFs)…';
                }
            },
        );
    } catch (err) {
        status.textContent = 'Erreur réseau : ' + (err && err.message ? err.message : err);
        e.target.value = '';
        return;
    }
    e.target.value = '';

    // Phase serveur (extraction PDF) : la barre passe à 100 % "envoi", on switch vers "Traitement…".
    if (result.ok || (result.payload && result.payload.errors)) {
        // OK
    } else if (result.status === 413) {
        const msg = (result.payload && result.payload.error)
            || `Fichier trop volumineux (limite serveur dépassée).`;
        status.textContent = msg;
        return;
    } else {
        const msg = (result.payload && result.payload.error) || `Erreur ${result.status}`;
        status.textContent = 'Erreur : ' + msg;
        return;
    }

    const payload = result.payload || {};
    const okCount = (payload.documents || []).length;
    const errs = payload.errors || [];
    let msg;
    if (errs.length === 0) {
        msg = okCount === 1 ? 'Document ajouté' : `${okCount} documents ajoutés`;
    } else if (okCount === 0) {
        msg = `Échec — ${errs.length} fichier(s) rejeté(s).`;
    } else {
        msg = `${okCount} ajouté(s), ${errs.length} échoué(s).`;
    }
    status.textContent = msg;
    if (errs.length) {
        const lines = errs.slice(0, 5).map(x => `• ${x.filename} : ${x.error}`).join('\n');
        const more = errs.length > 5 ? `\n…et ${errs.length - 5} autre(s).` : '';
        alert(`Fichiers rejetés :\n${lines}${more}`);
    }

    // Recharge la liste des docs.
    const r2 = await fetch(`/admin/assistants/${encodeURIComponent(assistantId)}`, {
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
    });
    if (r2.ok) {
        const d = await r2.json();
        renderAssistantDocs(d.documents || []);
    }
    setTimeout(() => { status.textContent = ''; }, 4000);
}

function renderAssistantDocs(docs) {
    const ul = document.getElementById('assistantDocsList');
    if (!ul) return;
    if (!docs.length) {
        ul.innerHTML = '<li class="admin-doc-empty">Aucun document chargé.</li>';
        return;
    }
    ul.innerHTML = docs.map(d => {
        const dt = (d.uploaded_at || '').slice(0, 10);
        const sizeKb = d.bytes ? Math.round(d.bytes / 1024) + ' Ko' : '';
        return `
            <li class="admin-doc-item">
                <span class="admin-doc-name">${escapeHtml(d.name)}</span>
                <span class="admin-doc-date">${escapeHtml(dt)} · ${escapeHtml(sizeKb)}</span>
                <button type="button" class="btn-doc-del" data-id="${escapeHtml(d.id)}">Supprimer</button>
            </li>
        `;
    }).join('');
    ul.querySelectorAll('.btn-doc-del').forEach(btn => {
        btn.addEventListener('click', async () => {
            const docId = btn.getAttribute('data-id');
            if (!confirm('Supprimer ce document ?')) return;
            const r = await fetch(
                `/admin/assistants/${encodeURIComponent(CURRENT_ASSISTANT_ID)}/documents/${encodeURIComponent(docId)}`,
                {
                    method: 'DELETE',
                    headers: { 'X-Requested-With': 'XMLHttpRequest' },
                },
            );
            if (r.ok) {
                const r2 = await fetch(`/admin/assistants/${encodeURIComponent(CURRENT_ASSISTANT_ID)}`, {
                    headers: { 'X-Requested-With': 'XMLHttpRequest' },
                });
                if (r2.ok) {
                    const d = await r2.json();
                    renderAssistantDocs(d.documents || []);
                }
            } else {
                alert('Erreur : ' + (await r.text()));
            }
        });
    });
}

function getVal(id) {
    const el = document.getElementById(id);
    return el ? (el.value || '').trim() : '';
}

function setVal(id, v) {
    const el = document.getElementById(id);
    if (el) el.value = v;
}

// escapeHtml est déjà défini dans app.js — protection au cas où app.js n'est pas chargé.
if (typeof escapeHtml === 'undefined') {
    window.escapeHtml = function (s) {
        return String(s).replace(/[&<>"']/g, c => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
        }[c]));
    };
}


// ===== Gestion des utilisateurs =====

let _adminUsersCache = [];

function _formatDate(iso) {
    if (!iso) return '—';
    try {
        const d = new Date(iso);
        if (isNaN(d.getTime())) return '—';
        return d.toLocaleDateString('fr-FR') + ' ' + d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
    } catch (e) {
        return '—';
    }
}

function _formatTokens(n) {
    n = Number(n) || 0;
    if (n === 0) return '0';
    if (n < 1000) return String(n);
    if (n < 1e6) return (n / 1000).toFixed(n < 10000 ? 1 : 0) + ' k';
    return (n / 1e6).toFixed(n < 1e7 ? 2 : 1) + ' M';
}

async function loadAdminUsers() {
    const tbody = document.getElementById('adminUsersBody');
    const status = document.getElementById('adminUsersStatus');
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="8" class="admin-status">Chargement…</td></tr>';
    if (status) status.textContent = '';
    try {
        const r = await fetch('/admin/users', { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
        if (r.status === 401) { window.location.href = '/login?next=/admin'; return; }
        if (!r.ok) {
            const err = await r.json().catch(() => ({}));
            throw new Error(err.error || ('HTTP ' + r.status));
        }
        const data = await r.json();
        _adminUsersCache = data.users || [];
        renderAdminUsers();
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="8" class="admin-status admin-status-err">Erreur : ${escapeHtml(e.message)}</td></tr>`;
    }
}

function renderAdminUsers() {
    const tbody = document.getElementById('adminUsersBody');
    const search = document.getElementById('adminUsersSearch');
    const filterSel = document.getElementById('adminUsersFilter');
    if (!tbody) return;
    const q = (search ? search.value : '').trim().toLowerCase();
    const filter = filterSel ? filterSel.value : 'all';
    const all = (_adminUsersCache || []);
    const totalAdmins = all.filter(u => u.is_admin).length;
    const rows = all.filter(u => {
        if (filter === 'admin' && !u.is_admin) return false;
        if (filter === 'user' && u.is_admin) return false;
        if (filter === 'suspended' && !u.is_suspended) return false;
        if (q) {
            return (u.email || '').toLowerCase().includes(q)
                || (u.full_name || '').toLowerCase().includes(q);
        }
        return true;
    });
    if (!rows.length) {
        tbody.innerHTML = '<tr><td colspan="8" class="admin-status">Aucun utilisateur.</td></tr>';
        return;
    }
    tbody.innerHTML = rows.map(u => {
        const roleBadge = u.is_admin
            ? '<span class="badge badge-admin">Admin</span>'
            : '<span class="badge badge-user">Utilisateur</span>';
        const statusBadges = [];
        if (u.is_suspended) statusBadges.push('<span class="badge badge-suspended">Suspendu</span>');
        else statusBadges.push('<span class="badge badge-active">Actif</span>');
        if (!u.has_profile) statusBadges.push('<span class="badge badge-warn" title="Le profil public.profiles est manquant pour ce compte. Le rôle/suspension ne peuvent pas être modifiés tant que le profil n\'est pas créé.">Profil manquant</span>');
        const tokensCell = `<strong>${escapeHtml(_formatTokens(u.tokens_total))}</strong> <span class="admin-tokens-sub">/ ${escapeHtml(_formatTokens(u.tokens_30d))}</span>`;
        const actions = [];
        if (u.is_self) {
            actions.push('<span class="admin-self-tag">vous</span>');
        } else {
            // Promouvoir / dépromouvoir admin (désactivé si profil manquant)
            if (u.has_profile) {
                if (u.is_admin) {
                    const lastAdmin = totalAdmins <= 1;
                    actions.push(`<button type="button" class="btn-secondary" data-act="demote" data-id="${escapeHtml(u.id)}" data-email="${escapeHtml(u.email)}" ${lastAdmin ? 'disabled title="Impossible : il doit rester au moins un administrateur."' : ''}>Retirer admin</button>`);
                } else {
                    actions.push(`<button type="button" class="btn-secondary" data-act="promote" data-id="${escapeHtml(u.id)}" data-email="${escapeHtml(u.email)}">Promouvoir admin</button>`);
                }
                if (u.is_suspended) {
                    actions.push(`<button type="button" class="btn-secondary" data-act="unsuspend" data-id="${escapeHtml(u.id)}">Réactiver</button>`);
                } else {
                    actions.push(`<button type="button" class="btn-secondary" data-act="suspend" data-id="${escapeHtml(u.id)}">Suspendre</button>`);
                }
            }
            if (u.tokens_total > 0) {
                actions.push(`<button type="button" class="btn-secondary" data-act="reset_usage" data-id="${escapeHtml(u.id)}" data-email="${escapeHtml(u.email)}">Réinitialiser quotas</button>`);
            }
            actions.push(`<button type="button" class="btn-danger" data-act="delete" data-id="${escapeHtml(u.id)}" data-email="${escapeHtml(u.email)}">Supprimer</button>`);
        }
        return `<tr>
            <td>${escapeHtml(u.email || '')}</td>
            <td>${escapeHtml(u.full_name || '')}</td>
            <td>${roleBadge}</td>
            <td>${escapeHtml(_formatDate(u.created_at))}</td>
            <td>${escapeHtml(_formatDate(u.last_sign_in_at))}</td>
            <td class="admin-tokens-cell">${tokensCell}</td>
            <td>${statusBadges.join(' ')}</td>
            <td class="admin-users-actions">${actions.join(' ')}</td>
        </tr>`;
    }).join('');
}

async function _userAction(action, userId, email) {
    const status = document.getElementById('adminUsersStatus');
    let url, method, confirmMsg;
    if (action === 'suspend') {
        url = `/admin/users/${encodeURIComponent(userId)}/suspend`;
        method = 'POST';
        confirmMsg = `Suspendre l'accès de ${email || 'cet utilisateur'} ? Il ne pourra plus se connecter.`;
    } else if (action === 'unsuspend') {
        url = `/admin/users/${encodeURIComponent(userId)}/unsuspend`;
        method = 'POST';
        confirmMsg = `Réactiver l'accès de ${email || 'cet utilisateur'} ?`;
    } else if (action === 'delete') {
        url = `/admin/users/${encodeURIComponent(userId)}`;
        method = 'DELETE';
        const typed = prompt(`Supprimer DÉFINITIVEMENT le compte ${email || ''} et toutes ses données (conversations, messages) ?\n\nTapez SUPPRIMER en majuscules pour confirmer.`);
        if (typed !== 'SUPPRIMER') {
            if (status) status.textContent = 'Suppression annulée.';
            return;
        }
    } else if (action === 'reset_usage') {
        url = `/admin/users/${encodeURIComponent(userId)}/reset_usage`;
        method = 'POST';
        confirmMsg = `Réinitialiser les compteurs de tokens de ${email || 'cet utilisateur'} ? Cette action est irréversible.`;
    } else if (action === 'promote') {
        url = `/admin/users/${encodeURIComponent(userId)}/promote`;
        method = 'POST';
        confirmMsg = `Promouvoir ${email || 'cet utilisateur'} en administrateur ? Il aura accès à la console admin et pourra gérer les autres comptes.`;
    } else if (action === 'demote') {
        url = `/admin/users/${encodeURIComponent(userId)}/demote`;
        method = 'POST';
        confirmMsg = `Retirer le rôle administrateur à ${email || 'cet utilisateur'} ? Il ne pourra plus accéder à la console admin.`;
    } else {
        return;
    }
    if (action !== 'delete' && !confirm(confirmMsg)) return;
    if (status) status.textContent = 'Traitement…';
    try {
        const r = await fetch(url, { method, headers: { 'X-Requested-With': 'XMLHttpRequest' } });
        if (r.status === 401) { window.location.href = '/login?next=/admin'; return; }
        if (!r.ok) {
            const err = await r.json().catch(() => ({}));
            throw new Error(err.error || ('HTTP ' + r.status));
        }
        if (status) status.textContent = 'OK.';
        await loadAdminUsers();
    } catch (e) {
        if (status) {
            status.textContent = 'Erreur : ' + (e.message || e);
            status.classList.add('admin-status-err');
            setTimeout(() => status.classList.remove('admin-status-err'), 5000);
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const usersTab = document.querySelector('.admin-tab[data-tab="users"]');
    const refreshBtn = document.getElementById('adminUsersRefresh');
    const search = document.getElementById('adminUsersSearch');
    const filterSel = document.getElementById('adminUsersFilter');
    const tbody = document.getElementById('adminUsersBody');
    if (usersTab) usersTab.addEventListener('click', loadAdminUsers);
    if (refreshBtn) refreshBtn.addEventListener('click', loadAdminUsers);
    if (search) search.addEventListener('input', renderAdminUsers);
    if (filterSel) filterSel.addEventListener('change', renderAdminUsers);
    if (tbody) {
        tbody.addEventListener('click', (e) => {
            const btn = e.target.closest('button[data-act]');
            if (!btn) return;
            _userAction(btn.dataset.act, btn.dataset.id, btn.dataset.email || '');
        });
    }
});
