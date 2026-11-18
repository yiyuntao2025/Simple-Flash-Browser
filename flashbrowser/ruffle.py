from __future__ import annotations

_BOOTSTRAP = r"""
(function () {
  if (location.hostname === "127.0.0.1" && location.port === "__PORT__") {
    return;
  }
  if (window.__flashassistRuffle) {
    return;
  }
  window.__flashassistRuffle = true;

  function boot() {
    var RufflePlayer = (window.RufflePlayer = window.RufflePlayer || {});
    var config = RufflePlayer.config || {};
    config.publicPath = "__BASE__/ruffle/";
    config.polyfills = true;
    config.autoplay = "on";
    config.unmuteOverlay = "hidden";
    config.splashScreen = false;
    config.contextMenu = "rightClick";
    config.letterbox = "on";
    config.scale = "showAll";
    config.quality = "high";
    config.logLevel = "error";
    config.openUrlMode = "allow";
    config.allowFullscreen = true;
    RufflePlayer.config = config;

    var script = document.createElement("script");
    script.src = "__BASE__/ruffle/ruffle.js";
    script.async = false;
    script.onerror = function () {};
    (document.head || document.documentElement || document).appendChild(script);
  }

  if (document.documentElement) {
    boot();
  } else {
    document.addEventListener("readystatechange", function handler() {
      if (document.documentElement) {
        document.removeEventListener("readystatechange", handler);
        boot();
      }
    });
  }
})();
"""


def bootstrap_script(port: int, base: str) -> str:
    return _BOOTSTRAP.replace("__BASE__", base).replace("__PORT__", str(port))
