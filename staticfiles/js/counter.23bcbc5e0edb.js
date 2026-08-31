(function () {
  const cards = document.querySelectorAll(".stat-card");
  if (!cards.length) return;

  const runCounter = (card) => {
    if (card.dataset.ran === "1") return;
    card.dataset.ran = "1";

    const target = Number(card.dataset.count) || 0;
    const numberEl = card.querySelector(".stat-number");
    if (!numberEl) return;

    let current = 0;
    const duration = 900; // ms
    const start = performance.now();

    const tick = (now) => {
      const progress = Math.min(1, (now - start) / duration);
      current = Math.floor(target * progress);
      numberEl.textContent = current.toLocaleString();

      if (progress < 1) requestAnimationFrame(tick);
      else numberEl.textContent = target.toLocaleString();
    };

    requestAnimationFrame(tick);
  };

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) runCounter(entry.target);
      });
    },
    { threshold: 0.3 }
  );

  cards.forEach((card) => observer.observe(card));
})();
