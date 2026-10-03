// Feed behaviour: autoplay the clip in view, report watch time, count ad
// impressions, likes and sharing. No framework, so it loads fast on 3G.
(function () {
  function csrf() {
    const m = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  }
  function post(url, body) {
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      keepalive: true,
      headers: { "X-CSRFToken": csrf(), "Content-Type": "application/json", "X-Requested-With": "fetch" },
      body: JSON.stringify(body || {}),
    });
  }

  const clips = document.querySelectorAll(".clip");
  let soundOn = false;

  clips.forEach(function (clip) {
    const video = clip.querySelector("video");
    let started = 0, watched = 0, sent = false, adTimer = null;

    function flush() {
      if (started) { watched += performance.now() - started; started = 0; }
      if (clip.dataset.view && !sent && watched > 0) {
        sent = true;
        post(clip.dataset.view, { watch_ms: Math.round(watched) });
      }
    }

    clip._enter = function () {
      video.muted = !soundOn;
      video.play().catch(function () {});
      started = performance.now();
      if (clip.dataset.ad) {
        adTimer = setTimeout(function () { post(clip.dataset.ad); clip.dataset.ad = ""; }, 1000);
      }
    };
    clip._leave = function () {
      video.pause();
      clearTimeout(adTimer);
      flush();
    };
    clip._flush = flush;

    video.addEventListener("click", function () { video.paused ? video.play() : video.pause(); });
    const unmute = clip.querySelector(".unmute");
    if (unmute) unmute.addEventListener("click", function () {
      soundOn = true; video.muted = false;
      document.querySelectorAll(".unmute").forEach(function (b) { b.hidden = true; });
    });
  });

  const io = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      if (e.intersectionRatio >= 0.6) e.target._enter(); else e.target._leave();
    });
  }, { threshold: [0, 0.6] });
  clips.forEach(function (c) { io.observe(c); });

  // Report partial watches if the user closes the tab or switches app.
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") clips.forEach(function (c) { c._flush(); });
  });

  document.addEventListener("click", function (ev) {
    const like = ev.target.closest("[data-like]");
    if (like) {
      if (like.dataset.login) { location.href = like.dataset.login + "?next=" + encodeURIComponent(location.pathname); return; }
      post(like.dataset.like).then(function (r) { return r.json(); }).then(function (d) {
        like.classList.toggle("on", d.liked);
        like.querySelector(".n").textContent = d.count;
      });
      return;
    }
    const share = ev.target.closest("[data-share]");
    if (share) {
      const url = share.dataset.share, text = share.dataset.text || "Check this out on Shaya";
      if (navigator.share) { navigator.share({ title: "Shaya", text: text, url: url }).catch(function () {}); }
      else { window.open("https://wa.me/?text=" + encodeURIComponent(text + " " + url), "_blank", "noopener"); }
    }
  });
})();
