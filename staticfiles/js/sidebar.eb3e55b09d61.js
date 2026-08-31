const sidebar = document.querySelector(".sidebar");
const tab = document.querySelector(".sidebar-tab");
const overlay = document.querySelector(".sidebar-overlay");

function toggleSidebar() {
  sidebar?.classList.toggle("open");
  overlay?.classList.toggle("show");
}

tab?.addEventListener("click", toggleSidebar);
overlay?.addEventListener("click", toggleSidebar);
