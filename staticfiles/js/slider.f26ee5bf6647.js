(function () {
  function initSlider(slider) {
    const track = slider.querySelector("[data-slider-track]");
    const images = track?.querySelectorAll("img") || [];
    const prev = slider.querySelector("[data-slider-prev]");
    const next = slider.querySelector("[data-slider-next]");

    if (!track || images.length <= 1) {
      if (prev) prev.style.display = "none";
      if (next) next.style.display = "none";
      return;
    }

    function getSlideWidth() {
      return slider.clientWidth;
    }

    next?.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();

      track.scrollBy({
        left: getSlideWidth(),
        behavior: "smooth",
      });
    });

    prev?.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();

      track.scrollBy({
        left: -getSlideWidth(),
        behavior: "smooth",
      });
    });

    // IMPORTANT FIX (this is often what breaks after refactors)
    track.style.scrollBehavior = "smooth";
    track.style.overflowX = "auto";
    track.style.display = "flex";
    track.style.scrollSnapType = "x mandatory";

    images.forEach((img) => {
      img.style.flex = "0 0 100%";
      img.style.scrollSnapAlign = "center";
      img.style.objectFit = "cover";
    });

    // Allow both axes so the browser can tell per-gesture whether a
    // touch starting on the image is a horizontal swipe (advance the
    // carousel) or a vertical one (scroll the page). `pan-x` alone
    // told the browser to only ever handle horizontal touches here,
    // which silently ate every attempt to scroll the page from a
    // touch that started on a card image.
    track.style.touchAction = "pan-x pan-y";
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-slider]").forEach(initSlider);
  });
})();