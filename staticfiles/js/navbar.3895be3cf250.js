const burger = document.getElementById("burgerBtn");
const nav = document.getElementById("navLinks");
const backdrop = document.getElementById("navBackdrop");

function openMenu() {
  nav?.classList.add("show");
  backdrop?.classList.add("show");
  document.body.classList.add("nav-open");
  burger?.classList.add("active");
  burger?.setAttribute("aria-expanded", "true");
  burger?.setAttribute("aria-label", "Close menu");
}

function closeMenu() {
  nav?.classList.remove("show");
  backdrop?.classList.remove("show");
  document.body.classList.remove("nav-open");
  burger?.classList.remove("active");
  burger?.setAttribute("aria-expanded", "false");
  burger?.setAttribute("aria-label", "Open menu");
}

burger?.addEventListener("click", (e) => {
  e.preventDefault();

  nav?.classList.contains("show") ? closeMenu() : openMenu();
});

backdrop?.addEventListener("click", closeMenu);

nav?.querySelectorAll("a").forEach((link) => {
  link.addEventListener("click", closeMenu);
});
