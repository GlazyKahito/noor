/* NOOR intro: a 3-second "printing press" reveal shown once per visit on the landing page.
   The animation itself is CSS (@keyframes in style.css). This script only decides whether to
   show it, closes it after 3 seconds, and lets the visitor skip it (button, click, Enter, Esc).
   Without JavaScript, or with "reduce motion" switched on, the intro never appears. */
(function () {
  var intro = document.getElementById("intro");
  if (!intro) return;
  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var seen = false;
  try { seen = sessionStorage.getItem("noor-intro-seen") === "1"; } catch (e) { seen = false; }
  if (reduceMotion || seen) { intro.remove(); return; }
  try { sessionStorage.setItem("noor-intro-seen", "1"); } catch (e) { /* private mode: show anyway */ }

  intro.classList.add("intro-on");
  var timer = setTimeout(close, 3000);

  function close() {
    clearTimeout(timer);
    document.removeEventListener("keydown", onKey);
    intro.classList.add("intro-out");              // CSS fades it out
    setTimeout(function () { intro.remove(); }, 450);
  }
  function onKey(event) {
    if (event.key === "Enter" || event.key === "Escape") close();
  }
  intro.addEventListener("click", close);
  document.addEventListener("keydown", onKey);
  document.getElementById("intro-skip").focus();
})();
