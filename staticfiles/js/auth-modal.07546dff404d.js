document.addEventListener("DOMContentLoaded", () => {
  const authBtn = document.getElementById("authToggle");
  const modal = document.getElementById("authModal");

  authBtn?.addEventListener("click", () => {
    modal?.classList.remove("hidden");
  });

  modal?.addEventListener("click", (e) => {
    if (e.target === modal) {
      modal.classList.add("hidden");
    }
  });

  document.querySelectorAll(".auth-option").forEach((btn) => {
    btn.addEventListener("click", () => {
      const url = btn.dataset.url;

      if (url) {
        window.location.href = url;
      }
    });
  });
});
