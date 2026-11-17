// Conversation page: send without reloading, show new replies as they
// arrive, "Seen" on your last message, quick replies and a text box that
// grows as you type. Everything still works as a plain form if this
// script doesn't load.
(function () {
  const root = document.querySelector("[data-conversation]");
  if (!root) return;

  const thread = document.getElementById("convThread");
  const form = document.getElementById("convComposer");
  const textarea = document.getElementById("convTextarea");
  const seen = root.querySelector("[data-conv-seen]");
  const errorEl = root.querySelector("[data-conv-error]");
  const pollUrl = root.dataset.pollUrl;
  const sendUrl = root.dataset.sendUrl;
  const otherInitial = root.dataset.otherInitial || "";
  const POLL_MS = 6000;

  function csrf() {
    const input = form && form.querySelector("input[name=csrfmiddlewaretoken]");
    return input ? input.value : "";
  }

  function lastId() {
    const rows = thread.querySelectorAll("[data-msg-id]");
    return rows.length ? parseInt(rows[rows.length - 1].dataset.msgId, 10) : 0;
  }

  function lastDay() {
    const days = thread.querySelectorAll("[data-day]");
    return days.length ? days[days.length - 1].dataset.day : "";
  }

  function nearBottom() {
    return thread.scrollHeight - thread.scrollTop - thread.clientHeight < 120;
  }

  function scrollToEnd() {
    thread.scrollTop = thread.scrollHeight;
  }

  function addMessage(m) {
    if (thread.querySelector('[data-msg-id="' + m.id + '"]')) return;
    const empty = thread.querySelector("[data-conv-empty]");
    if (empty) empty.remove();

    if (m.day !== lastDay()) {
      const day = document.createElement("div");
      day.className = "conv-day";
      day.dataset.day = m.day;
      day.textContent = m.day_label;
      thread.insertBefore(day, seen);
    }

    const row = document.createElement("div");
    row.className = "bubble-row " + (m.mine ? "bubble-row-out" : "bubble-row-in");
    row.dataset.msgId = m.id;

    if (!m.mine) {
      const avatar = document.createElement("div");
      avatar.className = "bubble-avatar";
      avatar.textContent = otherInitial;
      row.appendChild(avatar);
    }

    const bubble = document.createElement("div");
    bubble.className = "bubble " + (m.mine ? "bubble-out" : "bubble-in");
    const text = document.createElement("p");
    text.className = "bubble-text";
    text.textContent = m.body;
    const time = document.createElement("small");
    time.className = "bubble-time" + (m.mine ? " bubble-time-out" : " text-muted");
    time.textContent = m.time;
    bubble.appendChild(text);
    bubble.appendChild(time);
    row.appendChild(bubble);

    thread.insertBefore(row, seen);
  }

  function setSeen(lastMineId, read) {
    if (!seen) return;
    // Only show "Seen" when my message is the newest one in the thread.
    const rows = thread.querySelectorAll("[data-msg-id]");
    const newest = rows.length ? rows[rows.length - 1] : null;
    const newestIsMine = newest && newest.classList.contains("bubble-row-out");
    seen.hidden = !(read && newestIsMine && newest && parseInt(newest.dataset.msgId, 10) === lastMineId);
  }

  async function poll() {
    if (document.hidden) return;
    try {
      const res = await fetch(pollUrl + "?after=" + lastId(), { headers: { "X-Requested-With": "XMLHttpRequest" } });
      if (!res.ok) return;
      const data = await res.json();
      const stick = nearBottom();
      (data.messages || []).forEach(addMessage);
      setSeen(data.last_mine_id, data.last_mine_read);
      if (stick && data.messages && data.messages.length) scrollToEnd();
    } catch (e) {
      /* offline for a moment - try again next tick */
    }
  }

  function grow() {
    if (!textarea) return;
    textarea.style.height = "46px";
    textarea.style.height = Math.min(Math.max(textarea.scrollHeight, 46), 160) + "px";
  }

  function showError(text) {
    if (!errorEl) return;
    errorEl.textContent = text || "";
    errorEl.hidden = !text;
  }

  async function send(e) {
    if (e) e.preventDefault();
    const body = textarea.value.trim();
    if (!body) return;

    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    showError("");

    const data = new FormData();
    data.append("body", body);
    data.append("csrfmiddlewaretoken", csrf());

    try {
      const res = await fetch(sendUrl, {
        method: "POST",
        body: data,
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      const json = await res.json().catch(() => ({}));
      if (res.ok && json.ok) {
        addMessage(json.message);
        setSeen(json.message.id, false);
        textarea.value = "";
        grow();
        scrollToEnd();
      } else {
        showError(json.error || "Your message couldn't be sent. Please try again.");
      }
    } catch (err) {
      showError("You seem to be offline. Your message hasn't been sent yet.");
    } finally {
      button.disabled = false;
      textarea.focus();
    }
  }

  scrollToEnd();
  grow();

  if (form && textarea) {
    form.addEventListener("submit", send);
    textarea.addEventListener("input", grow);
    textarea.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) send(e);
    });
    root.querySelectorAll("[data-quick-reply]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        textarea.value = btn.textContent.trim();
        grow();
        textarea.focus();
      });
    });
  }

  setInterval(poll, POLL_MS);
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) poll();
  });
})();
