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

// Account menu (desktop dropdown). On phones it's shown inside the drawer.
const accountBtn = document.getElementById("accountToggle");
const accountMenu = document.getElementById("accountMenu");

function setAccountMenu(open) {
  accountMenu?.classList.toggle("open", open);
  accountBtn?.setAttribute("aria-expanded", open ? "true" : "false");
}

accountBtn?.addEventListener("click", (e) => {
  e.stopPropagation();
  setAccountMenu(!accountMenu.classList.contains("open"));
});

document.addEventListener("click", (e) => {
  if (accountMenu?.classList.contains("open") && !accountMenu.contains(e.target)) setAccountMenu(false);
});

document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  if (accountMenu?.classList.contains("open")) {
    setAccountMenu(false);
    accountBtn?.focus();
  }
  if (nav?.classList.contains("show")) closeMenu();
});

// Phones: the avatar next to the menu button opens the same menu.
document.querySelectorAll("[data-open-menu]").forEach((btn) => {
  btn.addEventListener("click", (e) => {
    e.preventDefault();
    nav?.classList.contains("show") ? closeMenu() : openMenu();
  });
});
