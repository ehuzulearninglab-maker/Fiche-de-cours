// chat.js — UI logique pour le mode conversationnel.
// Dépend de window.CHAT_CTX (assistant courant, conversation_id éventuel).

(function () {
    const ctx = window.CHAT_CTX || {};
    const assistant = ctx.assistant || {};
    let currentConversationId = ctx.conversationId || '';

    const els = {
        msgs: document.getElementById('chatMessages'),
        form: document.getElementById('chatForm'),
        input: document.getElementById('chatInput'),
        sendBtn: document.getElementById('chatSendBtn'),
        newBtn: document.getElementById('chatNewBtn'),
        convList: document.getElementById('chatConvList'),
        sidebarToggle: document.getElementById('chatSidebarToggle'),
        sidebarBackdrop: document.getElementById('chatSidebarBackdrop'),
        app: document.querySelector('.chat-app'),
    };

    // Bouton hamburger pour ouvrir/fermer la sidebar sur mobile.
    function toggleSidebar(open) {
        if (!els.app) return;
        const willOpen = (typeof open === 'boolean') ? open : !els.app.classList.contains('sidebar-open');
        els.app.classList.toggle('sidebar-open', willOpen);
    }
    if (els.sidebarToggle) {
        els.sidebarToggle.addEventListener('click', () => toggleSidebar());
    }
    if (els.sidebarBackdrop) {
        els.sidebarBackdrop.addEventListener('click', () => toggleSidebar(false));
    }

    // -----------------------------------------------------------------
    // Helpers
    // -----------------------------------------------------------------
    function escapeHtml(s) {
        return (s || '').replace(/[&<>"']/g, c => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
        }[c]));
    }

    function on401(resp) {
        if (resp && resp.status === 401) {
            const nxt = window.location.pathname + window.location.search;
            window.location.href = '/login?next=' + encodeURIComponent(nxt);
            return true;
        }
        return false;
    }

    function ajaxHeaders(extra) {
        return Object.assign(
            { 'X-Requested-With': 'XMLHttpRequest' },
            extra || {},
        );
    }

    function scrollMessagesToBottom() {
        if (els.msgs) els.msgs.scrollTop = els.msgs.scrollHeight;
    }

    function clearWelcome() {
        const w = els.msgs.querySelector('.chat-welcome');
        if (w) w.remove();
    }

    // Affiche un message dans le fil. `msg` = {id, role, content, files?}
    function renderMessage(msg, opts) {
        opts = opts || {};
        clearWelcome();
        const wrap = document.createElement('div');
        wrap.className = 'chat-msg chat-msg-' + (msg.role || 'user');
        wrap.dataset.messageId = msg.id || '';

        const bubble = document.createElement('div');
        bubble.className = 'chat-bubble';

        if (msg.role === 'assistant') {
            // Si la réponse contient une fiche, on cache le bloc fiche dans
            // le rendu texte (déjà rendu via la card "Fiche prête").
            const raw = msg.content || '';
            const cleaned = stripFicheBlock(raw);
            const hasFiche = extractFiche(raw) !== '';
            // Si tout le message était la fiche (cleaned vide), on n'affiche
            // PAS le contenu brut (sinon on verrait les marqueurs et la fiche
            // dupliquée). Un petit placeholder suffit.
            const fallback = hasFiche
                ? 'Voici la fiche ci-dessous.'
                : raw;
            bubble.innerHTML = renderAssistantMarkdown(cleaned || fallback);
        } else {
            bubble.textContent = msg.content || '';
        }
        wrap.appendChild(bubble);

        const ficheText = extractFiche(msg.content || '');
        if (msg.files && (msg.files.docx_file || msg.files.pdf_file)) {
            wrap.appendChild(renderFicheCard(msg.files, ficheText));
        } else if (opts.embedFicheFromContent) {
            if (ficheText) {
                // Pas de fichiers (cas: message historique non régénéré). On
                // affiche un placeholder qui invite à régénérer.
                wrap.appendChild(renderFichePending(msg.id));
            }
        }

        els.msgs.appendChild(wrap);
        scrollMessagesToBottom();
        return wrap;
    }

    // files = {docx_file, pdf_file, base_name, ...}
    // ficheText = contenu textuel de la fiche (pour l'éditeur)
    function renderFicheCard(files, ficheText) {
        const card = document.createElement('div');
        card.className = 'chat-fiche-card';
        // État courant (mutable pour permettre la régénération sur place).
        const state = {
            files: files || {},
            text: ficheText || '',
        };

        // Vue : titre + liens + boutons
        const renderView = () => {
            card.innerHTML = '';
            const title = document.createElement('div');
            title.className = 'chat-fiche-title';
            title.textContent = 'Fiche prête à télécharger';
            card.appendChild(title);

            const links = document.createElement('div');
            links.className = 'chat-fiche-links';
            if (state.files.docx_file) {
                const a = document.createElement('a');
                a.className = 'btn-primary';
                a.href = '/download/' + encodeURIComponent(state.files.docx_file);
                a.textContent = 'Télécharger Word';
                links.appendChild(a);
            }
            if (state.files.pdf_file) {
                const a = document.createElement('a');
                a.className = 'btn-ghost';
                a.href = '/download/' + encodeURIComponent(state.files.pdf_file);
                a.textContent = 'Télécharger PDF';
                links.appendChild(a);
            }
            if (state.text) {
                const editBtn = document.createElement('button');
                editBtn.type = 'button';
                editBtn.className = 'btn-ghost';
                editBtn.textContent = 'Modifier la fiche';
                editBtn.addEventListener('click', () => openFicheEditor(state, () => renderView()));
                links.appendChild(editBtn);
            }
            card.appendChild(links);
        };

        renderView();
        return card;
    }

    // -----------------------------------------------------------------
    // Éditeur de fiche en modal plein écran (partagé entre toutes les
    // fiche-cards). On l'ouvre avec l'état d'une carte ; à la
    // régénération réussie, on met à jour cet état et on appelle le
    // callback de re-render.
    // -----------------------------------------------------------------
    const ficheModal = (function () {
        const root = document.getElementById('ficheEditorModal');
        if (!root) return null;
        const ta = document.getElementById('ficheEditorTextarea');
        const regenBtn = document.getElementById('ficheEditorRegen');
        const statusEl = document.getElementById('ficheEditorStatus');
        let currentState = null;
        let currentOnSaved = null;
        let autoCloseTimer = null;
        let sessionId = 0;

        function clearAutoClose() {
            if (autoCloseTimer) { clearTimeout(autoCloseTimer); autoCloseTimer = null; }
        }
        function close() {
            clearAutoClose();
            root.classList.remove('is-open');
            root.setAttribute('aria-hidden', 'true');
            document.body.classList.remove('fiche-modal-open');
            currentState = null;
            currentOnSaved = null;
            statusEl.textContent = '';
            regenBtn.disabled = false;
        }
        function open(state, onSaved) {
            clearAutoClose();
            sessionId++;
            currentState = state;
            currentOnSaved = onSaved || null;
            ta.value = state.text || '';
            statusEl.textContent = '';
            regenBtn.disabled = false;
            root.classList.add('is-open');
            root.setAttribute('aria-hidden', 'false');
            document.body.classList.add('fiche-modal-open');
            // Focus sur le textarea après l'animation d'ouverture.
            setTimeout(() => { ta.focus(); ta.setSelectionRange(0, 0); ta.scrollTop = 0; }, 50);
        }
        // Boutons "Annuler" / "×" / clic sur le backdrop.
        root.querySelectorAll('[data-close]').forEach(el => {
            el.addEventListener('click', close);
        });
        // Échap pour fermer.
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && root.classList.contains('is-open')) close();
        });
        regenBtn.addEventListener('click', async () => {
            if (!currentState) return;
            // Capture l'état + le callback dans des locales avant tout
            // await : si le user ferme le modal (et reset currentState) ou
            // ouvre une autre fiche pendant la requête, la fiche d'origine
            // reste correctement mise à jour, sans crash NPE ni écrasement
            // d'une autre fiche par une réponse en retard.
            const stateRef = currentState;
            const onSavedRef = currentOnSaved;
            const sessionRef = sessionId;
            const newText = (ta.value || '').trim();
            if (!newText) { statusEl.textContent = 'Le contenu ne peut pas être vide.'; return; }
            regenBtn.disabled = true;
            statusEl.textContent = 'Régénération en cours…';
            // sessionId est incrémenté à chaque open() : on évite les
            // faux positifs si l'user ferme puis rouvre la même fiche
            // (même state object) pendant la requête.
            const isStillOpen = () => root.classList.contains('is-open') && sessionId === sessionRef;
            try {
                const r = await fetch('/regenerate', {
                    method: 'POST',
                    headers: ajaxHeaders({ 'Content-Type': 'application/json' }),
                    body: JSON.stringify({
                        content: newText,
                        base_name: stateRef.files.base_name || '',
                    }),
                });
                if (on401(r)) return;
                const data = await r.json();
                if (!r.ok || !data.success) {
                    if (isStillOpen()) {
                        statusEl.textContent = data.error || 'Erreur lors de la régénération.';
                        regenBtn.disabled = false;
                    }
                    return;
                }
                // Mise à jour de l'état d'origine (toujours valable même si
                // le modal a été fermé / réutilisé entretemps).
                stateRef.files = {
                    base_name: data.base_name,
                    docx_file: data.docx_file,
                    pdf_file: data.pdf_file,
                };
                stateRef.text = newText;
                if (onSavedRef) onSavedRef();
                if (isStillOpen()) {
                    statusEl.textContent = 'Régénération terminée.';
                    clearAutoClose();
                    autoCloseTimer = setTimeout(() => {
                        autoCloseTimer = null;
                        if (isStillOpen()) close();
                    }, 600);
                }
            } catch (err) {
                if (isStillOpen()) {
                    statusEl.textContent = 'Erreur réseau : ' + (err && err.message ? err.message : err);
                    regenBtn.disabled = false;
                }
            }
        });
        return { open, close };
    }());

    function openFicheEditor(state, onSaved) {
        if (ficheModal) ficheModal.open(state, onSaved);
    }

    function renderFichePending() {
        const card = document.createElement('div');
        card.className = 'chat-fiche-card chat-fiche-pending';
        const t = document.createElement('div');
        t.className = 'chat-fiche-title';
        t.textContent = 'Fiche archivée';
        const h = document.createElement('div');
        h.className = 'chat-fiche-help';
        h.textContent = "Les fichiers Word et PDF de cette fiche ont été nettoyés (rétention 14 jours). Régénère la fiche pour récupérer les téléchargements.";
        card.appendChild(t);
        card.appendChild(h);
        return card;
    }

    function extractFiche(text) {
        const a = '===FICHE_DEBUT===';
        const b = '===FICHE_FIN===';
        const i = text.indexOf(a);
        const j = text.indexOf(b, i >= 0 ? i + a.length : 0);
        if (i < 0 || j < 0) return '';
        return text.substring(i + a.length, j).trim();
    }

    function stripFicheBlock(text) {
        const a = '===FICHE_DEBUT===';
        const b = '===FICHE_FIN===';
        const i = text.indexOf(a);
        const j = text.indexOf(b, i >= 0 ? i + a.length : 0);
        if (i < 0 || j < 0) return text;
        return (text.substring(0, i).trim() + '\n\n' + text.substring(j + b.length).trim()).trim();
    }

    // Markdown très minimaliste (gras + sauts de ligne).
    function renderAssistantMarkdown(text) {
        let s = escapeHtml(text);
        s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
        s = s.replace(/\n{2,}/g, '</p><p>');
        s = s.replace(/\n/g, '<br>');
        return '<p>' + s + '</p>';
    }

    // -----------------------------------------------------------------
    // Conversations sidebar
    // -----------------------------------------------------------------
    async function refreshConversations() {
        try {
            const r = await fetch('/chat/conversations', { headers: ajaxHeaders() });
            if (on401(r)) return;
            const data = await r.json();
            const convs = data.conversations || [];
            if (!convs.length) {
                els.convList.innerHTML = '<li class="chat-conv-empty">Aucune conversation pour l\'instant.</li>';
                return;
            }
            els.convList.innerHTML = '';
            for (const c of convs) {
                const li = document.createElement('li');
                li.className = 'chat-conv-item' + (c.id === currentConversationId ? ' active' : '');
                li.dataset.conversationId = c.id;
                const titleEl = document.createElement('a');
                titleEl.href = '/chat?conversation=' + encodeURIComponent(c.id);
                titleEl.className = 'chat-conv-link';
                const titleText = c.title || 'Conversation';
                titleEl.innerHTML = '<span class="chat-conv-title">' + escapeHtml(titleText) + '</span>'
                    + '<span class="chat-conv-meta">' + escapeHtml(c.assistant_classe || '') + '</span>';
                li.appendChild(titleEl);
                const del = document.createElement('button');
                del.type = 'button';
                del.className = 'chat-conv-del';
                del.title = 'Supprimer la conversation';
                del.innerHTML = '×';
                del.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    deleteConversation(c.id);
                });
                li.appendChild(del);
                els.convList.appendChild(li);
            }
        } catch (err) {
            console.error('refreshConversations', err);
        }
    }

    async function deleteConversation(convId) {
        if (!confirm('Supprimer cette conversation ?')) return;
        const r = await fetch('/chat/conversations/' + encodeURIComponent(convId), {
            method: 'DELETE',
            headers: ajaxHeaders(),
        });
        if (on401(r)) return;
        if (convId === currentConversationId) {
            window.location.href = '/chat?assistant=' + encodeURIComponent(assistant.id || '');
            return;
        }
        refreshConversations();
    }

    // -----------------------------------------------------------------
    // Charger l'historique d'une conversation
    // -----------------------------------------------------------------
    async function loadConversation(convId) {
        try {
            const r = await fetch('/chat/conversations/' + encodeURIComponent(convId), {
                headers: ajaxHeaders(),
            });
            if (on401(r)) return;
            if (!r.ok) {
                console.error('Conversation introuvable');
                return;
            }
            const data = await r.json();
            els.msgs.innerHTML = '';
            const messages = data.messages || [];
            for (const m of messages) {
                // Les fichiers sont stockés dans metadata côté serveur.
                if (!m.files && m.metadata && (m.metadata.docx_file || m.metadata.pdf_file)) {
                    m.files = {
                        base_name: m.metadata.base_name || '',
                        docx_file: m.metadata.docx_file || null,
                        pdf_file: m.metadata.pdf_file || null,
                    };
                }
                renderMessage(m, { embedFicheFromContent: true });
            }
            scrollMessagesToBottom();
        } catch (err) {
            console.error('loadConversation', err);
        }
    }

    // -----------------------------------------------------------------
    // Envoi d'un message
    // -----------------------------------------------------------------
    async function ensureConversation() {
        if (currentConversationId) return currentConversationId;
        const r = await fetch('/chat/conversations', {
            method: 'POST',
            headers: ajaxHeaders({ 'Content-Type': 'application/json' }),
            body: JSON.stringify({ assistant_id: assistant.id }),
        });
        if (on401(r)) return '';
        if (!r.ok) {
            const err = await r.json().catch(() => ({}));
            alert(err.error || 'Impossible de créer la conversation.');
            return '';
        }
        const data = await r.json();
        currentConversationId = (data.conversation || {}).id || '';
        // Mettre à jour l'URL pour pouvoir recharger.
        if (currentConversationId) {
            const newUrl = '/chat?conversation=' + encodeURIComponent(currentConversationId);
            window.history.replaceState({}, '', newUrl);
        }
        refreshConversations();
        return currentConversationId;
    }

    function setBusy(busy) {
        els.input.disabled = busy;
        els.sendBtn.disabled = busy;
        // NB : on ne touche pas au contenu (l'icône SVG du bouton).
        // L'état désactivé est déjà stylé via CSS (.chat-send-btn:disabled).
        els.sendBtn.classList.toggle('is-busy', !!busy);
    }

    function showTyping() {
        const t = document.createElement('div');
        t.className = 'chat-msg chat-msg-assistant chat-typing';
        t.id = 'chatTyping';
        t.innerHTML = '<div class="chat-bubble">L\'assistant rédige…</div>';
        els.msgs.appendChild(t);
        scrollMessagesToBottom();
    }
    function hideTyping() {
        const t = document.getElementById('chatTyping');
        if (t) t.remove();
    }

    async function sendMessage(content) {
        if (!content.trim()) return;
        setBusy(true);

        const convId = await ensureConversation();
        if (!convId) {
            setBusy(false);
            return;
        }

        // Affiche immédiatement le message utilisateur.
        renderMessage({ role: 'user', content: content });
        els.input.value = '';
        els.input.style.height = 'auto';

        showTyping();

        try {
            const r = await fetch(
                '/chat/conversations/' + encodeURIComponent(convId) + '/messages',
                {
                    method: 'POST',
                    headers: ajaxHeaders({ 'Content-Type': 'application/json' }),
                    body: JSON.stringify({ content: content }),
                },
            );
            hideTyping();
            if (on401(r)) return;
            const data = await r.json();
            if (!r.ok) {
                renderMessage({
                    role: 'assistant',
                    content: '[Erreur] ' + (data.error || 'Erreur lors de la génération.'),
                });
                return;
            }
            const am = data.assistant_message || {};
            am.files = data.files || null;
            renderMessage(am);
            refreshConversations();
        } catch (err) {
            hideTyping();
            renderMessage({
                role: 'assistant',
                content: '[Erreur réseau] ' + (err && err.message ? err.message : err),
            });
        } finally {
            setBusy(false);
            els.input.focus();
        }
    }

    // -----------------------------------------------------------------
    // Wiring
    // -----------------------------------------------------------------
    els.form.addEventListener('submit', (e) => {
        e.preventDefault();
        sendMessage(els.input.value);
    });

    els.input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage(els.input.value);
        }
    });

    // Auto-grow du textarea principal selon le contenu.
    function autoGrowInput() {
        const ta = els.input;
        ta.style.height = 'auto';
        const maxH = 200;
        ta.style.height = Math.min(ta.scrollHeight, maxH) + 'px';
    }
    els.input.addEventListener('input', autoGrowInput);
    autoGrowInput();

    els.newBtn.addEventListener('click', () => {
        window.location.href = '/chat?assistant=' + encodeURIComponent(assistant.id || '');
    });

    document.querySelectorAll('.chat-suggestion').forEach(btn => {
        btn.addEventListener('click', () => {
            els.input.value = btn.textContent.trim();
            els.input.focus();
        });
    });

    // Boot
    refreshConversations();
    if (currentConversationId) {
        loadConversation(currentConversationId);
    }
    els.input.focus();
})();
