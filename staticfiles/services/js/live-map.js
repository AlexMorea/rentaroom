let guardianMap = null;
let liveMarker = null;
let breadcrumbLine = null;
let breadcrumbCoords = [];

function initializeGuardianMap() {

  const mapElement = document.getElementById("guardian-map");

  if (!mapElement) return;

  guardianMap = L.map("guardian-map").setView(
    [-25.7479, 28.2293],
    13
  );

  L.tileLayer(
    "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    {
      attribution: "&copy; OpenStreetMap contributors",
    }
  ).addTo(guardianMap);

  breadcrumbLine = L.polyline([], {
    weight: 5,
    opacity: 0.7,
  }).addTo(guardianMap);
}

function updateGuardianPosition(lat, lng) {

  if (!guardianMap) return;

  const position = [lat, lng];

  if (!liveMarker) {

    liveMarker = L.marker(position)
      .addTo(guardianMap)
      .bindPopup("🛡 Live Guardian Tracking");

    guardianMap.setView(position, 15);

  } else {

    liveMarker.setLatLng(position);

  }

  breadcrumbCoords.push(position);

  breadcrumbLine.setLatLngs(breadcrumbCoords);
}

document.addEventListener(
  "DOMContentLoaded",
  initializeGuardianMap
);