(function () {
    "use strict";

    // Chiave condivisa con chat.js: testo da inviare come primo messaggio.
    const PENDING_KEY = "cruise_assistant_pending_message";

    const form = document.getElementById("hp-ask-form");
    const input = document.getElementById("hp-ask-input");
    if (!form || !input) return;

    function autoResize() {
        input.style.height = "auto";
        input.style.height = Math.min(input.scrollHeight, 220) + "px";
    }

    function submit() {
        const text = input.value;
        if (!text.trim()) {
            input.focus();
            return;
        }
        // Il testo passa via sessionStorage, così arriva intero (a capo
        // compresi) anche se è lungo. Senza storage si ripiega sull'URL ?q=.
        try {
            sessionStorage.setItem(PENDING_KEY, text);
            window.location.href = "/cruise_assistant";
        } catch (e) {
            window.location.href = "/cruise_assistant?q=" + encodeURIComponent(text);
        }
    }

    form.addEventListener("submit", (ev) => {
        ev.preventDefault();
        submit();
    });
    input.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" && !ev.shiftKey && !ev.isComposing) {
            ev.preventDefault();
            submit();
        }
    });
    input.addEventListener("input", autoResize);
})();
