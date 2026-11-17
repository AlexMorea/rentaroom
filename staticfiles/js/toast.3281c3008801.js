// Flash messages: long enough to actually read.
// - Success/info stay at least 7s, longer for longer messages
//   (~ reading speed), and pause while hovered/touched.
// - Warnings/errors stay until the person closes them - they usually
//   say something the person needs to act on.
document.addEventListener("DOMContentLoaded", function () {
  const MIN_MS = 7000;
  const MS_PER_WORD = 400;

  document.querySelectorAll(".toast").forEach((toast) => {
    toast.classList.add("show");

    const dismiss = () => {
      toast.classList.remove("show");
      setTimeout(() => toast.remove(), 250);
    };

    const closeBtn = toast.querySelector(".toast-close");
    if (closeBtn) closeBtn.addEventListener("click", dismiss);

    const sticky =
      toast.classList.contains("toast-error") ||
      toast.classList.contains("toast-danger") ||
      toast.classList.contains("toast-warning");
    if (sticky) return;

    const words = (toast.textContent || "").trim().split(/\s+/).length;
    const total = Math.max(MIN_MS, words * MS_PER_WORD);
    let remaining = total;
    let started = Date.now();
    let timer = setTimeout(dismiss, remaining);

    const pause = () => {
      clearTimeout(timer);
      remaining -= Date.now() - started;
    };
    const resume = () => {
      started = Date.now();
      clearTimeout(timer);
      timer = setTimeout(dismiss, Math.max(remaining, 2000));
    };

    toast.addEventListener("mouseenter", pause);
    toast.addEventListener("mouseleave", resume);
    toast.addEventListener("touchstart", pause, { passive: true });
    toast.addEventListener("touchend", resume);
  });
});
