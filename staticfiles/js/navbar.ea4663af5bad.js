// Header panels. Only one is open at a time:
//   - the main menu (phones: the menu button),
//   - the account card (phones: the avatar; desktop: the name button),
//   - the Safety & Services panel (the "Safety" tab on the left edge).
const burger = document.getElementById("burgerBtn");
const nav = document.getElementById("navLinks");
const backdrop = document.getElementById("navBackdrop");

const accountBtn = document.getElementById("accountToggle");
const accountMenu = document.getElementById("accountMenu");
const sheetBtn = document.getElementById("accountSheetToggle");
const sheet = document.getElementById("accountSheet");
const safetyBtn = document.getElementById("safetyToggle");
const safety = document.getElementById("safetyPanel");

function showBackdrop(on) {
  backdrop?.classList.toggle("show", on);
  document.body.classList.toggle("nav-open", on);
}

function openMenu() {
  closeAll();
  nav?.classList.add("show");
  showBackdrop(true);
  burger?.classList.add("active");
  burger?.setAttribute("aria-expanded", "true");
  burger?.setAttribute("aria-label", "Close menu");
}

function closeMenu() {
  nav?.classList.remove("show");
  burger?.classList.remove("active");
  burger?.setAttribute("aria-expanded", "false");
  burger?.setAttribute("aria-label", "Open menu");
}

function setSheet(open) {
  if (open) closeAll();
  sheet?.classList.toggle("open", open);
  sheetBtn?.setAttribute("aria-expanded", open ? "true" : "false");
  if (open) showBackdrop(true);
}

function setSafety(open) {
  if (open) closeAll();
  safety?.classList.toggle("open", open);
  safetyBtn?.setAttribute("aria-expanded", open ? "true" : "false");
  if (open) {
    showBackdrop(true);
    safety?.querySelector("[data-safety-close]")?.focus();
  }
}

function setAccountMenu(open) {
  accountMenu?.classList.toggle("open", open);
  accountBtn?.setAttribute("aria-expanded", open ? "true" : "false");
}

function closeAll() {
  closeMenu();
  setAccountMenu(false);
  sheet?.classList.remove("open");
  sheetBtn?.setAttribute("aria-expanded", "false");
  safety?.classList.remove("open");
  safetyBtn?.setAttribute("aria-expanded", "false");
  showBackdrop(false);
}

burger?.addEventListener("click", (e) => {
  e.preventDefault();
  nav?.classList.contains("show") ? closeAll() : openMenu();
});

sheetBtn?.addEventListener("click", (e) => {
  e.preventDefault();
  e.stopPropagation();
  setSheet(!sheet.classList.contains("open"));
});

safetyBtn?.addEventListener("click", (e) => {
  e.preventDefault();
  setSafety(!safety.classList.contains("open"));
});

safety?.querySelectorAll("[data-safety-close]").forEach((btn) =>
  btn.addEventListener("click", () => {
    closeAll();
    safetyBtn?.focus();
  })
);

backdrop?.addEventListener("click", closeAll);

[nav, sheet, safety].forEach((panel) =>
  panel?.querySelectorAll("a").forEach((link) => link.addEventListener("click", closeAll))
);

// Desktop account dropdown.
accountBtn?.addEventListener("click", (e) => {
  e.stopPropagation();
  setAccountMenu(!accountMenu.classList.contains("open"));
});

document.addEventListener("click", (e) => {
  if (accountMenu?.classList.contains("open") && !accountMenu.contains(e.target)) setAccountMenu(false);
  if (sheet?.classList.contains("open") && !sheet.contains(e.target) && e.target !== sheetBtn) closeAll();
});

document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  if (accountMenu?.classList.contains("open")) accountBtn?.focus();
  closeAll();
});
