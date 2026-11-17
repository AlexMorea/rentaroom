// Keeps the unread-message badges in the menus up to date while the
// site is open, and shows a small pop-up when a new message arrives.
// Checks every 30 seconds, and only while the tab is visible, to keep
// data use low.
(function () {
  const url = document.body.dataset.unreadUrl;
  if (!url) return;
  const KEY = "r4y_last_notified_message";
  const POLL_MS = 30000;

  function setBadges(count) {
    document.querySelectorAll("[data-unread-badge]").forEach(function (el) {
      el.textContent = count > 99 ? "99+" : String(count);
      el.hidden = count === 0;
    });
    document.querySelectorAll("[data-unread-dot]").forEach(function (el) {
      el.hidden = count === 0;
    });
  }

  function popup(latest) {
    // Already looking at that conversation: no pop-up needed.
    if (window.location.pathname === latest.url) return;

    let wrap = document.querySelector(".toast-wrap");
    if (!wrap) {
      wrap = document.createElement("div");
      wrap.className = "toast-wrap";
      const main = document.querySelector("main") || document.body;
      main.insertBefore(wrap, main.firstChild);
    }
    const toast = document.createElement("div");
    toast.className = "toast toast-info show";
    toast.setAttribute("role", "status");
    const text = document.createElement("span");
    text.className = "toast-text";
    text.textContent = "New message from " + latest.from + " about “" + latest.room + "”. ";
    const link = document.createElement("a");
    link.href = latest.url;
    link.textContent = "Open";
    text.appendChild(link);
    const close = document.createElement("button");
    close.type = "button";
    close.className = "toast-close";
    close.setAttribute("aria-label", "Dismiss message");
    close.textContent = "×";
    close.addEventListener("click", function () { toast.remove(); });
    toast.appendChild(text);
    toast.appendChild(close);
    wrap.appendChild(toast);
    setTimeout(function () { toast.remove(); }, 12000);
  }

  async function check() {
    if (document.hidden) return;
    try {
      const res = await fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" } });
      if (!res.ok) return;
      const data = await res.json();
      setBadges(data.count || 0);
      if (data.latest) {
        let last = null;
        try { last = sessionStorage.getItem(KEY); } catch (e) {}
        if (last === null) {
          // First check in this visit: remember it without a pop-up, the
          // badge already shows it.
          try { sessionStorage.setItem(KEY, String(data.latest.id)); } catch (e) {}
        } else if (String(data.latest.id) !== last) {
          try { sessionStorage.setItem(KEY, String(data.latest.id)); } catch (e) {}
          popup(data.latest);
        }
      }
    } catch (e) {
      /* offline for a moment */
    }
  }

  check();
  setInterval(check, POLL_MS);
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) check();
  });
})();
