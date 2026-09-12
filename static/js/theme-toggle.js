document.addEventListener("DOMContentLoaded", () => {
  const btn = document.getElementById("themeToggle");
  if (!btn) return;

  const root = document.documentElement;
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)");

  function isDark() {
    const explicit = root.getAttribute("data-theme");
    if (explicit) return explicit === "dark";
    return prefersDark.matches;
  }

  function sync() {
    const dark = isDark();
    btn.setAttribute("aria-label", dark ? "Switch to light mode" : "Switch to dark mode");
    btn.classList.toggle("is-dark", dark);
  }

  btn.addEventListener("click", () => {
    const next = isDark() ? "light" : "dark";
    root.setAttribute("data-theme", next);
    localStorage.setItem("r4y-theme", next);
    sync();
  });

  // Follows the OS toggle live, but only while the visitor hasn't made
  // an explicit choice on this site (localStorage empty).
  prefersDark.addEventListener("change", () => {
    if (!localStorage.getItem("r4y-theme")) sync();
  });

  sync();
});
