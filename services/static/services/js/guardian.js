let watchId = null;

function startTracking(sessionId) {
  if (!navigator.geolocation) {
    alert("Geolocation not supported");
    return;
  }

  watchId = setInterval(() => {
    navigator.geolocation.getCurrentPosition(async (position) => {
      const data = {
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
      };

      await fetch(`/services/guardian/ping/${sessionId}/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCookie("csrftoken"),
        },
        body: JSON.stringify(data),
      });
    });
  }, 15000); // every 15 seconds
}

function triggerPanic(sessionId) {
  navigator.geolocation.getCurrentPosition(async (position) => {
    const data = {
      latitude: position.coords.latitude,
      longitude: position.coords.longitude,
    };

    await fetch(`/services/guardian/panic/${sessionId}/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCookie("csrftoken"),
      },
      body: JSON.stringify(data),
    });

    alert("🚨 Panic alert sent!");
  });
}

function stopTracking() {
  if (watchId) {
    clearInterval(watchId);
  }
}

// CSRF helper
function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== "") {
    const cookies = document.cookie.split(";");
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === name + "=") {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}
