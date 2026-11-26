(function () {
    "use strict";

    const $ = (id) => document.getElementById(id);
    const els = {
        list: $("ca-conv-list"),
        messages: $("ca-messages"),
        empty: $("ca-empty"),
        form: $("ca-form"),
        input: $("ca-input"),
        send: $("ca-send"),
        title: $("ca-title"),
        sidebar: $("ca-sidebar"),
        toggle: $("ca-toggle"),
    };
    let currentId = null;
    let busy = false;
    let rpcId = 0;

    // ------------------------------------------------------------------
    // JSON-RPC verso Odoo
    // ------------------------------------------------------------------
    async function rpc(url, params) {
        const resp = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "same-origin",
            body: JSON.stringify({ jsonrpc: "2.0", method: "call", params: params || {}, id: ++rpcId }),
        });
        if (resp.status === 401 || resp.redirected) {
            window.location.href = "/web/login?redirect=/cruise_assistant";
            throw new Error("Sessione scaduta");
        }
        const data = await resp.json();
        if (data.error) {
            const msg = (data.error.data && data.error.data.message) || data.error.message || "Errore";
            throw new Error(msg);
        }
        return data.result;
    }

    // ------------------------------------------------------------------
    // Markdown minimale (l'input viene sempre escapato prima)
    // ------------------------------------------------------------------
    function escapeHtml(s) {
        return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
    }

    function inline(s) {
        return s
            .replace(/`([^`]+)`/g, "<code>$1</code>")
            .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
            .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>")
            .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+|\/[^\s)]*)\)/g,
                '<a href="$2" target="_blank" rel="noopener">$1</a>');
    }

    function unescapeHtml(s) {
        return s.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"')
            .replace(/&#39;/g, "'").replace(/&amp;/g, "&");
    }

    // ------------------------------------------------------------------
    // Blocchi interattivi emessi dal modello (```cruises, ```choices,
    // ```summary): JSON trasformato in card. Ogni stringa viene escapata.
    // ------------------------------------------------------------------
    function parseBlock(escapedJson) {
        try {
            return JSON.parse(unescapeHtml(escapedJson));
        } catch (e) {
            return null;
        }
    }

    const str = (v) => (typeof v === "string" || typeof v === "number") ? String(v).trim() : "";

    function cruiseImage(id) {
        return id > 0
            ? '<img src="/web/image/codestorm.cruises/' + id + '/image/640x400" alt="" loading="lazy" onerror="this.remove()">'
            : "";
    }

    // ```cruises: [{"id": 1, "name": "..."}] -> card con immagine e nome.
    function renderCruiseCards(escapedJson) {
        const items = parseBlock(escapedJson);
        if (!Array.isArray(items)) return null;
        const cards = items.filter((c) => c && typeof c.name === "string" && c.name.trim()).map((c) => {
            const name = escapeHtml(c.name.trim());
            return '<button type="button" class="ca-cruise-card ca-pick" data-value="' + name + '" title="' + name + '">'
                + cruiseImage(parseInt(c.id, 10)) + '<span class="ca-cruise-name">' + name + "</span></button>";
        });
        return cards.length ? '<div class="ca-cruise-cards ca-interactive">' + cards.join("") + "</div>" : null;
    }

    // ```choices: {"multiple": false, "options": [{"label", "description"?, "icon"?}],
    //              "confirm_label"?, "none_label"?}
    // Scelta singola: il click invia la label. Multipla: le card si
    // selezionano e "Conferma" invia le label scelte (o none_label).
    function renderChoices(escapedJson) {
        const data = parseBlock(escapedJson);
        const options = data && Array.isArray(data.options) ? data.options : null;
        if (!options) return null;
        const multiple = !!data.multiple;
        const cards = options.filter((o) => o && str(o.label)).map((o) => {
            const label = escapeHtml(str(o.label));
            const icon = str(o.icon) ? '<span class="ca-choice-icon">' + escapeHtml(str(o.icon)) + "</span>" : "";
            const desc = str(o.description) ? '<small>' + escapeHtml(str(o.description)) + "</small>" : "";
            return '<button type="button" class="ca-choice' + (multiple ? " ca-toggle-choice" : " ca-pick")
                + '" data-value="' + label + '">' + icon + '<span class="ca-choice-label">' + label + "</span>"
                + desc + (multiple ? '<span class="ca-check" aria-hidden="true"></span>' : "") + "</button>";
        });
        if (!cards.length) return null;
        let html = '<div class="ca-choices ca-interactive' + (multiple ? " multiple" : "") + '"'
            + (multiple ? ' data-none="' + escapeHtml(str(data.none_label) || "Nessuna") + '"' : "") + ">"
            + '<div class="ca-choice-grid">' + cards.join("") + "</div>";
        if (multiple) {
            html += '<button type="button" class="ca-choice-confirm">'
                + escapeHtml(str(data.confirm_label) || "Conferma") + "</button>";
        }
        return html + "</div>";
    }

    // ```summary: {"title"?, "cruise_id"?, "rows": [{"label", "value"}], "note"?}
    // Riepilogo della prenotazione con il pulsante "Prenota Crociera".
    function renderSummary(escapedJson) {
        const data = parseBlock(escapedJson);
        const rows = data && Array.isArray(data.rows) ? data.rows.filter((r) => r && str(r.label)) : null;
        if (!rows || !rows.length) return null;
        const img = cruiseImage(parseInt(data.cruise_id, 10));
        return '<div class="ca-summary ca-interactive">'
            + (img ? '<div class="ca-summary-img">' + img + "</div>" : "")
            + '<div class="ca-summary-body">'
            + "<h4>" + escapeHtml(str(data.title) || "Riepilogo della tua crociera") + "</h4>"
            + "<dl>" + rows.map((r) => "<dt>" + escapeHtml(str(r.label)) + "</dt><dd>"
                + escapeHtml(Array.isArray(r.value) ? r.value.map(str).filter(Boolean).join(", ") : str(r.value))
                + "</dd>").join("") + "</dl>"
            + (str(data.note) ? '<p class="ca-summary-note">' + escapeHtml(str(data.note)) + "</p>" : "")
            + '<button type="button" class="ca-book">Prenota Crociera</button>'
            + "</div></div>";
    }

    const BLOCK_RENDERERS = { cruises: renderCruiseCards, choices: renderChoices, summary: renderSummary };

    function renderMarkdown(src) {
        const lines = escapeHtml(src).split("\n");
        const out = [];
        let i = 0;
        while (i < lines.length) {
            const line = lines[i];
            if (/^```/.test(line)) {
                const lang = line.slice(3).trim().toLowerCase();
                const code = [];
                i++;
                while (i < lines.length && !/^```/.test(lines[i])) code.push(lines[i++]);
                i++;
                const cards = BLOCK_RENDERERS[lang] ? BLOCK_RENDERERS[lang](code.join("\n")) : null;
                out.push(cards || "<pre><code>" + code.join("\n") + "</code></pre>");
                continue;
            }
            if (/^\s*\|.*\|\s*$/.test(line) && i + 1 < lines.length && /^\s*\|[\s:|-]+\|\s*$/.test(lines[i + 1])) {
                const cells = (l) => l.trim().replace(/^\||\|$/g, "").split("|").map((c) => inline(c.trim()));
                let html = "<table><thead><tr>" + cells(line).map((c) => "<th>" + c + "</th>").join("") + "</tr></thead><tbody>";
                i += 2;
                while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) {
                    html += "<tr>" + cells(lines[i++]).map((c) => "<td>" + c + "</td>").join("") + "</tr>";
                }
                out.push(html + "</tbody></table>");
                continue;
            }
            const h = line.match(/^(#{1,4})\s+(.*)$/);
            if (h) {
                out.push((h[1].length <= 2 ? "<h3>" : "<h4>") + inline(h[2]) + (h[1].length <= 2 ? "</h3>" : "</h4>"));
                i++;
                continue;
            }
            if (/^\s*([-*]|\d+\.)\s+/.test(line)) {
                const ordered = /^\s*\d+\./.test(line);
                const items = [];
                while (i < lines.length && /^\s*([-*]|\d+\.)\s+/.test(lines[i])) {
                    items.push("<li>" + inline(lines[i].replace(/^\s*([-*]|\d+\.)\s+/, "")) + "</li>");
                    i++;
                }
                out.push((ordered ? "<ol>" : "<ul>") + items.join("") + (ordered ? "</ol>" : "</ul>"));
                continue;
            }
            if (!line.trim()) { i++; continue; }
            const para = [];
            while (i < lines.length && lines[i].trim() && !/^(```|#{1,4}\s|\s*([-*]|\d+\.)\s+|\s*\|)/.test(lines[i])) {
                para.push(inline(lines[i++]));
            }
            if (!para.length) { para.push(inline(lines[i++])); }
            out.push("<p>" + para.join("<br>") + "</p>");
        }
        return out.join("");
    }

    // ------------------------------------------------------------------
    // Rendering
    // ------------------------------------------------------------------
    function scrollDown() {
        els.messages.scrollTop = els.messages.scrollHeight;
    }

    function addMessage(m) {
        els.empty.style.display = "none";
        const node = document.createElement("div");
        node.className = "ca-msg " + m.role + (m.is_error ? " error" : "");
        if (m.role === "assistant") node.innerHTML = renderMarkdown(m.content);
        else node.textContent = m.content;
        // Solo l'ultima risposta dell'assistente resta cliccabile: le card
        // dei passaggi precedenti diventano "scadute".
        if (m.role === "assistant" && !m.is_error) {
            els.messages.querySelectorAll(".ca-msg.assistant:not(.ca-stale)").forEach((n) => n.classList.add("ca-stale"));
        }
        els.messages.appendChild(node);
        scrollDown();
        return node;
    }

    function clearMessages() {
        els.messages.querySelectorAll(".ca-msg, .ca-typing").forEach((n) => n.remove());
        els.empty.style.display = "";
    }

    function setBusy(value) {
        busy = value;
        els.send.disabled = value;
        els.input.disabled = value;
        if (!value) els.input.focus();
    }

    async function loadConversations() {
        const convs = await rpc("/cruise_assistant/conversations");
        els.list.innerHTML = "";
        for (const c of convs) {
            const li = document.createElement("li");
            if (c.id === currentId) li.className = "active";
            const name = document.createElement("button");
            name.type = "button";
            name.className = "ca-conv-name";
            name.textContent = c.name;
            name.title = c.name;
            name.addEventListener("click", () => openConversation(c.id));
            const del = document.createElement("button");
            del.type = "button";
            del.className = "ca-conv-del";
            del.title = "Elimina";
            del.textContent = "✕";
            del.addEventListener("click", async (ev) => {
                ev.stopPropagation();
                if (!confirm("Eliminare questa conversazione?")) return;
                await rpc("/cruise_assistant/delete", { conversation_id: c.id });
                if (c.id === currentId) newConversation();
                loadConversations();
            });
            li.append(name, del);
            els.list.appendChild(li);
        }
    }

    async function openConversation(id) {
        if (busy) return;
        const data = await rpc("/cruise_assistant/messages", { conversation_id: id });
        currentId = id;
        els.title.textContent = data.conversation.name;
        clearMessages();
        data.messages.forEach(addMessage);
        els.sidebar.classList.remove("open");
        history.replaceState(null, "", "/cruise_assistant?c=" + id);
        loadConversations();
    }

    function newConversation() {
        if (busy) return;
        currentId = null;
        els.title.textContent = "Cruise Assistant";
        clearMessages();
        els.sidebar.classList.remove("open");
        history.replaceState(null, "", "/cruise_assistant");
        loadConversations();
        els.input.focus();
    }

    async function sendMessage(text) {
        text = text.trim();
        if (!text || busy) return;
        setBusy(true);
        const userNode = addMessage({ role: "user", content: text });
        els.input.value = "";
        autoResize();
        const typing = document.createElement("div");
        typing.className = "ca-typing";
        typing.innerHTML = "Sto pensando<span>.</span><span>.</span><span>.</span>";
        els.messages.appendChild(typing);
        scrollDown();
        try {
            const res = await rpc("/cruise_assistant/send", { message: text, conversation_id: currentId });
            typing.remove();
            if (res.error) {
                userNode.remove();
                els.input.value = text;
                addMessage({ role: "assistant", content: "Errore: " + res.error, is_error: true });
                return;
            }
            userNode.remove();
            res.messages.forEach(addMessage);
            if (currentId !== res.conversation.id) {
                currentId = res.conversation.id;
                history.replaceState(null, "", "/cruise_assistant?c=" + currentId);
            }
            els.title.textContent = res.conversation.name;
            loadConversations();
        } catch (e) {
            typing.remove();
            userNode.remove();
            els.input.value = text;
            addMessage({ role: "assistant", content: "Errore: " + e.message, is_error: true });
        } finally {
            setBusy(false);
        }
    }

    function autoResize() {
        els.input.style.height = "auto";
        els.input.style.height = Math.min(els.input.scrollHeight, 200) + "px";
    }

    // ------------------------------------------------------------------
    // Eventi
    // ------------------------------------------------------------------
    els.form.addEventListener("submit", (ev) => {
        ev.preventDefault();
        sendMessage(els.input.value);
    });
    els.input.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" && !ev.shiftKey && !ev.isComposing) {
            ev.preventDefault();
            sendMessage(els.input.value);
        }
    });
    els.input.addEventListener("input", autoResize);
    els.toggle.addEventListener("click", () => els.sidebar.classList.toggle("open"));
    // Card interattive: cliccarle equivale a scrivere in chat la scelta.
    els.messages.addEventListener("click", (ev) => {
        const target = ev.target.closest(".ca-pick, .ca-toggle-choice, .ca-choice-confirm, .ca-book");
        if (!target || busy || target.closest(".ca-stale")) return;
        if (target.classList.contains("ca-book")) {
            showThankYou();
        } else if (target.classList.contains("ca-toggle-choice")) {
            target.classList.toggle("selected");
            target.setAttribute("aria-pressed", target.classList.contains("selected"));
        } else if (target.classList.contains("ca-choice-confirm")) {
            const box = target.closest(".ca-choices");
            const picked = [...box.querySelectorAll(".ca-toggle-choice.selected")].map((c) => c.dataset.value);
            sendMessage(picked.length ? picked.join(", ") : box.dataset.none);
        } else {
            target.classList.add("selected");
            sendMessage(target.dataset.value);
        }
    });

    // "Prenota Crociera": messaggio di ringraziamento e ritorno alla home.
    function showThankYou() {
        if (document.querySelector(".ca-thanks")) return;
        const overlay = document.createElement("div");
        overlay.className = "ca-thanks";
        overlay.setAttribute("role", "dialog");
        overlay.innerHTML = '<div class="ca-thanks-box"><div class="ca-thanks-icon">&#9875;</div>'
            + "<h2>Grazie per aver provato questa demo</h2>"
            + "<p>Tra pochi secondi tornerai alla homepage…</p>"
            + '<button type="button">Torna alla homepage</button></div>';
        const goHome = () => { window.location.href = "/cruise_assistant/home"; };
        overlay.querySelector("button").addEventListener("click", goHome);
        document.body.appendChild(overlay);
        setTimeout(goHome, 3500);
    }
    document.querySelectorAll(".ca-suggestion").forEach((b) =>
        b.addEventListener("click", () => sendMessage(b.textContent)));

    const params = new URLSearchParams(location.search);
    const initial = parseInt(params.get("c"), 10);
    // Testo dalla home ("Cosa hai in mente?"), via sessionStorage (home.js) o
    // ?q=...: nuova chat con quel testo come primo messaggio dell'utente.
    // Viene consumato subito (storage svuotato, URL ripulito) così un
    // ricaricamento della pagina non lo reinvia.
    let question = "";
    try {
        question = sessionStorage.getItem("cruise_assistant_pending_message") || "";
        sessionStorage.removeItem("cruise_assistant_pending_message");
    } catch (e) { /* storage non disponibile */ }
    if (!question.trim()) question = params.get("q") || "";
    if (question.trim()) {
        history.replaceState(null, "", "/cruise_assistant");
        loadConversations();
        sendMessage(question);
    } else if (initial) openConversation(initial).catch(() => newConversation());
    else loadConversations();
    els.input.focus();
})();
