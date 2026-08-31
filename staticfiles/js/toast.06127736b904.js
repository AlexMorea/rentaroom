document.addEventListener("DOMContentLoaded", function () {
  const alerts = document.querySelectorAll(".toast");

  alerts.forEach((alert) => {
    alert.classList.add("show");

    setTimeout(() => {
      alert.classList.remove("show");

      setTimeout(() => {
        alert.remove();
      }, 250);
    }, 3000);
  });
});

