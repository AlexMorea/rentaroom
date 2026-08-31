document.addEventListener("DOMContentLoaded", function () {
  const sidebar = document.getElementById("sidebar");
  const toggle = document.getElementById("sidebarToggle");
  const overlay = document.getElementById("sidebarOverlay");
  const arrow = document.getElementById("sidebarArrow");

  if (!sidebar || !toggle) return;

  function openSidebar() {
    sidebar.classList.add("open");
    overlay?.classList.add("show");
    document.body.classList.add("sidebar-open");

    if (arrow) arrow.textContent = "❮";
  }

  function closeSidebar() {
    sidebar.classList.remove("open");
    overlay?.classList.remove("show");
    document.body.classList.remove("sidebar-open");

    if (arrow) arrow.textContent = "❯";
  }

  toggle.addEventListener("click", function () {
    if (sidebar.classList.contains("open")) {
      closeSidebar();
    } else {
      openSidebar();
    }
  });

  overlay?.addEventListener("click", closeSidebar);

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closeSidebar();
  });

  sidebar.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", closeSidebar);
  });
});
