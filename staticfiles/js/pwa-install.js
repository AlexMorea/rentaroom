(function () {
  var INSTALLED_KEY = "r4y-installed";
  var DISMISSED_KEY = "r4y-install-dismissed-at";
  var COOLDOWN_DAYS = 14;

  function isStandalone() {
    return (
      window.matchMedia("(display-mode: standalone)").matches ||
      window.navigator.standalone === true
    );
  }

  function isInstalled() {
    return localStorage.getItem(INSTALLED_KEY) === "1";
  }

  function isDismissedRecently() {
    var raw = localStorage.getItem(DISMISSED_KEY);
    if (!raw) return false;
    var elapsedDays = (Date.now() - Number(raw)) / (1000 * 60 * 60 * 24);
    return elapsedDays < COOLDOWN_DAYS;
  }

  function markInstalled() {
    localStorage.setItem(INSTALLED_KEY, "1");
  }

  // isStandalone() only ever tells us about *this* window - installing
  // opens a separate standalone window, so the original browser tab
  // that triggered the install stays in "browser" display-mode forever.
  // markInstalled() is what actually stops the banner coming back there.
  if (isStandalone() || isInstalled() || isDismissedRecently()) return;

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

      var promptEvent = deferredPrompt;
      deferredPrompt = null;

      promptEvent.prompt();
      promptEvent.userChoice.then(function (choice) {
        // Whatever the user decides here, they've made the decision -
        // don't ask again this session. Only an explicit "accepted"
        // permanently stops the banner; a decline just gets the normal
        // cooldown so we're not permanently silent on a "not now".
        if (choice.outcome === "accepted") {
          markInstalled();
        } else {
          localStorage.setItem(DISMISSED_KEY, String(Date.now()));
        }
      });
    });

    dismissBtn.addEventListener("click", function () {
      banner.hidden = true;
      localStorage.setItem(DISMISSED_KEY, String(Date.now()));
    });
  });

  // Belt-and-braces: appinstalled is known to fire unreliably across
  // browsers, but when it does fire, treat it as authoritative -
  // covers installs triggered via the browser's own UI rather than
  // this banner's button.
  window.addEventListener("appinstalled", function () {
    var banner = document.getElementById("pwaInstallBanner");
    if (banner) banner.hidden = true;
    markInstalled();
  });
})();
