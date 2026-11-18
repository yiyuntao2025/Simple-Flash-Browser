(function () {
  "use strict";

  var ICON_MAX =
    '<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="2.7" y="2.7" width="10.6" height="10.6" rx="1.6" fill="none" stroke="currentColor" stroke-width="1.3"/></svg>';
  var ICON_RESTORE =
    '<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="2.6" y="4.6" width="8.8" height="8.8" rx="1.4" fill="none" stroke="currentColor" stroke-width="1.2"/><path d="M5.2 4.6V3.4A1.4 1.4 0 0 1 6.6 2h6A1.4 1.4 0 0 1 14 3.4v6a1.4 1.4 0 0 1-1.4 1.4h-1.2" fill="none" stroke="currentColor" stroke-width="1.2"/></svg>';
  var ICON_SUN =
    '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4.2" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M12 2.8v2.4M12 18.8v2.4M2.8 12h2.4M18.8 12h2.4M5.5 5.5l1.7 1.7M16.8 16.8l1.7 1.7M18.5 5.5l-1.7 1.7M7.2 16.8l-1.7 1.7" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>';
  var ICON_MOON =
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20.5 15.2A8.6 8.6 0 0 1 8.8 3.5 8.6 8.6 0 1 0 20.5 15.2Z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/></svg>';

  var bridge = null;
  var state = null;
  var tabsSignature = "";
  var dom = {};

  function $(id) {
    return document.getElementById(id);
  }

  function call(method, argument) {
    if (!bridge || typeof bridge[method] !== "function") {
      return;
    }
    if (typeof argument === "undefined") {
      bridge[method]();
    } else {
      bridge[method](argument);
    }
  }

  function connect() {
    if (!window.qt || !window.qt.webChannelTransport) {
      window.setTimeout(connect, 50);
      return;
    }
    new window.QWebChannel(window.qt.webChannelTransport, function (channel) {
      bridge = channel.objects.bridge;
      bridge.stateChanged.connect(function (payload) {
        try {
          applyState(JSON.parse(payload));
        } catch (error) {
          return;
        }
      });
      bridge.request_state();
    });
  }

  function renderTabs(tabs, active) {
    var signature =
      active +
      "|" +
      tabs
        .map(function (tab) {
          return (
            (tab.title || "") +
            "|" +
            (tab.icon ? tab.icon.length : 0) +
            "|" +
            (tab.loading ? 1 : 0)
          );
        })
        .join("~");

    if (signature === tabsSignature) {
      return;
    }
    tabsSignature = signature;

    while (dom.tabs.firstChild) {
      dom.tabs.removeChild(dom.tabs.firstChild);
    }

    tabs.forEach(function (tab, index) {
      var item = document.createElement("div");
      item.className = "tab";
      if (index === active) {
        item.className += " active";
      }
      if (tab.loading) {
        item.className += " loading";
      }
      item.setAttribute("role", "tab");
      item.dataset.index = String(index);
      item.title = tab.title || "新标签页";

      if (tab.icon) {
        var image = document.createElement("img");
        image.className = "favicon";
        image.src = tab.icon;
        image.alt = "";
        image.draggable = false;
        item.appendChild(image);
      } else {
        var fallback = document.createElement("div");
        fallback.className = "favicon fallback";
        fallback.textContent = (tab.title || "F").trim().charAt(0) || "F";
        item.appendChild(fallback);
      }

      var title = document.createElement("span");
      title.className = "title";
      title.textContent = tab.title || "新标签页";
      item.appendChild(title);

      var close = document.createElement("button");
      close.className = "close";
      close.type = "button";
      close.title = "关闭标签页";
      close.textContent = "\u00d7";
      item.appendChild(close);

      dom.tabs.appendChild(item);
    });

    var activeItem = dom.tabs.children[active];
    if (activeItem) {
      window.requestAnimationFrame(function () {
        activeItem.scrollIntoView({ block: "nearest", inline: "nearest" });
      });
    }
  }

  function applyState(next) {
    state = next;

    var tabs = next.tabs || [];
    var active = typeof next.active === "number" ? next.active : 0;
    renderTabs(tabs, active);

    if (document.activeElement !== dom.address) {
      dom.address.value = next.url || "";
    }

    var light = next.theme === "light";
    document.documentElement.dataset.theme = light ? "light" : "dark";
    dom.theme.innerHTML = light ? ICON_MOON : ICON_SUN;
    dom.theme.title = light ? "切换到深色模式" : "切换到浅色模式";

    var engine = next.searchLabel || "Bing";
    dom.address.placeholder = "在 " + engine + " 搜索，或输入网址";

    dom.back.disabled = !next.canBack;
    dom.forward.disabled = !next.canForward;
    document.body.classList.toggle("loading", Boolean(next.loading));
    dom.reload.title = next.loading ? "停止加载" : "重新加载 (F5)";

    dom.status.className = "status-pill " + (next.statusClass || "");
    dom.statusText.textContent = next.statusText || "";
    dom.status.title = next.statusTitle || "";

    dom.winMax.innerHTML = next.maximized ? ICON_RESTORE : ICON_MAX;
    dom.winMax.title = next.maximized ? "还原" : "最大化";
  }

  function selectTab(index) {
    call("select_tab", index);
  }

  function closeTab(index) {
    call("close_tab", index);
  }

  function isInteractive(target) {
    return !!target.closest("button, input, a, .tab");
  }

  function attachDrag(element) {
    element.addEventListener("mousedown", function (event) {
      if (event.button !== 0 || isInteractive(event.target)) {
        return;
      }
      call("start_drag");
    });

    element.addEventListener("dblclick", function (event) {
      if (isInteractive(event.target)) {
        return;
      }
      call("toggle_maximize");
    });
  }

  function bindUi() {
    dom.back.addEventListener("click", function () {
      call("go_back");
    });
    dom.forward.addEventListener("click", function () {
      call("go_forward");
    });
    dom.reload.addEventListener("click", function () {
      if (state && state.loading) {
        call("stop");
      } else {
        call("reload");
      }
    });
    dom.home.addEventListener("click", function () {
      call("go_home");
    });
    dom.newtab.addEventListener("click", function () {
      call("new_tab");
    });
    dom.openfile.addEventListener("click", function () {
      call("open_file");
    });
    dom.menu.addEventListener("click", function () {
      call("show_menu");
    });
    dom.theme.addEventListener("click", function () {
      call("toggle_theme");
    });

    dom.min.addEventListener("click", function () {
      call("minimize");
    });
    dom.max.addEventListener("click", function () {
      call("toggle_maximize");
    });
    dom.close.addEventListener("click", function () {
      call("close_window");
    });

    dom.tabs.addEventListener("mousedown", function (event) {
      if (event.button === 1) {
        var middleTab = event.target.closest(".tab");
        if (middleTab) {
          event.preventDefault();
          closeTab(Number(middleTab.dataset.index));
        }
      }
    });

    dom.tabs.addEventListener("click", function (event) {
      var close = event.target.closest(".close");
      if (close) {
        event.stopPropagation();
        closeTab(Number(close.closest(".tab").dataset.index));
        return;
      }
      var tab = event.target.closest(".tab");
      if (tab) {
        selectTab(Number(tab.dataset.index));
      }
    });

    dom.tabs.addEventListener(
      "wheel",
      function (event) {
        if (Math.abs(event.deltaY) > Math.abs(event.deltaX)) {
          dom.tabs.scrollLeft += event.deltaY;
          event.preventDefault();
        }
      },
      { passive: false }
    );

    dom.omnibox.addEventListener("submit", function (event) {
      event.preventDefault();
      var value = dom.address.value.trim();
      if (!value) {
        return;
      }
      call("navigate", value);
      dom.address.blur();
    });

    dom.address.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        dom.address.value = state ? state.url || "" : "";
        dom.address.blur();
      }
    });

    attachDrag(dom.titlebar);
    attachDrag(dom.dragspace);
    attachDrag(dom.brand);
  }

  function init() {
    dom.tabs = $("tabs");
    dom.titlebar = $("titlebar");
    dom.dragspace = $("dragspace");
    dom.brand = $("brand");
    dom.newtab = $("newtab");
    dom.address = $("address");
    dom.omnibox = $("omnibox");
    dom.back = $("nav-back");
    dom.forward = $("nav-forward");
    dom.reload = $("nav-reload");
    dom.home = $("nav-home");
    dom.status = $("status");
    dom.statusText = $("status-text");
    dom.openfile = $("openfile");
    dom.menu = $("menu");
    dom.theme = $("theme-toggle");
    dom.min = $("win-min");
    dom.max = $("win-max");
    dom.close = $("win-close");

    bindUi();
    connect();
  }

  window.__focusAddress = function () {
    if (!dom.address) {
      return;
    }
    dom.address.focus();
    dom.address.select();
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
