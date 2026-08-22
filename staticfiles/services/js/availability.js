document.addEventListener("DOMContentLoaded", function () {

  const toggleBtn = document.getElementById(
    "availabilityToggle"
  );

  if (!toggleBtn) return;

  toggleBtn.addEventListener("click", async function () {

    const response = await fetch(
      "/services/driver/toggle-availability/",
      {
        method: "POST",
        headers: {
          "X-CSRFToken": getCookie("csrftoken"),
        },
      }
    );

    const data = await response.json();

    if (data.available) {

      toggleBtn.innerHTML = "🟢 ONLINE";

      toggleBtn.classList.add("online");

    } else {

      toggleBtn.innerHTML = "⚪ OFFLINE";

      toggleBtn.classList.remove("online");

    }

  });

});

function getCookie(name) {

  let cookieValue = null;

  if (document.cookie && document.cookie !== "") {

    const cookies = document.cookie.split(";");

    for (let i = 0; i < cookies.length; i++) {

      const cookie = cookies[i].trim();

      if (
        cookie.substring(0, name.length + 1) ===
        name + "="
      ) {

        cookieValue = decodeURIComponent(
          cookie.substring(name.length + 1)
        );

        break;
      }
    }
  }

  return cookieValue;
}