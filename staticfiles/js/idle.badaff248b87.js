if (document.body.dataset.auth === "1") {
  const IDLE = 15 * 60 * 1000;
  const WARN = 60;

  const modal = document.getElementById("idleModal");
  const countdown = document.getElementById("idleCountdown");

  let idleTimer;
  let countTimer;
  let remaining = WARN;

  function openModal() {
    modal?.classList.add("show");

    countTimer = setInterval(() => {
      remaining--;

      if (countdown) {
        countdown.textContent = remaining;
      }

      if (remaining <= 0) {
        document.getElementById("logout-form")?.submit();
      }
    }, 1000);
  }

  function reset() {
    clearTimeout(idleTimer);
    clearInterval(countTimer);

    remaining = WARN;

    modal?.classList.remove("show");

    idleTimer = setTimeout(openModal, IDLE);
  }

  ["mousemove", "mousedown", "keydown", "scroll", "touchstart"].forEach((e) => {
    window.addEventListener(e, reset, { passive: true });
  });

  document.getElementById("stayLoggedInBtn")?.addEventListener("click", reset);

  reset();
}
