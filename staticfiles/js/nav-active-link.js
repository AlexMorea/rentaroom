document.addEventListener("DOMContentLoaded", () => {
  const path = window.location.pathname;

  function markActive(selector) {
    document.querySelectorAll(selector).forEach((link) => {
      let linkPath;
      try {
        linkPath = new URL(link.href).pathname;
      } catch (e) {
        return;
      }

      // "/" only matches the homepage itself - otherwise it would light
      // up on every page. Every other link matches its own page and any
      // page nested under it (e.g. "/rooms/" also covers "/rooms/42/").
      const isActive =
        path === linkPath || (linkPath !== "/" && path.startsWith(linkPath));

      if (isActive) link.classList.add("active");
    });
  }

  markActive(".nav-links a[href]");
  markActive(".sidebar a[href]");
});
