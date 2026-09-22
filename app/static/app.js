// Chat client for the Caravista bot. Talks to POST /api/chat and echoes the
// session_id the backend hands back on every subsequent request.
//
// The interaction copies WhatsApp's, because that is where this bot is headed
// (app/whatsapp.py): Enter sends, Shift+Enter breaks the line, an outgoing
// message appears immediately with a single tick, the header switches to
// "escrivint…" while the backend works, and the ticks turn blue when the reply
// lands. None of that changes the request contract.
(function () {
  "use strict";

  var form = document.getElementById("chat-form");
  var input = document.getElementById("message");
  var sendBtn = document.getElementById("send");
  var messages = document.getElementById("messages");
  var presence = document.getElementById("presence");

  // The backend appends the disclaimer after a final separator.
  var SEPARATOR = "\n\n---\n";
  var PRESENCE_ONLINE = "en línia";
  var PRESENCE_TYPING = "escrivint…";

  var sessionId = null;
  try {
    sessionId = window.sessionStorage.getItem("caravista.session_id");
  } catch (err) {
    // Private mode / blocked storage: a fresh session per load is acceptable.
    sessionId = null;
  }

  function rememberSession(id) {
    sessionId = id;
    try {
      window.sessionStorage.setItem("caravista.session_id", id);
    } catch (err) {
      /* not worth surfacing */
    }
  }

  function now() {
    var d = new Date();
    return String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
  }

  function escapeHtml(text) {
    return text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // WhatsApp's own inline markup, which app/whatsapp.py already emits for the
  // phone channel: *bold*, _italic_, ~strikethrough~. Escaped first, so the
  // markup is the only HTML that can ever reach the DOM.
  function formatMarkup(text) {
    return linkify(
      escapeHtml(text)
        .replace(/(^|\s)\*(\S([^*]*\S)?)\*(?=\s|$|[.,!?;:])/g, "$1<strong>$2</strong>")
        .replace(/(^|\s)_(\S([^_]*\S)?)_(?=\s|$|[.,!?;:])/g, "$1<em>$2</em>")
        .replace(/(^|\s)~(\S([^~]*\S)?)~(?=\s|$|[.,!?;:])/g, "$1<s>$2</s>")
    );
  }

  // One alternation so each stretch of text is claimed by at most one link.
  // Runs on escaped text: "&" only appears as "&amp;" (valid in an href, the
  // browser decodes it), and "<"/">" only occur in the tags formatMarkup just
  // inserted, so excluding them stops a URL at </strong> and friends.
  var LINK_PATTERN =
    /https?:\/\/(?:[^\s<>&]|&amp;)+|www\.(?:[^\s<>&]|&amp;)+|[\w.+-]+@[\w-]+(?:\.[\w-]+)+|\+?\d[\d ().-]{6,}\d/g;

  function linkify(html) {
    return html.replace(LINK_PATTERN, function (match, offset) {
      // Sentence punctuation after a URL/email belongs to the sentence, and a
      // closing paren only to the URL if the URL itself opened one.
      var trail = "";
      var m = match.match(/[.,!?;:]+$/);
      if (m) {
        trail = m[0];
        match = match.slice(0, -trail.length);
      }
      if (match.slice(-1) === ")" && match.indexOf("(") === -1) {
        trail = ")" + trail;
        match = match.slice(0, -1);
      }

      var href;
      var external = false;
      if (/^https?:\/\//.test(match)) {
        href = match;
        external = true;
      } else if (match.slice(0, 4) === "www.") {
        href = "https://" + match;
        external = true;
      } else if (match.indexOf("@") !== -1) {
        href = "mailto:" + match;
      } else {
        // Phone candidate: anything digit-shaped matched; only link it when it
        // plausibly is one: 9 digits (Spanish, no prefix) up to 15 (E.164 max),
        // not glued to a preceding letter/digit (IBANs, reference ids), and no
        // standalone 4-digit group — years, dates and IBAN chunks have those,
        // Spanish numbers group as 3-3-3 or 2-3-2-2.
        var digits = match.replace(/\D/g, "");
        if (
          digits.length < 9 ||
          digits.length > 15 ||
          /\w/.test(html.charAt(offset - 1)) ||
          /(^|\D)\d{4}(\D|$)/.test(match)
        ) {
          return match + trail;
        }
        href = "tel:" + (match.charAt(0) === "+" ? "+" : "") + digits;
      }

      var attrs = external ? ' target="_blank" rel="noopener noreferrer"' : "";
      return '<a href="' + href + '"' + attrs + ">" + match + "</a>" + trail;
    });
  }

  function isLastRow(kind) {
    var last = messages.lastElementChild;
    return !!last && last.classList.contains("row--" + kind);
  }

  function scrollToBottom() {
    var canvas = messages.parentElement;
    canvas.scrollTop = canvas.scrollHeight;
  }

  /** Append a row and return its bubble element. */
  function addRow(kind, options) {
    var tail = !isLastRow(kind);
    var row = document.createElement("li");
    row.className = "row row--" + kind;

    var bubble = document.createElement("div");
    bubble.className = "bubble bubble--" + kind + (tail ? " bubble--tail" : "");
    row.appendChild(bubble);

    var text = document.createElement("span");
    text.className = "bubble__text";
    bubble.appendChild(text);

    if (options && options.withMeta) {
      var meta = document.createElement("span");
      meta.className = "bubble__meta";
      var time = document.createElement("time");
      time.textContent = now();
      meta.appendChild(time);
      if (kind === "out") {
        var ticks = document.createElement("span");
        ticks.className = "bubble__ticks";
        meta.appendChild(ticks);
      }
      bubble.appendChild(meta);
    }

    messages.appendChild(row);
    scrollToBottom();
    return bubble;
  }

  var TICK_SINGLE =
    '<svg viewBox="0 0 16 11" width="16" height="11" aria-hidden="true">' +
    '<path fill="currentColor" d="M11.07.65 5.3 8.2 2.8 5.66l-.9.9 3.5 3.55L12.1 1.4z"/></svg>';
  var TICK_DOUBLE =
    '<svg viewBox="0 0 16 11" width="16" height="11" aria-hidden="true">' +
    '<path fill="currentColor" d="M11.07.65 5.3 8.2 2.8 5.66l-.9.9 3.5 3.55L12.1 1.4z"/>' +
    '<path fill="currentColor" d="M15.3.65 9.53 8.2l-.96-.98-.83.9 1.8 1.99L16.3 1.4z"/></svg>';

  function setTicks(bubble, state) {
    var ticks = bubble.querySelector(".bubble__ticks");
    if (!ticks) return;
    ticks.innerHTML = state === "sent" ? TICK_SINGLE : TICK_DOUBLE;
    ticks.classList.toggle("bubble__ticks--read", state === "read");
    ticks.setAttribute(
      "aria-label",
      state === "sent" ? "Enviat" : state === "delivered" ? "Entregat" : "Llegit"
    );
  }

  /** Render the bot's answer, splitting the trailing disclaimer into a caption. */
  function renderAnswer(bubble, answer) {
    var at = answer.lastIndexOf(SEPARATOR);
    var body = at === -1 ? answer : answer.slice(0, at);
    var note = at === -1 ? "" : answer.slice(at + SEPARATOR.length).trim();

    var text = bubble.querySelector(".bubble__text");
    text.innerHTML = formatMarkup(body.trim());

    if (note) {
      var caption = document.createElement("small");
      caption.className = "bubble__disclaimer";
      caption.textContent = note;
      text.insertAdjacentElement("afterend", caption);
    }

    var meta = document.createElement("span");
    meta.className = "bubble__meta";
    var time = document.createElement("time");
    time.textContent = now();
    meta.appendChild(time);
    bubble.appendChild(meta);
    scrollToBottom();
  }

  function addTypingBubble() {
    var bubble = addRow("in", { withMeta: false });
    var text = bubble.querySelector(".bubble__text");
    text.remove();
    var typing = document.createElement("div");
    typing.className = "typing";
    typing.setAttribute("aria-label", "Caravista està escrivint");
    typing.innerHTML = "<span></span><span></span><span></span>";
    bubble.appendChild(typing);
    scrollToBottom();
    return bubble;
  }

  function addErrorRow(message) {
    var bubble = addRow("error", { withMeta: false });
    bubble.querySelector(".bubble__text").textContent = message;
  }

  function autoGrow() {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 100) + "px";
  }

  async function send(message) {
    var payload = { message: message };
    if (sessionId) payload.session_id = sessionId;

    var resp = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    var data = await resp.json().catch(function () {
      return {};
    });

    if (!resp.ok) {
      if (resp.status === 429) {
        throw new Error("Has enviat massa missatges seguits. Prova-ho d'aquí una estona.");
      }
      throw new Error(data.error || "Error " + resp.status);
    }
    if (data.session_id) rememberSession(data.session_id);
    return data.response;
  }

  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    var message = input.value.trim();
    if (!message) return;

    var outgoing = addRow("out", { withMeta: true });
    outgoing.querySelector(".bubble__text").textContent = message;
    setTicks(outgoing, "sent");

    input.value = "";
    autoGrow();
    input.disabled = true;
    sendBtn.disabled = true;
    presence.textContent = PRESENCE_TYPING;

    var typing = addTypingBubble();

    try {
      var response = await send(message);
      setTicks(outgoing, "read");
      typing.querySelector(".typing").remove();
      var text = document.createElement("span");
      text.className = "bubble__text";
      typing.appendChild(text);
      renderAnswer(typing, response);
    } catch (err) {
      setTicks(outgoing, "delivered");
      typing.parentElement.remove();
      addErrorRow(err.message || "No s'ha pogut enviar el missatge.");
    } finally {
      presence.textContent = PRESENCE_ONLINE;
      input.disabled = false;
      sendBtn.disabled = false;
      input.focus();
    }
  });

  // Enter sends, Shift+Enter (and mobile keyboards' newline) breaks the line.
  input.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      form.requestSubmit();
    }
  });

  input.addEventListener("input", autoGrow);

  // The greeting bubble ships in the HTML with a placeholder time, so the page
  // is meaningful before JS runs; stamp it with the real local time here.
  var firstTime = messages.querySelector(".bubble--in time");
  if (firstTime) firstTime.textContent = now();
  var firstBubble = messages.querySelector(".bubble--in");
  if (firstBubble) firstBubble.classList.add("bubble--tail");
  scrollToBottom();
})();
