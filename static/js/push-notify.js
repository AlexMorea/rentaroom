// Web Push opt-in banner: shown once (per-browser) to a logged-in user
// whose browser supports push and who hasn't already subscribed or
// dismissed it. Mirrors pwa-install.js's "reveal only when genuinely
// actionable" approach rather than nagging on every load.
(function () {
  const DISMISS_KEY = "r4y_push_dismissed";

  function getCookie(name) {
    const match = document.cookie.match(new RegExp("(^| )" + name + "=([^;]+)"));
    return match ? decodeURIComponent(match[2]) : null;
  }

  function urlBase64ToUint8Array(base64String) {
    const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
    const rawData = atob(base64);
    return Uint8Array.from([...rawData].map((c) => c.charCodeAt(0)));
  }

  async function postJSON(url, body) {
    return fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCookie("csrftoken") || "",
      },
      body: JSON.stringify(body),
    });
  }

  async function isAlreadySubscribed(registration) {
    const existing = await registration.pushManager.getSubscription();
    return !!existing;
  }

  async function subscribe(registration) {
    if (!window.VAPID_PUBLIC_KEY) return null;

    return registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(window.VAPID_PUBLIC_KEY),
    });
  }

  document.addEventListener("DOMContentLoaded", async function () {
    const isAuthed = document.body.dataset.auth === "1";
    const banner = document.getElementById("pushNotifyBanner");
    const enableBtn = document.getElementById("pushNotifyBtn");
    const dismissBtn = document.getElementById("pushNotifyDismiss");

    if (!isAuthed || !banner) return;
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) return;
    if (Notification.permission === "denied") return;
    if (localStorage.getItem(DISMISS_KEY) === "1") return;

    try {
      const registration = await navigator.serviceWorker.ready;
      if (await isAlreadySubscribed(registration)) return;

      banner.hidden = false;

      enableBtn.addEventListener("click", async function () {
        try {
          const permission = await Notification.requestPermission();
          if (permission !== "granted") {
            banner.hidden = true;
            return;
          }

          const subscription = await subscribe(registration);
          if (!subscription) {
            banner.hidden = true;
            return;
          }

          await postJSON("/accounts/push/subscribe/", subscription.toJSON());
        } catch (e) {
          // Silent on purpose, same policy as service worker registration -
          // push is a nice-to-have, never a blocking error for the user.
        } finally {
          banner.hidden = true;
        }
      });

      dismissBtn.addEventListener("click", function () {
        localStorage.setItem(DISMISS_KEY, "1");
        banner.hidden = true;
      });
    } catch (e) {
      // Service worker never became ready - nothing to offer.
    }
  });
})();
