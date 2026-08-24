function initAutocomplete() {
  const input = document.getElementById("id_full_address");

  if (!input || typeof google === "undefined") return;

  const autocomplete = new google.maps.places.Autocomplete(input, {
    types: ["geocode"],
    componentRestrictions: { country: "za" },
  });

  autocomplete.addListener("place_changed", function () {
    const place = autocomplete.getPlace();

    if (!place || !place.address_components) return;

    let suburb = "";
    let city = "";
    let province = "";
    let postal_code = "";

    for (const component of place.address_components) {
      const types = component.types;

      if (types.includes("route")) {
        // optional street capture if needed later
      }

      if (types.includes("sublocality") || types.includes("neighborhood")) {
        suburb = component.long_name;
      }

      if (types.includes("locality")) {
        city = component.long_name;
      }

      if (types.includes("administrative_area_level_1")) {
        province = component.long_name;
      }

      if (types.includes("postal_code")) {
        postal_code = component.long_name;
      }
    }

    const suburbEl = document.getElementById("id_suburb");
    const cityEl = document.getElementById("id_city");
    const provinceEl = document.getElementById("id_province");
    const postalEl = document.getElementById("id_postal_code");

    if (suburbEl) suburbEl.value = suburb;
    if (cityEl) cityEl.value = city;
    if (provinceEl) provinceEl.value = province;
    if (postalEl) postalEl.value = postal_code;

    // enforce formatted address
    input.value = place.formatted_address;
  });
}

document.addEventListener("DOMContentLoaded", initAutocomplete);
