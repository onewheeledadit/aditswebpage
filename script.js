/* Aditya Venkataraman — hero interactions
 *
 * Each word in the set previews a facet of Aditya:
 *   - swaps the portrait (adit1 -> adit2)
 *   - drops the theme emoji over the eyes
 *   - tints a soft glow behind the head
 *
 * Hover / keyboard focus = transient preview.
 * Click / tap = pin that state (so touch devices, which have no hover, get it).
 */
(function () {
  "use strict";

  var portrait = document.getElementById("portrait");
  var eyes = document.getElementById("emoji");
  var hint = document.getElementById("hint");
  var words = Array.prototype.slice.call(document.querySelectorAll(".word"));
  var glyphs = eyes
    ? Array.prototype.slice.call(eyes.querySelectorAll(".portrait__emoji"))
    : [];
  if (!portrait || !glyphs.length || !words.length) return;

  var pinned = null; // the currently pinned button, or null

  function setGlyphs(text) {
    glyphs.forEach(function (g) { g.textContent = text; });
  }

  function paint(btn) {
    portrait.dataset.theme = btn.dataset.theme;
    setGlyphs(btn.dataset.emoji);
    portrait.classList.add("is-active");
  }

  function clear() {
    portrait.classList.remove("is-active");
    // keep data-theme until the fade finishes so the glow doesn't flip colour
    window.setTimeout(function () {
      if (!portrait.classList.contains("is-active")) {
        delete portrait.dataset.theme;
        setGlyphs("");
      }
    }, 260);
  }

  function preview(btn) {
    if (pinned) return; // a pin wins over hover
    paint(btn);
  }

  function endPreview() {
    if (pinned) return;
    clear();
  }

  function togglePin(btn) {
    if (pinned === btn) {
      pinned = null;
      btn.setAttribute("aria-pressed", "false");
      clear();
    } else {
      if (pinned) pinned.setAttribute("aria-pressed", "false");
      pinned = btn;
      btn.setAttribute("aria-pressed", "true");
      paint(btn);
    }
  }

  words.forEach(function (btn) {
    btn.addEventListener("mouseenter", function () { preview(btn); });
    btn.addEventListener("mouseleave", endPreview);
    btn.addEventListener("focus", function () { preview(btn); });
    btn.addEventListener("blur", endPreview);
    btn.addEventListener("click", function () {
      if (btn.tagName === "A") return; // real link: let the browser navigate
      togglePin(btn);
    });
  });

  // Show the pin hint only where hover isn't available (touch).
  if (window.matchMedia && window.matchMedia("(hover: none)").matches && hint) {
    hint.hidden = false;
  }

  // Release a pin when tapping / clicking elsewhere.
  document.addEventListener("click", function (e) {
    if (pinned && !e.target.closest(".word")) togglePin(pinned);
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && pinned) togglePin(pinned);
  });

  /* ---- pointer: parallax + look left / right --------------------------- *
   * With no topic engaged, the figure glances the way the cursor sits:
   *   cursor left of the figure  -> adit3   cursor right -> adit4   over it -> adit1
   * A pinned/hovered topic (adit2 + emoji) always wins.
   */
  var fine = window.matchMedia("(pointer: fine)").matches;
  var still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (fine && !still) {
    var pRect = portrait.getBoundingClientRect();
    var refreshRect = function () { pRect = portrait.getBoundingClientRect(); };
    window.addEventListener("resize", refreshRect);
    window.addEventListener("scroll", refreshRect, { passive: true });

    var raf = 0;
    window.addEventListener("pointermove", function (e) {
      var x = e.clientX;
      var y = e.clientY;
      if (raf) return;
      raf = window.requestAnimationFrame(function () {
        raf = 0;
        var dx = (x / window.innerWidth - 0.5) * 2;
        var dy = (y / window.innerHeight - 0.5) * 2;
        portrait.style.transform =
          "translate(" + (dx * 8).toFixed(2) + "px," + (dy * 6).toFixed(2) + "px)";

        var gaze = x < pRect.left ? "left" : x > pRect.right ? "right" : "";
        if (portrait.dataset.gaze !== gaze) portrait.dataset.gaze = gaze;
      });
    });

    document.addEventListener("pointerleave", function () {
      portrait.style.transform = "";
      portrait.dataset.gaze = "";
    });
  }
})();
