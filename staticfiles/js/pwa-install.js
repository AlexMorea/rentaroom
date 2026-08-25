(function () {
  var STORAGE_KEY = "r4y-install-dismissed-at";
  var COOLDOWN_DAYS = 14;

  function isStandalone() {
    return (
      window.matchMedia("(display-mode: standalone)").matches ||
      window.navigator.standalone === true
    );
  }

  function isDismissedRecently() {
    var raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return false;
    var elapsedDays = (Date.now() - Number(raw)) / (1000 * 60 * 60 * 24);
    return elapsedDays < COOLDOWN_DAYS;
  }

  if (isStandalone() || isDismissedRecently()) return;

  var deferredPrompt = null;

  window.addEventListener("beforeinstallprompt", function (event) {
    event.preventDefault();
    deferredPrompt = event;

    var banner = document.getElementById("pwaInstallBanner");
    if (banner) banner.hidden = false;
  });

  document.addEventListener("DOMContentLoaded", function () {
    var banner = document.getElementById("pwaInstallBanner");
    var installBtn = document.getElementById("pwaInstallBtn");
    var dismissBtn = document.getElementById("pwaInstallDismiss");

    if (!banner || !installBtn || !dismissBtn) return;

    installBtn.addEventListener("click", function () {
      banner.hidden = true;
      if (!deferredPrompt) return;

      deferredPrompt.prompt();
      deferredPrompt.userChoice.finally(function () {
        deferredPrompt = null;
      });
    });

    dismissBtn.addEventListener("click", function () {
      banner.hidden = true;
      localStorage.setItem(STORAGE_KEY, String(Date.now()));
    });
  });

  window.addEventListener("appinstalled", function () {
    var banner = document.getElementById("pwaInstallBanner");
    if (banner) banner.hidden = true;
    localStorage.setItem(STORAGE_KEY, String(Date.now()));
  });
})();
