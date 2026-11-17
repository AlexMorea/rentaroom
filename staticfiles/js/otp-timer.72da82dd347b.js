// Live countdowns on the verify pages (sign-up code and new-device code).
//
// The page renders two numbers from the server: seconds until the code
// expires and seconds until another code can be sent. Counting down
// from those, rather than from the phone's clock, keeps the timers right
// even when a phone's time is wrong.
(function () {
  const root = document.querySelector("[data-otp-timer]");
  if (!root) return;

  const resendUrl = root.dataset.resendUrl;
  const expiryEl = root.querySelector("[data-otp-expiry]");
  const btn = root.querySelector("[data-otp-resend]");
  const btnText = root.querySelector("[data-otp-resend-text]");
  const msg = root.querySelector("[data-otp-message]");
  const resendLabel = btnText ? btnText.textContent.trim() : "Send a new code";

  let expiresAt = Date.now() + (parseInt(root.dataset.expiresIn, 10) || 0) * 1000;
  let resendAt = Date.now() + (parseInt(root.dataset.resendIn, 10) || 0) * 1000;

  function mmss(totalSeconds) {
    const m = Math.floor(totalSeconds / 60);
    const s = totalSeconds % 60;
    return m + ":" + String(s).padStart(2, "0");
  }

  function setMessage(text, level) {
    if (!msg) return;
    msg.textContent = text || "";
    msg.dataset.level = level || "";
  }

  function tick() {
    const now = Date.now();

    if (expiryEl) {
      const left = Math.max(0, Math.ceil((expiresAt - now) / 1000));
      if (left > 0) {
        expiryEl.textContent = "Your code expires in " + mmss(left);
        expiryEl.dataset.state = left <= 60 ? "soon" : "ok";
      } else {
        expiryEl.textContent = "This code has expired. Please ask for a new one below.";
        expiryEl.dataset.state = "expired";
      }
    }

    if (btn && !btn.dataset.busy) {
      const wait = Math.max(0, Math.ceil((resendAt - now) / 1000));
      btn.disabled = wait > 0;
      if (btnText) btnText.textContent = wait > 0 ? "Send a new code in " + mmss(wait) : resendLabel;
    }
  }

  async function resend() {
    if (!btn || btn.disabled) return;
    btn.dataset.busy = "1";
    btn.disabled = true;
    if (btnText) btnText.textContent = "Sending...";
    setMessage("");

    try {
      const res = await fetch(resendUrl, { headers: { "X-Requested-With": "XMLHttpRequest" } });
      const data = await res.json().catch(() => ({}));
      if (data.cooldown) resendAt = Date.now() + data.cooldown * 1000;

      if (res.ok) {
        if (data.expires_in) expiresAt = Date.now() + data.expires_in * 1000;
        setMessage(data.message || "We've sent you a new code.", "success");
      } else {
        setMessage(data.message || "We couldn't send a new code just now. Please try again in a moment.",
                   res.status === 429 ? "warning" : "error");
      }
    } catch (e) {
      setMessage("We couldn't reach the server. Check your connection and try again.", "error");
    } finally {
      delete btn.dataset.busy;
      tick();
    }
  }

  if (btn) btn.addEventListener("click", resend);
  tick();
  setInterval(tick, 1000);
})();
