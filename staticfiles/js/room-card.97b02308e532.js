(function () {
  function getCsrfToken() {
    const el = document.querySelector("[name=csrfmiddlewaretoken]");
    return el ? el.value : "";
  }

  // ---- Photo fade-in ----
  // Progressive enhancement: only images JS catches before they finish
  // loading get the temporary opacity dip - see the rc-img-loading rule
  // in _room_cards.html for why that's safe if this script never runs.
  function markLoaded(img) {
    if (img.complete && img.naturalWidth > 0) return;

    img.classList.add("rc-img-loading");

    const finish = () => {
      img.classList.remove("rc-img-loading");
      img.classList.add("rc-img-loaded");
    };

    img.addEventListener("load", finish, { once: true });
    img.addEventListener("error", finish, { once: true });
  }

  function scanImages(root) {
    root.querySelectorAll(".rc-img").forEach(markLoaded);
  }

  document.addEventListener("DOMContentLoaded", function () {
    scanImages(document);

    // Room cards can also arrive later via the "Browse More" AJAX
    // pagination on room_list.html - a MutationObserver on the grid
    // catches those without this script needing to know anything about
    // that pagination code.
    const grid = document.getElementById("roomGrid");
    if (grid && window.MutationObserver) {
      new MutationObserver((mutations) => {
        mutations.forEach((mutation) => {
          // Stagger only within one batch (e.g. one page of "Browse
          // More" results landing in a single insertAdjacentHTML call) -
          // resets each mutation record rather than climbing forever.
          let staggerIndex = 0;

          mutation.addedNodes.forEach((node) => {
            if (node.nodeType !== 1) return;

            if (node.classList && node.classList.contains("room-card")) {
              node.classList.add("rc-card-enter");
              node.style.animationDelay = `${Math.min(staggerIndex, 8) * 40}ms`;
              staggerIndex++;
            }

            if (node.classList && node.classList.contains("rc-img")) {
              markLoaded(node);
            }
            scanImages(node);
          });
        });
      }).observe(grid, { childList: true, subtree: true });
    }
  });

  // ---- Save / favorite heart ----
  document.addEventListener("click", async function (e) {
    const btn = e.target.closest("[data-fav-btn]");
    if (!btn) return;

    e.preventDefault();
    e.stopPropagation();

    if (btn.disabled) return;
    btn.disabled = true;

    const roomId = btn.dataset.roomId;
    const wasFavorited = btn.dataset.favorited === "true";

    function applyState(favorited) {
      btn.classList.toggle("rc-fav-active", favorited);
      btn.dataset.favorited = String(favorited);
      btn.setAttribute("aria-pressed", String(favorited));
    }

    // Optimistic flip - feels instant, corrected below if the server
    // doesn't confirm it.
    applyState(!wasFavorited);
    btn.classList.add("rc-fav-pop");
    setTimeout(() => btn.classList.remove("rc-fav-pop"), 320);

    try {
      const res = await fetch(`/rooms/${roomId}/favorite/`, {
        method: "POST",
        headers: {
          "X-Requested-With": "XMLHttpRequest",
          "X-CSRFToken": getCsrfToken(),
        },
      });

      if (res.redirected) {
        // Not logged in - Django's login_required bounced this through
        // to the login page. Revert the optimistic flip and send the
        // browser there for real, with a way back to this page.
        applyState(wasFavorited);
        window.location.href =
          "/login/?next=" +
          encodeURIComponent(window.location.pathname + window.location.search);
        return;
      }

      if (!res.ok) {
        // e.g. 403 for an account that isn't a tenant - revert quietly.
        applyState(wasFavorited);
        return;
      }

      const data = await res.json();
      applyState(!!data.favorited);
    } catch (err) {
      applyState(wasFavorited);
    } finally {
      btn.disabled = false;
    }
  });
})();
