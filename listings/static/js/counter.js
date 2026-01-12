document.querySelectorAll('.stat-card').forEach(card => {
  const target = Number(card.dataset.count) || 0;
  const numberEl = card.querySelector('.stat-number');
  let current = 0;
  const step = Math.max(1, Math.floor(target / 40));

  const timer = setInterval(() => {
    current += step;
    if (current >= target) {
      current = target;
      clearInterval(timer);
    }
    numberEl.textContent = current;
  }, 20);
});
