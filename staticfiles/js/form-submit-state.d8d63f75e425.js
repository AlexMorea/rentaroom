// Fix #4 (Phase A mobile audit): prevent duplicate submissions and give
// visual feedback on slow mobile connections.
//
// Applies automatically to every <form> on the page. On submit, disables
// the submit button and swaps its label to a loading state, re-enabling
// it if the browser blocks navigation (e.g. back-forward cache restore).
//
// Opt out per-form with: <form data-no-loading-state> ... </form>
// Opt out per-button with: <button data-no-loading-state> ... </button>
// Customize the loading label with: <button data-loading-text="Uploading…">

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("form").forEach((form) => {
    if (form.hasAttribute("data-no-loading-state")) return;

    form.addEventListener("submit", () => {
      // The native "submit" event only fires after built-in HTML5
      // validation passes, so it's safe to lock the button here.
      const submitBtn = form.querySelector(
        'button[type="submit"], input[type="submit"]'
      );

      if (!submitBtn || submitBtn.hasAttribute("data-no-loading-state")) {
        return;
      }

      if (submitBtn.disabled) {
        // Already mid-submit — this blocks a second tap from firing
        // another submit before the first request completes.
        return;
      }

      const loadingText =
        submitBtn.dataset.loadingText ||
        (submitBtn.tagName === "INPUT" ? null : "Please wait…");

      submitBtn.disabled = true;
      submitBtn.classList.add("is-submitting");

      if (submitBtn.tagName === "INPUT") {
        submitBtn.dataset.originalValue = submitBtn.value;
        if (submitBtn.dataset.loadingText) {
          submitBtn.value = submitBtn.dataset.loadingText;
        }
      } else {
        submitBtn.dataset.originalHtml = submitBtn.innerHTML;
        submitBtn.innerHTML = loadingText;
      }
    });
  });

  // If the page is restored from the back-forward cache (bfcache) after a
  // user hits "back" post-submit, buttons can be left disabled. Reset them.
  window.addEventListener("pageshow", (event) => {
    if (!event.persisted) return;

    document
      .querySelectorAll("button.is-submitting, input.is-submitting")
      .forEach((btn) => {
        btn.disabled = false;
        btn.classList.remove("is-submitting");
        if (btn.tagName === "INPUT" && btn.dataset.originalValue) {
          btn.value = btn.dataset.originalValue;
        } else if (btn.dataset.originalHtml) {
          btn.innerHTML = btn.dataset.originalHtml;
        }
      });
  });
});