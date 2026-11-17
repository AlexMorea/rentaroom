// Turns the "Add a room" form into four short steps with a progress bar.
// Without this script the form simply shows every section on one page,
// so it never stops anyone from listing.
(function () {
  const form = document.querySelector("[data-room-steps]");
  if (!form) return;

  const steps = Array.from(form.querySelectorAll(".cr-step"));
  const progress = form.querySelector("[data-cr-progress]");
  const back = form.querySelector("[data-cr-back]");
  const next = form.querySelector("[data-cr-next]");
  const submit = form.querySelector("[data-cr-submit]");
  const cancel = form.querySelector("[data-cr-cancel]");
  if (steps.length < 2 || !next || !submit) return;

  form.classList.add("cr-stepped");
  if (progress) progress.hidden = false;

  // Open on the first step that has a server-side error, if any.
  let current = steps.findIndex(function (s) { return s.querySelector(".field-error"); });
  if (current < 0) current = 0;

  function show(i) {
    current = i;
    steps.forEach(function (s, n) { s.hidden = n !== i; });
    const last = i === steps.length - 1;
    back.hidden = i === 0;
    if (cancel) cancel.hidden = i !== 0;
    next.hidden = last;
    submit.hidden = !last;
    if (progress) {
      progress.querySelectorAll("[data-cr-dot]").forEach(function (dot, n) {
        dot.classList.toggle("is-done", n < i);
        dot.classList.toggle("is-current", n === i);
        if (n === i) dot.setAttribute("aria-current", "step"); else dot.removeAttribute("aria-current");
      });
    }
    const top = form.getBoundingClientRect().top + window.scrollY - 90;
    window.scrollTo({ top: top, behavior: "smooth" });
  }

  function stepIsValid(i) {
    const fields = steps[i].querySelectorAll("input, select, textarea");
    for (const field of fields) {
      if (!field.checkValidity()) {
        field.reportValidity();
        return false;
      }
    }
    return true;
  }

  next.addEventListener("click", function () {
    if (stepIsValid(current)) show(current + 1);
  });
  back.addEventListener("click", function () { show(current - 1); });

  // Pressing Enter in a text field moves to the next step instead of
  // submitting half a listing.
  form.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && e.target.tagName === "INPUT" && current < steps.length - 1) {
      e.preventDefault();
      next.click();
    }
  });

  // If the browser blocks submit because a field on an earlier step is
  // invalid, jump to that step so the person can see what's wrong.
  form.addEventListener("invalid", function (e) {
    const owner = steps.findIndex(function (s) { return s.contains(e.target); });
    if (owner >= 0 && owner !== current) show(owner);
  }, true);

  show(current);
})();
