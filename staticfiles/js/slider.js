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

    // mobile behaviour (optional but safe)
    track.style.touchAction = "pan-x";
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-slider]").forEach(initSlider);
  });
})();