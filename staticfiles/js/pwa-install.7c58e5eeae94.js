(function () {
  var INSTALLED_KEY = "r4y-installed";
  var DISMISSED_KEY = "r4y-install-dismissed-at";
  var DISMISS_COUNT_KEY = "r4y-install-dismiss-count";
  var NEVER_KEY = "r4y-install-never";

  // Escalating cooldown per dismissal - a single "not now" shouldn't
  // cost as much patience as someone who's already said no twice.
  // Index 0 = cooldown after the 1st dismissal, index 1 = after the
  // 2nd. One dismissal beyond the last entry (MAX_DISMISSALS) stops
  // asking altogether instead of cycling back to a short cooldown.
  var COOLDOWN_DAYS_BY_DISMISSAL = [7, 30];
  var MAX_DISMISSALS = COOLDOWN_DAYS_BY_DISMISSAL.length + 1;

  // Don't interrupt the instant a page loads, even on a device that's
  // otherwise eligible - give a first-time visitor a few seconds to
  // actually look at the page before asking them to install anything.
  var SHOW_DELAY_MS = 6000;

  function isStandalone() {
    return (
      window.matchMedia("(display-mode: standalone)").matches ||
      window.navigator.standalone === true
    );
  }

  function isInstalled() {
    return localStorage.getItem(INSTALLED_KEY) === "1";
  }

  function hasOptedOutPermanently() {
    return localStorage.getItem(NEVER_KEY) === "1";
  }

  function getDismissCount() {
    return Number(localStorage.getItem(DISMISS_COUNT_KEY) || 0);
  }

  function isDismissedRecently() {
    var raw = localStorage.getItem(DISMISSED_KEY);
    if (!raw) return false;

    // dismissCount is at least 1 by the time this is ever checked
    // (isDismissedRecently only matters after a dismissal happened).
    // Clamped to the array's last index as a defensive fallback -
    // in practice recordDismissal() sets NEVER_KEY at MAX_DISMISSALS
    // before dismissCount could ever exceed this array's range.
    var index = Math.min(getDismissCount(), COOLDOWN_DAYS_BY_DISMISSAL.length) - 1;
    var cooldownDays = COOLDOWN_DAYS_BY_DISMISSAL[index];

    var elapsedDays = (Date.now() - Number(raw)) / (1000 * 60 * 60 * 24);
    return elapsedDays < cooldownDays;
  }

  function markInstalled() {
    localStorage.setItem(INSTALLED_KEY, "1");
  }

  function recordDismissal() {
    var count = getDismissCount() + 1;
    localStorage.setItem(DISMISS_COUNT_KEY, String(count));
    localStorage.setItem(DISMISSED_KEY, String(Date.now()));

    // They've said "not now" enough times that it's not "not now"
    // anymore - take the hint and stop asking rather than resuming a
    // short cooldown loop forever.
    if (count >= MAX_DISMISSALS) {
      localStorage.setItem(NEVER_KEY, "1");
    }
  }

  // isStandalone() only ever tells us about *this* window - installing
  // opens a separate standalone window, so the original browser tab
  // that triggered the install stays in "browser" display-mode forever.
  // markInstalled() is what actually stops the banner coming back there.
  if (
    isStandalone() ||
    isInstalled() ||
    hasOptedOutPermanently() ||
    isDismissedRecently()
  ) {
    return;
  }

  var deferredPrompt = null;

  window.addEventListener("beforeinstallprompt", function (event) {
    event.preventDefault();
    deferredPrompt = event;

    setTimeout(function () {
      // Re-check here, not just at script load - the user may have
      // dismissed an earlier prompt (e.g. a browser-native one) or
      // installed in the seconds since this fired.
      if (isInstalled() || hasOptedOutPermanently() || isDismissedRecently()) {
        return;
      }
      var banner = document.getElementById("pwaInstallBanner");
      if (banner) banner.hidden = false;
    }, SHOW_DELAY_MS);
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
        // (escalating) cooldown so we're not permanently silent on a
        // single "not now".
        if (choice.outcome === "accepted") {
          markInstalled();
        } else {
          recordDismissal();
        }
      });
    });

    dismissBtn.addEventListener("click", function () {
      banner.hidden = true;
      recordDismissal();
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
