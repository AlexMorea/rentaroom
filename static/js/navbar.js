const burger = document.getElementById("burgerBtn");
const nav = document.getElementById("navLinks");
const backdrop = document.getElementById("navBackdrop");

function openMenu() {
  nav?.classList.add("show");
  backdrop?.classList.add("show");
  document.body.classList.add("nav-open");
}

function closeMenu() {
  nav?.classList.remove("show");
  backdrop?.classList.remove("show");
  document.body.classList.remove("nav-open");
}

burger?.addEventListener("click", (e) => {
  e.preventDefault();

  nav?.classList.contains("show") ? closeMenu() : openMenu();
});

backdrop?.addEventListener("click", closeMenu);

nav?.querySelectorAll("a").forEach((link) => {
  link.addEventListener("click", closeMenu);
});
