(() => {
  const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  if (tg) {
    try {
      tg.ready();
      tg.expand();
    } catch {}
  }

  // Извлекаем ключ доступа (?key=...) и данные Web Share Target (?share_title/text/url=...)
  const urlParams = new URLSearchParams(window.location.search);
  const keyParam = urlParams.get("key");
  const shareTitle = (urlParams.get("share_title") || "").trim();
  const shareText = (urlParams.get("share_text") || "").trim();
  const shareUrl = (urlParams.get("share_url") || "").trim();
  const shareParts = [];
  if (shareUrl) {
    shareParts.push(shareUrl);
    if (shareTitle && !shareTitle.includes(shareUrl)) shareParts.push(shareTitle);
    if (shareText && !shareText.includes(shareUrl) && shareText !== shareTitle) shareParts.push(shareText);
  } else {
    if (shareTitle) shareParts.push(shareTitle);
    if (shareText && shareText !== shareTitle) shareParts.push(shareText);
  }
  let pendingShareText = shareParts.join("\n").trim();

  if (keyParam || shareTitle || shareText || shareUrl) {
    if (keyParam) localStorage.setItem("sb_access_key", keyParam.trim());
    urlParams.delete("key");
    urlParams.delete("share_title");
    urlParams.delete("share_text");
    urlParams.delete("share_url");
    const cleanSearch = urlParams.toString();
    const cleanUrl = window.location.pathname + (cleanSearch ? `?${cleanSearch}` : "") + window.location.hash;
    window.history.replaceState({}, "", cleanUrl);
  }

  function getAccessKey() {
    return localStorage.getItem("sb_access_key") || "";
  }

  const CATALOG_PAGE_SIZE = 100;
  const isTgWebApp = Boolean(tg && tg.initData);
  let tmaHomeScreenCanAdd = false;

  function syncTmaSafeArea() {
    if (!tg) return;
    try {
      const rootStyle = document.documentElement.style;
      const saTop = Number((tg.safeAreaInset && tg.safeAreaInset.top) || 0);
      const csaTop = Number((tg.contentSafeAreaInset && tg.contentSafeAreaInset.top) || 0);
      rootStyle.setProperty("--tg-safe-area-inset-top", `${Math.max(0, saTop)}px`);
      rootStyle.setProperty("--tg-content-safe-area-inset-top", `${Math.max(0, csaTop)}px`);
      document.documentElement.classList.toggle("is-tma-fullscreen", Boolean(tg.isFullscreen));
    } catch {}
  }

  function saveCloudPref(key, value) {
    if (!isTgWebApp || !tg || !tg.CloudStorage || typeof tg.CloudStorage.setItem !== "function") return;
    try {
      tg.CloudStorage.setItem(key, String(value), () => {});
    } catch {}
  }

  function hydrateFromTgCloudStorage() {
    if (!isTgWebApp || !tg || !tg.CloudStorage || typeof tg.CloudStorage.getItems !== "function") return;
    try {
      tg.CloudStorage.getItems(["sb_theme_mode", "sb_view_modes_by_tab_v1"], (err, values) => {
        if (err || !values) return;
        let changedViewMode = false;
        let changedTheme = false;
        if (values.sb_theme_mode && ["auto", "light", "dark"].includes(values.sb_theme_mode)) {
          if (values.sb_theme_mode !== state.themeMode) {
            state.themeMode = values.sb_theme_mode;
            localStorage.setItem("sb_theme_mode", state.themeMode);
            changedTheme = true;
          }
        }
        if (values.sb_view_modes_by_tab_v1) {
          try {
            const parsed = JSON.parse(values.sb_view_modes_by_tab_v1);
            if (parsed && typeof parsed === "object") {
              viewModesByTab = { ...viewModesByTab, ...parsed };
              localStorage.setItem("sb_view_modes_by_tab_v1", JSON.stringify(viewModesByTab));
              const nextMode = getViewModeForTab(state.tab);
              if (nextMode !== state.viewMode && state.view === "catalog") {
                state.viewMode = nextMode;
                changedViewMode = true;
              }
            }
          } catch {}
        }
        if (changedTheme) applyTheme();
        if (changedViewMode) {
          syncNavigationState();
          if (state.items.length > 0) renderCatalog({ skipDrawer: true });
        }
      });
    } catch {}
  }

  function toggleTmaFullscreen() {
    if (!tg) return;
    try {
      if (tg.isFullscreen && typeof tg.exitFullscreen === "function") {
        tg.exitFullscreen();
      } else if (typeof tg.requestFullscreen === "function") {
        tg.requestFullscreen();
      }
    } catch {}
  }

  function triggerTmaHomeScreen() {
    if (!tg || typeof tg.addToHomeScreen !== "function") return;
    try {
      tg.addToHomeScreen();
      tmaHomeScreenCanAdd = false;
    } catch {}
  }

  if (isTgWebApp) {
    document.documentElement.classList.add("is-tma");
    syncTmaSafeArea();
    if (tg && typeof tg.onEvent === "function") {
      try {
        tg.onEvent("fullscreenChanged", syncTmaSafeArea);
        tg.onEvent("safeAreaChanged", syncTmaSafeArea);
        tg.onEvent("contentSafeAreaChanged", syncTmaSafeArea);
      } catch {}
    }
    if (tg && typeof tg.addToHomeScreen === "function") {
      if (typeof tg.checkHomeScreenStatus === "function") {
        try {
          tg.checkHomeScreenStatus((status) => {
            tmaHomeScreenCanAdd = status !== "added" && status !== "unsupported";
          });
        } catch {
          tmaHomeScreenCanAdd = true;
        }
      } else {
        tmaHomeScreenCanAdd = true;
      }
    }
  }

  let deferredInstallPrompt = null;
  if (!isTgWebApp && "serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("./sw.js").catch(() => undefined);
    });
  }
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    deferredInstallPrompt = e;
  });

  const UI_ICONS = {
    library: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m16 6 4 14"/><path d="M12 6v14"/><path d="M8 8v12"/><path d="M4 4v16"/></svg>`,
    chart: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><rect width="4" height="7" x="7" y="10" rx="1"/><rect width="4" height="12" x="15" y="5" rx="1"/></svg>`,
    checkSquare: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="18" x="3" y="3" rx="3"/><path d="m9 12 2 2 4-4"/></svg>`,
    inbox: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/></svg>`,
    refresh: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/></svg>`,
    logout: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" x2="9" y1="12" y2="12"/></svg>`,
    search: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>`,
    sliders: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="4" x2="4" y1="21" y2="14"/><line x1="4" x2="4" y1="10" y2="3"/><line x1="12" x2="12" y1="21" y2="12"/><line x1="12" x2="12" y1="8" y2="3"/><line x1="20" x2="20" y1="21" y2="16"/><line x1="20" x2="20" y1="12" y2="3"/><line x1="2" x2="6" y1="14" y2="14"/><line x1="10" x2="14" y1="8" y2="8"/><line x1="18" x2="22" y1="16" y2="16"/></svg>`,
    list: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="8" x2="21" y1="6" y2="6"/><line x1="8" x2="21" y1="12" y2="12"/><line x1="8" x2="21" y1="18" y2="18"/><line x1="3" x2="3.01" y1="6" y2="6"/><line x1="3" x2="3.01" y1="12" y2="12"/><line x1="3" x2="3.01" y1="18" y2="18"/></svg>`,
    posters: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="7" height="10" x="3" y="3" rx="1.5"/><rect width="7" height="10" x="14" y="3" rx="1.5"/><path d="M3 17h7"/><path d="M14 17h7"/><path d="M3 20.5h5"/><path d="M14 20.5h5"/></svg>`,
    grid: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="7" height="7" x="3" y="3" rx="1"/><rect width="7" height="7" x="14" y="3" rx="1"/><rect width="7" height="7" x="14" y="14" rx="1"/><rect width="7" height="7" x="3" y="14" rx="1"/></svg>`,
    kanban: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="18" x="3" y="3" rx="2"/><path d="M8 7v7"/><path d="M12 7v4"/><path d="M16 7v9"/></svg>`,
    play: `<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" stroke="none"><polygon points="7 4 20 12 7 20 7 4"/></svg>`,
    sun: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/></svg>`,
    moon: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/></svg>`,
    auto: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 3v18"/><path d="M12 8l5-3"/><path d="M12 13l6-3.5"/><path d="M12 18l5-3"/></svg>`,
    star: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l2.8 5.7 6.2.9-4.5 4.4 1.1 6.2L12 17.3l-5.6 2.9 1.1-6.2L3 9.6l6.2-.9L12 3Z"/></svg>`,
    starFilled: `<svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"><path d="M12 3l2.8 5.7 6.2.9-4.5 4.4 1.1 6.2L12 17.3l-5.6 2.9 1.1-6.2L3 9.6l6.2-.9L12 3Z"/></svg>`,
    trash: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12"/><path d="M9 7V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v3"/></svg>`,
    chevronDown: `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round"><path d="m7 10 5 5 5-5"/></svg>`,
    plus: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14"/><path d="M5 12h14"/></svg>`,
    dice: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="18" x="3" y="3" rx="3" ry="3"/><circle cx="8.5" cy="8.5" r="1.2" fill="currentColor"/><circle cx="15.5" cy="8.5" r="1.2" fill="currentColor"/><circle cx="12" cy="12" r="1.2" fill="currentColor"/><circle cx="8.5" cy="15.5" r="1.2" fill="currentColor"/><circle cx="15.5" cy="15.5" r="1.2" fill="currentColor"/></svg>`,
    edit: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>`,
  };

  function withViewTransition(fn) {
    const canAnimate =
      typeof document.startViewTransition === "function" &&
      window.innerWidth > 820 &&
      !(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
    if (canAnimate) {
      try {
        document.startViewTransition(() => fn());
        return;
      } catch {}
    }
    fn();
  }

  function hydrateIcons(root = document) {
    root.querySelectorAll("[data-icon]").forEach((el) => {
      const key = el.dataset.icon;
      if (UI_ICONS[key]) {
        el.innerHTML = UI_ICONS[key];
      }
    });
  }

  function haptic(type = "light") {
    try {
      if (tg && tg.HapticFeedback) {
        if (type === "selection") {
          tg.HapticFeedback.selectionChanged();
        } else {
          tg.HapticFeedback.impactOccurred(type);
        }
      }
    } catch {}
  }

  const savedThemeMode = localStorage.getItem("sb_theme_mode");
  const savedViewMode = localStorage.getItem("sb_view_mode");
  const VALID_VIEW_MODES = ["list", "posters", "cards", "kanban"];
  const DEFAULT_VIEW_BY_TAB = {
    "": VALID_VIEW_MODES.includes(savedViewMode) ? savedViewMode : "list",
    movies: "posters",
    books: "posters",
    video: "cards",
    article: "list",
    ideas: "list",
  };

  let viewModesByTab = {};
  try {
    const rawMap = localStorage.getItem("sb_view_modes_by_tab_v1");
    if (rawMap) {
      const parsedMap = JSON.parse(rawMap);
      if (parsedMap && typeof parsedMap === "object") {
        viewModesByTab = parsedMap;
      }
    }
  } catch {}

  function getViewModeForTab(tabKey) {
    const k = tabKey || "";
    const stored = viewModesByTab[k];
    if (VALID_VIEW_MODES.includes(stored)) return stored;
    return DEFAULT_VIEW_BY_TAB[k] || "list";
  }

  function saveViewModeForTab(tabKey, mode) {
    const k = tabKey || "";
    viewModesByTab[k] = mode;
    try {
      const encoded = JSON.stringify(viewModesByTab);
      localStorage.setItem("sb_view_modes_by_tab_v1", encoded);
      if (k === "") localStorage.setItem("sb_view_mode", mode);
      saveCloudPref("sb_view_modes_by_tab_v1", encoded);
    } catch {}
  }

  const SMART_VIEWS_META = {
    top_planned: {
      label: "🔥 Топ к просмотру",
      desc: "Входящие и запланированные с рейтингом от 7.5 (книги от 4.0)",
    },
    favorites: {
      label: "⭐ Любимое (8+)",
      desc: "Записи с вашей оценкой 8 и выше",
    },
    noted: {
      label: "✍️ С заметками",
      desc: "Записи с вашими личными заметками",
    },
    unrated_done: {
      label: "🎯 Готово без оценки",
      desc: "Завершённые записи, которым ещё не выставлена оценка",
    },
    attention: {
      label: "⚠️ Требуют внимания",
      desc: "Записи с ошибками или неполным обогащением",
    },
  };

  const state = {
    view: "catalog",
    viewMode: getViewModeForTab(""),
    themeMode: ["auto", "light", "dark"].includes(savedThemeMode)
      ? savedThemeMode
      : tg && tg.colorScheme
      ? "auto"
      : "light",
    tab: "",
    smart: "",
    status: "all",
    tags: [],
    q: "",
    sort: "created",
    items: [],
    itemsTotal: 0,
    hasMoreItems: false,
    loadingMoreItems: false,
    originals: [],
    allTags: [],
    tgChatId: 0,
    drawerItemId: null,
    externalDrawerItem: null,
    drawerConfirmDelete: false,
    drawerEditMode: false,
    drawerAddTagMode: false,
    statusPopoverItemId: null,
    ratingPopoverItemId: null,
    filtersSheetOpen: false,
    quickAddOpen: false,
    cmdPaletteOpen: false,
    shortcutsOpen: false,
    triageMode: false,
    triageQueue: [],
    triageTotal: 0,
    triageProcessed: 0,
    triageCompletedView: false,
    luckyMode: false,
    luckySeenIds: new Set(),
    focusedIndex: -1,
    statsData: null,
    statsYear: "",
    selectedIds: new Set(),
    lastSelectedId: null,
    bulkDeleteConfirm: false,
    bulkTagOpen: false,
    statusCountsByTab: {},
    expandedTagIds: new Set(),
  };

  function findDrawerItem(itemId) {
    const numId = Number(itemId);
    const inList = state.items.find((i) => Number(i.id) === numId);
    if (inList) return inList;
    if (state.externalDrawerItem && Number(state.externalDrawerItem.id) === numId) {
      return state.externalDrawerItem;
    }
    return null;
  }

  function syncStateToUrl({ push = false } = {}) {
    try {
      const params = new URLSearchParams();
      if (state.view && state.view !== "catalog") params.set("view", state.view);
      if (state.view === "stats" && state.statsYear) {
        params.set("year", String(state.statsYear));
      } else {
        if (state.tab) params.set("tab", state.tab);
        if (state.smart) params.set("smart", state.smart);
        if (state.status && state.status !== "all") params.set("status", state.status);
        if (state.tags.length) params.set("tags", state.tags.join(","));
        if (state.q) params.set("q", state.q);
        if (state.sort && state.sort !== "created") params.set("sort", state.sort);
      }
      if (state.drawerItemId !== null && !state.triageCompletedView) {
        params.set("item", String(state.drawerItemId));
      }
      const qs = params.toString();
      const nextUrl = window.location.pathname + (qs ? `?${qs}` : "") + window.location.hash;
      const curUrl = window.location.pathname + window.location.search + window.location.hash;
      if (nextUrl === curUrl) return;
      if (push) {
        window.history.pushState({ sb: true }, "", nextUrl);
      } else {
        window.history.replaceState({ sb: true }, "", nextUrl);
      }
    } catch {}
  }

  function restoreStateFromUrl() {
    try {
      const p = new URLSearchParams(window.location.search);
      const viewP = p.get("view");
      state.view = viewP === "originals" ? "originals" : viewP === "stats" ? "stats" : "catalog";
      const yearP = p.get("year") || "";
      state.statsYear = /^\d{4}$/.test(yearP) ? yearP : "";
      state.tab = p.get("tab") || "";
      const smartP = p.get("smart") || "";
      state.smart = SMART_VIEWS_META[smartP] ? smartP : "";
      const stP = p.get("status") || "all";
      state.status = ["all", "inbox", "planned", "in_progress", "done", "dropped"].includes(stP) ? stP : "all";
      const rawTags = p.get("tags") || p.get("tag") || "";
      state.tags = rawTags
        ? [...new Set(rawTags.split(",").map((t) => t.trim().replace(/^#+/, "").toLowerCase()).filter(Boolean))]
        : [];
      state.q = (p.get("q") || "").trim();
      const sortP = p.get("sort") || "created";
      state.sort = ["created", "updated", "imdb", "kp", "rt", "user", "year", "title"].includes(sortP)
        ? sortP
        : "created";
      const modeP = p.get("mode") || "";
      state.viewMode = VALID_VIEW_MODES.includes(modeP) ? modeP : getViewModeForTab(state.tab);

      const sInp = document.getElementById("searchInput");
      if (sInp) sInp.value = state.q;
      const dSort = document.getElementById("sortSelect");
      if (dSort) dSort.value = state.sort;
      const mSort = document.getElementById("mobileSortSelect");
      if (mSort) mSort.value = state.sort;

      const itemP = p.get("item");
      const itemId = itemP && /^\d+$/.test(itemP) ? Number(itemP) : null;
      return itemId;
    } catch {
      return null;
    }
  }

  let itemsAbort = null;
  let tagsAbort = null;
  let originalsAbort = null;
  let statsAbort = null;

  const STATUS_META = {
    inbox: {
      label: "Входящие",
      short: "Входящие",
      dot: "#64748b",
      svg: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12h4l2 3h6l2-3h4"/><path d="M5.5 5.5A2.5 2.5 0 0 1 7.7 4h8.6a2.5 2.5 0 0 1 2.2 1.5L21 12v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-6l2.5-6.5Z"/></svg>`,
    },
    planned: {
      label: "В планах",
      short: "В планах",
      dot: "#2563eb",
      svg: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21l-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>`,
    },
    in_progress: {
      label: "В процессе",
      short: "В процессе",
      dot: "#d97706",
      svg: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><polygon points="10 8.5 16 12 10 15.5 10 8.5" fill="currentColor" stroke="none"/></svg>`,
    },
    done: {
      label: "Готово",
      short: "Готово",
      dot: "#059669",
      svg: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="m8.5 12.2 2.3 2.3 4.7-4.7"/></svg>`,
    },
    dropped: {
      label: "Брошено",
      short: "Брошено",
      dot: "#dc2626",
      svg: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="m9.5 9.5 5 5M14.5 9.5l-5 5"/></svg>`,
    },
  };

  const TOPIC_LABELS = {
    movies: "🎬 Кино и сериалы",
    books: "📚 Книги",
    video: "▶️ YouTube",
    article: "📰 Статьи",
    ideas: "💡 Идеи и посты",
  };

  const CATEGORY_EMOJI = {
    movie: "🎬",
    series: "📺",
    book: "📚",
    video: "▶️",
    article: "📰",
    post: "💬",
    idea: "💡",
  };

  const CATEGORY_TITLES = {
    movie: "🎬 Фильм",
    series: "📺 Сериал",
    book: "📚 Книга",
    video: "▶️ YouTube",
    article: "📰 Статья",
    post: "💬 Пост",
    idea: "💡 Идея",
  };

  // ==================== ТЕМА: СВЕТЛАЯ / ТЁМНАЯ + TG-ТЕМА ====================

  function resolveEffectiveTheme() {
    if (state.themeMode === "dark") return "dark";
    if (state.themeMode === "light") return "light";
    if (tg && tg.colorScheme) {
      return tg.colorScheme === "dark" ? "dark" : "light";
    }
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  function applyTheme() {
    const effective = resolveEffectiveTheme();
    document.documentElement.setAttribute("data-theme", effective);

    const iconKey =
      state.themeMode === "auto" ? "auto" : effective === "dark" ? "moon" : "sun";
    const labelText =
      state.themeMode === "auto"
        ? `Авто (${effective === "dark" ? "TG 🌙" : "TG ☀️"})`
        : effective === "dark"
        ? "Чернила"
        : "Бумага";

    const deskIcon = document.getElementById("themeIconDesktop");
    const deskLabel = document.getElementById("themeLabelDesktop");
    if (deskIcon) deskIcon.innerHTML = UI_ICONS[iconKey];
    if (deskLabel) deskLabel.textContent = labelText;

    const metaTheme = document.getElementById("metaThemeColor");
    if (metaTheme) {
      metaTheme.setAttribute("content", effective === "dark" ? "#171513" : "#fbf8f3");
    }

    if (tg) {
      const bgHex = effective === "dark" ? "#171513" : "#fbf8f3";
      try {
        if (typeof tg.setHeaderColor === "function") tg.setHeaderColor(bgHex);
        if (typeof tg.setBackgroundColor === "function") tg.setBackgroundColor(bgHex);
      } catch {}
    }
  }

  function setThemeMode(mode) {
    if (!["auto", "light", "dark"].includes(mode)) return;
    state.themeMode = mode;
    localStorage.setItem("sb_theme_mode", state.themeMode);
    saveCloudPref("sb_theme_mode", state.themeMode);
    applyTheme();
    if (state.filtersSheetOpen) {
      renderFiltersSheet();
    }
    haptic("selection");
  }

  function cycleThemeMode() {
    if (tg && tg.colorScheme) {
      const order = ["auto", "light", "dark"];
      state.themeMode = order[(order.indexOf(state.themeMode) + 1) % order.length];
    } else {
      state.themeMode = resolveEffectiveTheme() === "dark" ? "light" : "dark";
    }
    localStorage.setItem("sb_theme_mode", state.themeMode);
    saveCloudPref("sb_theme_mode", state.themeMode);
    applyTheme();
    if (state.filtersSheetOpen) {
      renderFiltersSheet();
    }
    haptic("selection");
  }

  if (tg && typeof tg.onEvent === "function") {
    try {
      tg.onEvent("themeChanged", () => {
        if (state.themeMode === "auto") {
          applyTheme();
          if (state.filtersSheetOpen) {
            renderFiltersSheet();
          }
        }
      });
    } catch {}
  }

  // ==================== АВТОРИЗАЦИЯ И ЗАГОЛОВКИ ====================

  function authHeaders() {
    const headers = { "Content-Type": "application/json" };
    if (tg && tg.initData) {
      headers["Authorization"] = `tma ${tg.initData}`;
    } else {
      const key = getAccessKey();
      if (key) {
        headers["X-Access-Key"] = key;
      }
    }
    return headers;
  }

  const authModal = document.getElementById("authModal");
  const authForm = document.getElementById("authForm");
  const authUsernameInput = document.getElementById("authUsernameInput");
  const authPasswordInput = document.getElementById("authPasswordInput");
  const authErrorMsg = document.getElementById("authErrorMsg");
  const authDescText = document.getElementById("authDescText");
  const logoutBtns = [
    document.getElementById("logoutBtnDesktop"),
    document.getElementById("logoutBtnMobile"),
  ].filter(Boolean);

  logoutBtns.forEach((btn) => {
    if (isTgWebApp) {
      btn.classList.add("hidden");
    } else {
      btn.addEventListener("click", async () => {
        localStorage.removeItem("sb_access_key");
        localStorage.removeItem("sb_cache_items_v1");
        localStorage.removeItem("sb_cache_tags_v1");
        try {
          await fetch("/api/logout", { method: "POST" });
        } catch {}
        state.items = [];
        state.originals = [];
        closeDetailDrawer();
        renderCatalog();
        showAuthModal(false);
      });
    }
  });

  if (!isTgWebApp && !getAccessKey()) {
    setTimeout(() => {
      showAuthModal(false);
    }, 10);
  }

  function showAuthModal(isForbiddenTelegram = false) {
    if (!authModal) return;
    authModal.classList.remove("hidden");
    if (isForbiddenTelegram) {
      if (authDescText) {
        authDescText.textContent = "Доступ запрещён: ваш Telegram-аккаунт не авторизован для этой базы.";
      }
      if (authForm) authForm.classList.add("hidden");
    } else {
      if (authForm) authForm.classList.remove("hidden");
      if (authPasswordInput) {
        authPasswordInput.value = "";
        setTimeout(() => authPasswordInput.focus(), 50);
      }
    }
  }

  function consumePendingShareTarget() {
    if (!pendingShareText) return;
    const shared = pendingShareText;
    pendingShareText = "";
    openQuickAddModal({ prefillText: shared });
  }

  function hideAuthModal() {
    if (authModal) authModal.classList.add("hidden");
    if (authErrorMsg) authErrorMsg.classList.add("hidden");
    consumePendingShareTarget();
  }

  if (authForm) {
    authForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const username = (authUsernameInput ? authUsernameInput.value : "admin").trim();
      const password = (authPasswordInput ? authPasswordInput.value : "").trim();
      if (!password) return;

      if (authErrorMsg) authErrorMsg.classList.add("hidden");

      try {
        const res = await fetch("/api/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username, password }),
        });

        if (!res.ok) {
          if (authErrorMsg) {
            authErrorMsg.textContent = "Неверный логин или пароль. Попробуйте снова.";
            authErrorMsg.classList.remove("hidden");
          }
          return;
        }

        const data = await res.json();
        const token = data.token || password;
        localStorage.setItem("sb_access_key", token);
        hideAuthModal();
        refreshCurrentView();
      } catch {
        if (authErrorMsg) {
          authErrorMsg.textContent = "Ошибка сети или сервера. Попробуйте снова.";
          authErrorMsg.classList.remove("hidden");
        }
      }
    });
  }

  // ==================== УТИЛИТЫ И РЕЙТИНГИ ====================

  function parseMeta(raw) {
    if (!raw) return {};
    if (typeof raw === "object") return raw;
    try {
      return JSON.parse(raw);
    } catch {
      return {};
    }
  }

  function badgeTone(score, scale = 10) {
    if (score == null) return "";
    const normalized = scale === 5 ? score * 2 : scale === 100 ? score / 10 : score;
    if (normalized >= 7.5) return "high";
    if (normalized >= 6.0) return "mid";
    return "";
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str || "";
    return div.innerHTML;
  }

  function linkifyText(str) {
    const escaped = escapeHtml(str || "");
    return escaped.replace(
      /(https?:\/\/[^\s<]+)/gi,
      (url) => `<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>`
    );
  }

  const SVC_ICONS = {
    threads: `<svg class="svc-svg" viewBox="0 0 192 192" width="13" height="13" fill="currentColor"><path d="M141.537 88.9883C140.71 88.5919 139.87 88.2104 139.019 87.8451C137.537 60.5382 122.616 44.905 97.5619 44.745C97.4184 44.7443 97.2748 44.7443 97.1313 44.745C75.8062 44.745 59.4975 58.115 54.4363 79.475C49.375 100.835 56.685 125.145 74.0537 137.955C89.1762 149.11 110.126 150.315 125.753 141.455L120.436 129.565C108.575 136.295 92.4287 135.215 80.6975 126.565C67.6663 116.955 62.1587 97.975 66.1762 81.015C70.1937 64.055 82.5275 53.485 97.2287 53.485C115.111 53.605 125.961 65.615 127.166 88.295C124.717 89.475 122.137 90.725 119.431 92.055C102.774 100.225 84.7212 109.085 86.8537 127.835C87.9725 137.665 96.0825 145.415 106.004 145.415C116.541 145.415 126.136 138.445 131.789 129.745C136.529 138.515 143.725 143.265 152.923 143.265C166.456 143.265 177.346 132.375 177.346 118.842C177.346 95.845 159.957 88.025 141.537 88.9883ZM120.916 117.815C117.476 123.965 111.451 127.675 104.931 127.675C99.8825 127.675 95.8362 124.085 95.3425 119.745C94.2787 110.375 104.382 104.935 118.736 97.895C120.479 97.039 122.203 96.1983 123.904 95.3725C124.496 103.585 123.496 113.205 120.916 117.815Z"/></svg>`,
    youtube: `<svg class="svc-svg" viewBox="0 0 24 24" width="14" height="14" fill="#ef4444"><path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/></svg>`,
    instagram: `<svg class="svc-svg" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="#e1306c" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="20" rx="5" ry="5"></rect><path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z"></path><line x1="17.5" y1="6.5" x2="17.51" y2="6.5"></line></svg>`,
    telegram: `<svg class="svc-svg" viewBox="0 0 24 24" width="13" height="13" fill="#0284c7"><path d="m20.665 3.717-17.73 6.837c-1.21.486-1.203 1.161-.222 1.462l4.552 1.42 10.532-6.645c.498-.303.953-.14.579.192l-8.533 7.701h-.002l-.313 4.673c.46 0 .663-.211.921-.46l2.211-2.15 4.599 3.397c.848.467 1.457.227 1.668-.785l3.019-14.228c.309-1.239-.473-1.8-1.282-1.414z"/></svg>`,
    x: `<svg class="svc-svg" viewBox="0 0 24 24" width="12" height="12" fill="currentColor"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>`,
    reddit: `<svg class="svc-svg" viewBox="0 0 24 24" width="13" height="13" fill="#ea580c"><circle cx="12" cy="12" r="10"/><path fill="#fff" d="M17 11.5a1.5 1.5 0 0 0-2.5-1.1c-.8-.5-1.8-.8-3-.9l.5-2.5 2 .4a1 1 0 1 0 .2-.7l-2.4-.5a.5.5 0 0 0-.6.4l-.7 3.2c-1.1.1-2.2.4-3 .9A1.5 1.5 0 0 0 5 11.5c0 .6.3 1.1.8 1.3 0 .2 0 .4 0 .7 0 2.2 2.7 4 6 4s6-1.8 6-4c0-.3 0-.5 0-.7.5-.2.8-.7.8-1.3zM9 11.5a1 1 0 1 1 2 0 1 1 0 0 1-2 0zm5.8 3.3c-.6.6-1.7.7-2.8.7s-2.2-.1-2.8-.7a.3.3 0 0 1 .4-.4c.5.5 1.4.6 2.4.6s1.9-.1 2.4-.6a.3.3 0 0 1 .4.4zm.2-2.3a1 1 0 1 1 0-2 1 1 0 0 1 0 2z"/></svg>`,
    github: `<svg class="svc-svg" viewBox="0 0 24 24" width="13" height="13" fill="currentColor"><path fill-rule="evenodd" clip-rule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"/></svg>`,
    tiktok: `<svg class="svc-svg" viewBox="0 0 24 24" width="13" height="13" fill="currentColor"><path d="M19.589 6.686a4.793 4.793 0 0 1-3.77-4.245V2h-3.445v13.672a2.896 2.896 0 0 1-2.883 2.87 2.896 2.896 0 0 1-2.884-2.87 2.896 2.896 0 0 1 2.884-2.87c.29 0 .57.042.836.12v-3.52a6.376 6.376 0 0 0-.836-.056C5.932 9.436 3 12.38 3 16.012c0 3.633 2.932 6.578 6.547 6.578 3.616 0 6.548-2.945 6.548-6.578V9.167a8.21 8.21 0 0 0 4.887 1.583v-3.44a4.83 4.83 0 0 1-1.393-.624z"/></svg>`,
    globe: `<svg class="svc-svg" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="2" y1="12" x2="22" y2="12"></line><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path></svg>`,
  };

  function resolveSourceVisual(url) {
    if (!url) return null;
    let domain = "";
    try {
      const u = new URL(url);
      domain = u.hostname.toLowerCase().replace(/^www\./, "");
    } catch {
      domain = "";
    }

    let iconHtml = SVC_ICONS.globe;
    let label = domain || "Ссылка";

    if (domain.includes("threads.net") || domain.includes("threads.com")) {
      iconHtml = SVC_ICONS.threads;
      label = "Threads";
    } else if (domain.includes("youtube.com") || domain.includes("youtu.be")) {
      iconHtml = SVC_ICONS.youtube;
      label = "YouTube";
    } else if (domain.includes("instagram.com") || domain.includes("instagr.am")) {
      iconHtml = SVC_ICONS.instagram;
      label = "Instagram";
    } else if (domain.includes("t.me") || domain.includes("telegram.me") || domain.includes("telegram.org")) {
      iconHtml = SVC_ICONS.telegram;
      label = "Telegram";
    } else if (domain.includes("twitter.com") || domain.includes("x.com")) {
      iconHtml = SVC_ICONS.x;
      label = "X";
    } else if (domain.includes("reddit.com") || domain.includes("redd.it")) {
      iconHtml = SVC_ICONS.reddit;
      label = "Reddit";
    } else if (domain.includes("github.com")) {
      iconHtml = SVC_ICONS.github;
      label = "GitHub";
    } else if (domain.includes("tiktok.com")) {
      iconHtml = SVC_ICONS.tiktok;
      label = "TikTok";
    } else if (domain.includes("medium.com")) {
      iconHtml = `<span style="font-weight:800;font-size:12px;">M</span>`;
      label = "Medium";
    } else if (domain.includes("wikipedia.org")) {
      iconHtml = SVC_ICONS.globe;
      label = "Википедия";
    }

    return {
      iconHtml,
      label,
      safeUrl: escapeHtml(url),
      safeLabel: escapeHtml(label),
    };
  }

  function buildSourceBadgeHtml(url, index = null) {
    const visual = resolveSourceVisual(url);
    if (!visual) return "";
    const labelText = index != null ? `${visual.safeLabel} ${index}` : visual.safeLabel;
    return `<a class="rating-badge source-badge" href="${visual.safeUrl}" target="_blank" rel="noopener noreferrer" title="${labelText}: ${visual.safeUrl}">${visual.iconHtml}<span>${labelText}</span></a>`;
  }

  function getPrimarySourceUrl(item) {
    const sources = item.sources || [];
    const firstWithUrl = sources.find((s) => s.source_url);
    return (firstWithUrl && firstWithUrl.source_url) || item.canonical_url || "";
  }

  function buildCornerSourceHtml(item) {
    const visual = resolveSourceVisual(getPrimarySourceUrl(item));
    if (!visual) return "";
    return `<a class="liquid-pill corner-source-pill" href="${visual.safeUrl}" target="_blank" rel="noopener noreferrer" title="${visual.safeLabel}: ${visual.safeUrl}" aria-label="${visual.safeLabel}">${visual.iconHtml}<svg class="corner-ext-arrow" width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 11 11 5M6 5h5v5"/></svg></a>`;
  }

  const BRAND_BADGES = {
    imdb: `<span class="brand-imdb">IMDb</span>`,
    kp: `<span class="brand-kp">К</span>`,
    tmdb: `<span class="brand-tmdb">TMDB</span>`,
    rt: `<span class="brand-rt"><svg width="10" height="10" viewBox="0 0 16 16" fill="none"><path d="M8 2.2v3.6M5.2 3.8 8 5.8l2.8-2" stroke="#86EFAC" stroke-width="2" stroke-linecap="round"/><circle cx="8" cy="10.2" r="4.2" fill="#fff" fill-opacity="0.22"/></svg></span>`,
    fantlab: `<span class="brand-fl">FL</span>`,
    goodreads: `<span class="brand-gr">g</span>`,
    wiki: `<span class="brand-wiki">W</span>`,
  };

  function buildRatingsHtml(item, { compact = false, includeSources = true } = {}) {
    const meta = parseMeta(item.meta);
    const badges = [];

    if (item.category === "book") {
      const rFl = meta.rating_fantlab ?? item.rating_kp;
      const uFl = meta.url_fantlab || "#";
      if (rFl != null || meta.url_fantlab) {
        const flVal = rFl != null ? `<span>${rFl}</span>` : "";
        badges.push(
          `<a class="rating-badge ${badgeTone(rFl, 10)}" href="${uFl}" target="_blank" rel="noopener noreferrer">${BRAND_BADGES.fantlab}${flVal}</a>`
        );
      }
      const rGr = meta.rating_goodreads ?? item.rating_imdb;
      const uGr = meta.url_goodreads || "#";
      if (rGr != null || meta.url_goodreads) {
        const grVal = rGr != null ? `<span>${rGr}</span>` : "";
        badges.push(
          `<a class="rating-badge ${badgeTone(rGr, 5)}" href="${uGr}" target="_blank" rel="noopener noreferrer">${BRAND_BADGES.goodreads}${grVal}</a>`
        );
      }
      if (meta.info_link) {
        badges.push(`<a class="rating-badge" href="${meta.info_link}" target="_blank" rel="noopener noreferrer">${BRAND_BADGES.wiki}<span>Вики</span></a>`);
      }
    } else if (item.category === "movie" || item.category === "series") {
      if (item.rating_imdb != null || item.imdb_id) {
        const url = item.imdb_id ? `https://www.imdb.com/title/${item.imdb_id}/` : "#";
        const val = item.rating_imdb != null ? `<span>${item.rating_imdb}</span>` : "";
        badges.push(
          `<a class="rating-badge ${badgeTone(item.rating_imdb, 10)}" href="${url}" target="_blank" rel="noopener noreferrer">${BRAND_BADGES.imdb}${val}</a>`
        );
      }
      const kpQuery = encodeURIComponent((item.title_ru || item.title_orig || "").trim());
      const kpUrl = item.kp_id
        ? `https://www.kinopoisk.ru/film/${item.kp_id}/`
        : kpQuery
        ? `https://www.kinopoisk.ru/index.php?kp_query=${kpQuery}`
        : "#";
      const kpVal = item.rating_kp != null ? `<span>${item.rating_kp}</span>` : "";
      badges.push(
        `<a class="rating-badge ${badgeTone(item.rating_kp, 10)}" href="${kpUrl}" target="_blank" rel="noopener noreferrer">${BRAND_BADGES.kp}${kpVal}</a>`
      );
      if (meta.rating_tmdb != null || meta.tmdb_id) {
        const tmdbType = item.category === "series" ? "tv" : "movie";
        const url = meta.tmdb_id ? `https://www.themoviedb.org/${tmdbType}/${meta.tmdb_id}` : "#";
        const tmdbVal = meta.rating_tmdb != null ? `<span>${meta.rating_tmdb}</span>` : "";
        badges.push(
          `<a class="rating-badge ${badgeTone(meta.rating_tmdb, 10)}" href="${url}" target="_blank" rel="noopener noreferrer">${BRAND_BADGES.tmdb}${tmdbVal}</a>`
        );
      }
      if (item.rating_rt != null || item.url_rt) {
        const url = item.url_rt || "#";
        const rtVal = item.rating_rt != null ? `<span>${item.rating_rt}%</span>` : "";
        badges.push(
          `<a class="rating-badge ${badgeTone(item.rating_rt, 100)}" href="${url}" target="_blank" rel="noopener noreferrer">${BRAND_BADGES.rt}${rtVal}</a>`
        );
      }
    }

    if (includeSources) {
      const sources = item.sources || [];
      const seenUrls = new Set();
      sources.forEach((s, idx) => {
        if (s.source_url && !seenUrls.has(s.source_url)) {
          seenUrls.add(s.source_url);
          if (!compact || seenUrls.size <= 1) {
            badges.push(buildSourceBadgeHtml(s.source_url, sources.length > 1 ? idx + 1 : null));
          }
        }
      });
      if (item.canonical_url && !seenUrls.has(item.canonical_url)) {
        seenUrls.add(item.canonical_url);
        if (!compact || seenUrls.size <= 1) {
          badges.push(buildSourceBadgeHtml(item.canonical_url, null));
        }
      }
    }

    return badges.join("");
  }

  function buildTelegramMessageLink(item) {
    if (!state.tgChatId || !item.tg_message_id) return "";
    const cleanChat = String(state.tgChatId).replace(/^-100/, "");
    const topicPart = item.tg_topic_id ? `${item.tg_topic_id}/` : "";
    return `https://t.me/c/${cleanChat}/${topicPart}${item.tg_message_id}`;
  }

  // ==================== APPLE LIQUID GLASS КНОПКИ (СТАТУС / ОЦЕНКА / В ЧАТЕ / УДАЛИТЬ) ====================

  const statusPopoverEl = document.getElementById("statusPopover");
  const ratingPopoverEl = document.getElementById("ratingPopover");

  let openSwipeWrap = null;
  let suppressSwipeClickUntil = 0;

  function closeOpenSwipeRow(exceptWrap = null) {
    if (!openSwipeWrap || openSwipeWrap === exceptWrap) return;
    const wrap = openSwipeWrap;
    openSwipeWrap = null;
    wrap.classList.remove("swipe-open-left", "swipe-open-right");
    const row = wrap.querySelector(".list-row");
    if (row) {
      row.classList.remove("swiping");
      row.style.transform = "";
    }
    wrap.querySelectorAll(".swipe-tray").forEach((tray) => {
      tray.classList.remove("visible", "interactive", "full-armed");
    });
  }

  function closeStatusPopover() {
    if (state.statusPopoverItemId === null) return;
    state.statusPopoverItemId = null;
    if (statusPopoverEl) {
      statusPopoverEl.classList.add("hidden");
      statusPopoverEl.innerHTML = "";
    }
    document.querySelectorAll(".liquid-status-btn.open").forEach((btn) => {
      btn.classList.remove("open");
      btn.setAttribute("aria-expanded", "false");
    });
  }

  function closeRatingPopover() {
    if (state.ratingPopoverItemId === null) return;
    state.ratingPopoverItemId = null;
    if (ratingPopoverEl) {
      ratingPopoverEl.classList.add("hidden");
      ratingPopoverEl.innerHTML = "";
    }
    document.querySelectorAll(".liquid-rating-btn.open").forEach((btn) => {
      btn.classList.remove("open");
      btn.setAttribute("aria-expanded", "false");
    });
  }

  function openStatusPopover(itemId, anchorBtn) {
    if (!statusPopoverEl) return;
    const numId = Number(itemId);
    if (state.statusPopoverItemId === numId) {
      closeStatusPopover();
      return;
    }

    const item = state.items.find((i) => Number(i.id) === numId);
    if (!item) return;

    closeRatingPopover();
    closeStatusPopover();
    state.statusPopoverItemId = numId;
    anchorBtn.classList.add("open");
    anchorBtn.setAttribute("aria-expanded", "true");

    statusPopoverEl.innerHTML = Object.entries(STATUS_META)
      .map(([key, meta]) => {
        const active = (item.status || "inbox") === key;
        return `
          <button type="button" class="lm-option ${active ? "active" : ""}" data-status-opt="${key}" data-id="${item.id}" role="option" aria-selected="${active ? "true" : "false"}">
            <span class="lm-ico" style="color:${meta.dot};">${meta.svg}</span>
            <span class="lm-label">${escapeHtml(meta.label)}</span>
            <span class="lm-check">${active ? "✓" : ""}</span>
          </button>
        `;
      })
      .join("");

    statusPopoverEl.classList.remove("hidden");

    const rect = anchorBtn.getBoundingClientRect();
    const popW = Math.max(rect.width, 168);
    statusPopoverEl.style.minWidth = `${Math.round(popW)}px`;
    const popH = statusPopoverEl.offsetHeight || 190;

    let left = rect.left;
    if (left + popW > window.innerWidth - 8) {
      left = Math.max(8, window.innerWidth - popW - 8);
    }

    let top = rect.bottom + 5;
    if (top + popH > window.innerHeight - 10) {
      top = Math.max(8, rect.top - popH - 5);
    }

    statusPopoverEl.style.left = `${Math.round(left)}px`;
    statusPopoverEl.style.top = `${Math.round(top)}px`;
    haptic("selection");
  }

  function openRatingPopover(itemId, anchorBtn) {
    if (!ratingPopoverEl) return;
    const numId = Number(itemId);
    if (state.ratingPopoverItemId === numId) {
      closeRatingPopover();
      return;
    }

    const item = state.items.find((i) => Number(i.id) === numId);
    if (!item) return;

    closeStatusPopover();
    closeRatingPopover();
    state.ratingPopoverItemId = numId;
    anchorBtn.classList.add("open");
    anchorBtn.setAttribute("aria-expanded", "true");

    const currentRating = Number(item.user_rating || 0);
    const resetBtnHtml = currentRating
      ? `<button type="button" class="rating-pop-reset" data-rating-opt="0" data-id="${item.id}">Сбросить</button>`
      : "";
    const numsHtml = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
      .map((r) => {
        const active = currentRating === r;
        return `<button type="button" class="rp-num-btn ${active ? "active" : ""}" data-rating-opt="${r}" data-id="${item.id}" role="option" aria-selected="${active ? "true" : "false"}">${r}</button>`;
      })
      .join("");

    ratingPopoverEl.innerHTML = `
      <div class="rating-pop-header">
        <span class="rating-pop-title">Моя оценка</span>
        ${resetBtnHtml}
      </div>
      <div class="rating-pop-grid">${numsHtml}</div>
    `;

    ratingPopoverEl.classList.remove("hidden");

    const rect = anchorBtn.getBoundingClientRect();
    const popW = Math.max(ratingPopoverEl.offsetWidth || 220, 220);
    const popH = ratingPopoverEl.offsetHeight || 125;

    let left = rect.left;
    if (left + popW > window.innerWidth - 8) {
      left = Math.max(8, window.innerWidth - popW - 8);
    }

    let top = rect.bottom + 5;
    if (top + popH > window.innerHeight - 10) {
      top = Math.max(8, rect.top - popH - 5);
    }

    ratingPopoverEl.style.left = `${Math.round(left)}px`;
    ratingPopoverEl.style.top = `${Math.round(top)}px`;
    haptic("selection");
  }

  if (statusPopoverEl) {
    statusPopoverEl.addEventListener("click", async (e) => {
      e.stopPropagation();
      const optBtn = e.target.closest("[data-status-opt]");
      if (!optBtn || !optBtn.dataset.id) return;
      const id = Number(optBtn.dataset.id);
      const nextStatus = optBtn.dataset.statusOpt;
      closeStatusPopover();
      await patchItem(id, { status: nextStatus });
    });
  }

  if (ratingPopoverEl) {
    ratingPopoverEl.addEventListener("click", async (e) => {
      e.stopPropagation();
      const optBtn = e.target.closest("[data-rating-opt]");
      if (!optBtn || !optBtn.dataset.id) return;
      const id = Number(optBtn.dataset.id);
      const rawVal = Number(optBtn.dataset.ratingOpt);
      const item = state.items.find((i) => Number(i.id) === id);
      const nextVal = item && Number(item.user_rating || 0) === rawVal && rawVal !== 0 ? 0 : rawVal;
      closeRatingPopover();
      await patchItem(id, { user_rating: nextVal });
      haptic("selection");
    });
  }

  function buildCardActionsHtml(item, variant = "") {
    const stMeta = STATUS_META[item.status] || STATUS_META.inbox;
    const isStatusOpen = state.statusPopoverItemId === Number(item.id);
    const isRatingOpen = state.ratingPopoverItemId === Number(item.id);

    const currentRating = Number(item.user_rating || 0);
    const ratingLabel = currentRating ? String(currentRating) : "Оценка";
    const includeDelete = variant !== "mobile-inline";

    const delBtnHtml = includeDelete
      ? `<span class="card-actions-right"><button type="button" class="liquid-pill liquid-delete-btn delete-btn" data-action="delete" data-id="${item.id}" title="Удалить запись" aria-label="Удалить запись">${UI_ICONS.trash}</button></span>`
      : "";
    const starIcon = currentRating ? UI_ICONS.starFilled : UI_ICONS.star;
    const cls = variant && variant !== "mobile-inline" ? `card-actions ${variant}` : "card-actions";

    return `
      <div class="${cls}">
        <button type="button" class="liquid-pill liquid-status-btn status-select ${isStatusOpen ? "open" : ""}" data-action="status-menu" data-id="${item.id}" aria-haspopup="listbox" aria-expanded="${isStatusOpen ? "true" : "false"}" aria-label="Статус">
          <span class="pill-st-ico" style="color:${stMeta.dot};">${stMeta.svg}</span>
          <span>${escapeHtml(stMeta.label)}</span>
          <span class="pill-st-chev">${UI_ICONS.chevronDown}</span>
        </button>
        <button type="button" class="liquid-pill liquid-rating-btn ${currentRating ? "has-rating" : ""} ${isRatingOpen ? "open" : ""}" data-action="rating-menu" data-id="${item.id}" aria-haspopup="listbox" aria-expanded="${isRatingOpen ? "true" : "false"}" aria-label="Моя оценка">
          <span class="pill-st-ico">${starIcon}</span>
          <span>${ratingLabel}</span>
          <span class="pill-st-chev">${UI_ICONS.chevronDown}</span>
        </button>
        ${delBtnHtml}
      </div>
    `;
  }

  // ==================== ДЕТАЛЬНАЯ ШТОРКА (DETAIL DRAWER) ====================

  const drawerOverlay = document.getElementById("detailDrawerOverlay");
  const drawerEl = document.getElementById("detailDrawer");
  const drawerBody = document.getElementById("drawerBody");
  const drawerCategoryLabel = document.getElementById("drawerCategoryLabel");
  const drawerPrevBtn = document.getElementById("drawerPrevBtn");
  const drawerNextBtn = document.getElementById("drawerNextBtn");
  const drawerLuckyAgainBtn = document.getElementById("drawerLuckyAgainBtn");
  const shortcutsOverlay = document.getElementById("shortcutsOverlay");
  const posterLightbox = document.getElementById("posterLightbox");
  const lightboxImg = document.getElementById("lightboxImg");

  function openPosterLightbox(url, alt = "") {
    if (!posterLightbox || !lightboxImg || !url) return;
    lightboxImg.src = url;
    lightboxImg.alt = alt;
    posterLightbox.classList.remove("hidden");
    posterLightbox.setAttribute("aria-hidden", "false");
    syncTelegramBackButton();
  }

  function closePosterLightbox() {
    if (!posterLightbox || posterLightbox.classList.contains("hidden")) return;
    posterLightbox.classList.add("hidden");
    posterLightbox.setAttribute("aria-hidden", "true");
    if (lightboxImg) lightboxImg.src = "";
    syncTelegramBackButton();
  }

  if (posterLightbox) {
    document.getElementById("lightboxCloseBtn").addEventListener("click", closePosterLightbox);
    posterLightbox.addEventListener("click", (e) => {
      if (e.target === posterLightbox) closePosterLightbox();
    });
  }

  function syncTelegramBackButton() {
    if (!tg || !tg.BackButton) return;
    try {
      const lightboxOpen = posterLightbox && !posterLightbox.classList.contains("hidden");
      if (
        lightboxOpen ||
        state.shortcutsOpen ||
        state.cmdPaletteOpen ||
        state.quickAddOpen ||
        state.drawerItemId !== null ||
        state.filtersSheetOpen
      ) {
        tg.BackButton.show();
      } else {
        tg.BackButton.hide();
      }
    } catch {}
  }

  if (tg && tg.BackButton) {
    try {
      tg.BackButton.onClick(() => {
        if (posterLightbox && !posterLightbox.classList.contains("hidden")) {
          closePosterLightbox();
        } else if (state.shortcutsOpen) {
          closeShortcutsModal();
        } else if (state.cmdPaletteOpen) {
          closeCmdPalette();
        } else if (state.quickAddOpen) {
          closeQuickAddModal();
        } else if (state.drawerItemId !== null) {
          closeDetailDrawer();
        } else if (state.filtersSheetOpen) {
          closeFiltersSheet();
        }
      });
    } catch {}
  }

  function extractYouTubeId(url) {
    if (!url) return "";
    const m = String(url).match(
      /(?:youtu\.be\/|youtube\.com\/(?:watch\?v=|shorts\/|embed\/|live\/))([a-zA-Z0-9_-]{11})/
    );
    return m ? m[1] : "";
  }

  let noteSaveTimer = null;
  let pendingNoteDraft = null;

  function formatAddedDate(isoStr) {
    if (!isoStr) return "";
    const raw = String(isoStr).trim();
    const normalized = raw.includes("T") ? raw : raw.replace(" ", "T") + "Z";
    const dt = new Date(normalized);
    if (Number.isNaN(dt.getTime())) return raw.slice(0, 10);
    try {
      return dt.toLocaleDateString("ru-RU", { day: "numeric", month: "short", year: "numeric" });
    } catch {
      return raw.slice(0, 10);
    }
  }

  function setNoteSaveIndicator(text, tone = "") {
    const el = document.getElementById("drawerNoteStatus");
    if (!el) return;
    el.textContent = text;
    el.className = `note-save-state${tone ? ` ${tone}` : ""}`;
  }

  async function flushPendingNoteSave(opts = {}) {
    clearTimeout(noteSaveTimer);
    noteSaveTimer = null;
    if (!pendingNoteDraft) return;
    const draft = pendingNoteDraft;
    pendingNoteDraft = null;
    setNoteSaveIndicator("Сохранение...");
    const ok = await patchItem(
      draft.itemId,
      { user_note: draft.value },
      { fromNoteAutosave: true, keepalive: Boolean(opts.keepalive) }
    );
    if (Number(state.drawerItemId) === Number(draft.itemId)) {
      setNoteSaveIndicator(ok ? "Сохранено ✓" : "Ошибка сохранения", ok ? "saved" : "error");
    }
  }

  function buildDrawerTagsInnerHtml(item) {
    const genresList = item.genres || [];
    const userTagsList = item.tags || [];
    const genrePills = genresList
      .map((g) => `<span class="genre-pill" data-drawer-tag="${escapeHtml(g)}">#${escapeHtml(g)}</span>`)
      .join("");
    const userTagPills = userTagsList
      .map(
        (t) =>
          `<span class="genre-pill" data-drawer-tag="${escapeHtml(t)}">#${escapeHtml(t)}<span class="tag-remove-x" data-remove-tag="${escapeHtml(t)}" title="Удалить тег">×</span></span>`
      )
      .join("");

    const datalistOpts = (state.allTags || [])
      .map((t) => `<option value="${escapeHtml(t.tag)}"></option>`)
      .join("");

    const tagAddFormHtml = state.drawerAddTagMode
      ? `
        <div class="drawer-tag-add-row">
          <input type="text" id="drawerNewTagInput" class="drawer-edit-input drawer-tag-input" list="drawerTagsDatalist" placeholder="Новый тег..." autocomplete="off" />
          <datalist id="drawerTagsDatalist">${datalistOpts}</datalist>
          <button type="button" class="liquid-pill drawer-save-note-btn" data-drawer-add-tag-submit="${item.id}">OK</button>
        </div>
      `
      : "";

    return `
      <div class="drawer-section-title">Жанры и теги</div>
      <div class="genres-line">
        ${genrePills}
        ${userTagPills}
        <button type="button" class="genre-pill drawer-add-tag-pill" data-drawer-add-tag-toggle>+ Тег</button>
      </div>
      ${tagAddFormHtml}
    `;
  }

  function buildDrawerSummaryInnerHtml(item) {
    if (state.drawerEditMode) {
      return `
        <div class="drawer-section">
          <div class="drawer-section-title">Редактирование карточки</div>
          <input type="text" id="drawerEditTitleInput" class="drawer-edit-input" value="${escapeHtml(item.title_ru || "")}" placeholder="Название" />
          <textarea id="drawerEditSummaryInput" class="drawer-note-textarea" rows="4" placeholder="Описание...">${escapeHtml(item.summary || "")}</textarea>
          <div class="drawer-note-footer">
            <button type="button" class="confirm-cancel-btn" data-drawer-edit-cancel>Отмена</button>
            <button type="button" class="liquid-pill drawer-save-note-btn" data-drawer-edit-save="${item.id}">Сохранить</button>
          </div>
        </div>
      `;
    }
    if (item.summary) {
      return `
        <div class="drawer-section">
          <div class="drawer-section-title">Описание</div>
          <div class="drawer-summary">${linkifyText(item.summary)}</div>
        </div>
      `;
    }
    return "";
  }

  function isVideoItem(item) {
    return Boolean(item && (item.category || "").toLowerCase() === "video");
  }

  function isTextOnlyCategory(item) {
    if (!item) return false;
    const cat = (item.category || "").toLowerCase();
    return ["idea", "post", "article"].includes(cat) && !item.poster_url;
  }

  function buildItemDomainLabel(item) {
    const visual = resolveSourceVisual(getPrimarySourceUrl(item));
    return visual ? visual.label : "";
  }

  function getDrawerReaderText(item) {
    if (!item) return "";
    const sourceLongText = (item.sources || [])
      .map((s) => (s.raw_text || "").trim())
      .find((t) => t && !/^https?:\/\/\S+$/i.test(t) && t.length > (item.summary || "").trim().length + 40);
    return (item.extracted_text || "").trim() || sourceLongText || "";
  }

  function estimateReadingMinutes(text) {
    const clean = String(text || "").trim();
    if (!clean) return 0;
    const words = clean.split(/\s+/).filter(Boolean).length;
    if (words < 60) return 0;
    return Math.max(1, Math.round(words / 200));
  }

  function getPrimaryPosterScore(item) {
    if (!item) return null;
    if (item.user_rating) {
      return { text: `★ ${item.user_rating}`, isUser: true };
    }
    const meta = parseMeta(item.meta);
    if (item.category === "book") {
      const fl = meta.rating_fantlab ?? item.rating_kp;
      if (fl != null) return { text: `FL ${fl}`, isUser: false };
      const gr = meta.rating_goodreads ?? item.rating_imdb;
      if (gr != null) return { text: `g ${gr}`, isUser: false };
      return null;
    }
    if (item.rating_imdb != null) return { text: `IMDb ${item.rating_imdb}`, isUser: false };
    if (item.rating_kp != null) return { text: `КП ${item.rating_kp}`, isUser: false };
    if (meta.rating_tmdb != null) return { text: `TMDB ${meta.rating_tmdb}`, isUser: false };
    if (item.rating_rt != null) return { text: `${item.rating_rt}%`, isUser: false };
    return null;
  }

  function getSwipeRightActions(curStatus) {
    const st = curStatus || "inbox";
    if (st === "inbox") {
      return [
        { status: "planned", label: "В планах", tone: "st-tone-planned", svg: STATUS_META.planned.svg },
        { status: "done", label: "Готово", tone: "st-tone-done", svg: STATUS_META.done.svg },
      ];
    }
    if (st === "planned") {
      return [
        { status: "in_progress", label: "В процессе", tone: "st-tone-progress", svg: STATUS_META.in_progress.svg },
        { status: "done", label: "Готово", tone: "st-tone-done", svg: STATUS_META.done.svg },
      ];
    }
    if (st === "in_progress") {
      return [
        { status: "done", label: "Готово", tone: "st-tone-done", svg: STATUS_META.done.svg },
        { status: "planned", label: "В планах", tone: "st-tone-planned", svg: STATUS_META.planned.svg },
      ];
    }
    if (st === "done") {
      return [
        { status: "planned", label: "В планах", tone: "st-tone-planned", svg: STATUS_META.planned.svg },
        { status: "inbox", label: "Входящие", tone: "st-tone-inbox", svg: STATUS_META.inbox.svg },
      ];
    }
    return [
      { status: "planned", label: "В планах", tone: "st-tone-planned", svg: STATUS_META.planned.svg },
      { status: "done", label: "Готово", tone: "st-tone-done", svg: STATUS_META.done.svg },
    ];
  }

  function buildDrawerReaderHtml(item) {
    const fullReaderText = getDrawerReaderText(item);
    if (!fullReaderText) return "";
    return `
      <details class="drawer-section drawer-reader-box">
        <summary class="drawer-reader-summary">
          <span>📖 Полный текст из источника</span>
          <span>▾</span>
        </summary>
        <div class="drawer-reader-content">${linkifyText(fullReaderText)}</div>
      </details>
    `;
  }

  function buildDrawerActionsFooterHtml(item) {
    const chatHtml = `<span></span>`;
    const deleteFooterHtml = state.drawerConfirmDelete
      ? `
        <div class="drawer-confirm-box">
          <span style="font-size:12.5px;color:var(--muted);">Удалить запись?</span>
          <button type="button" class="confirm-yes-btn" data-drawer-delete-confirm="${item.id}">Удалить</button>
          <button type="button" class="confirm-cancel-btn" data-drawer-delete-cancel>Отмена</button>
        </div>
      `
      : `<button type="button" class="drawer-delete-btn" data-drawer-delete-ask>${UI_ICONS.trash}<span>Удалить</span></button>`;
    return `${chatHtml}${deleteFooterHtml}`;
  }

  async function startInboxTriage() {
    closeStatusPopover();
    closeRatingPopover();
    closeOpenSwipeRow();
    state.smart = "";
    state.view = "catalog";
    state.status = "inbox";
    state.viewMode = getViewModeForTab(state.tab);
    syncNavigationState();
    syncStateToUrl({ push: true });
    await loadItems();
    const queue = state.items
      .filter((i) => (i.status || "inbox") === "inbox")
      .map((i) => Number(i.id));
    if (!queue.length) return;

    state.triageMode = true;
    state.triageQueue = queue;
    state.triageTotal = queue.length;
    state.triageProcessed = 0;
    state.triageCompletedView = false;
    state.luckyMode = false;
    openDetailDrawer(queue[0], { keepTriage: true });
  }

  function advanceInboxTriage({ processed = true, currentId = null } = {}) {
    if (!state.triageMode) return;
    if (currentId !== null) {
      const curNum = Number(currentId);
      state.triageQueue = state.triageQueue.filter((id) => Number(id) !== curNum);
    } else if (state.triageQueue.length) {
      state.triageQueue.shift();
    }
    if (processed) {
      state.triageProcessed += 1;
    }
    if (state.triageQueue.length > 0) {
      openDetailDrawer(state.triageQueue[0], { keepTriage: true, replaceUrl: true });
    } else {
      state.triageCompletedView = true;
      renderDetailDrawer();
      syncStateToUrl({ push: false });
      haptic("medium");
    }
  }

  function navigateDrawer(delta) {
    if (state.drawerItemId === null || !state.items.length) return;
    flushPendingNoteSave();
    const idx = state.items.findIndex((i) => Number(i.id) === Number(state.drawerItemId));
    if (idx === -1) return;
    const target = state.items[idx + delta];
    if (target) {
      openDetailDrawer(target.id, {
        keepTriage: state.triageMode,
        keepLucky: state.luckyMode,
        replaceUrl: true,
      });
    }
  }

  function syncDetailDrawerInPlace(item, opts = {}) {
    if (!item || state.drawerItemId === null) return;
    if (Number(drawerBody.dataset.renderedItemId) !== Number(item.id)) {
      renderDetailDrawer();
      return;
    }

    const titleEl = document.getElementById("drawerTitle");
    if (titleEl) {
      const yearStr = item.release_year ? ` (${item.release_year})` : "";
      titleEl.textContent = `${item.title_ru || ""}${yearStr}`;
    }

    const activeStatus = item.status || "inbox";
    drawerBody.querySelectorAll(".drawer-status-pill[data-drawer-status-btn]").forEach((btn) => {
      const isAct = btn.dataset.drawerStatusBtn === activeStatus;
      btn.classList.toggle("active", isAct);
      btn.setAttribute("aria-pressed", isAct ? "true" : "false");
    });

    const curRating = Number(item.user_rating || 0);
    drawerBody.querySelectorAll(".drawer-rate-btn[data-drawer-rate-btn]").forEach((btn) => {
      const n = Number(btn.dataset.drawerRateBtn);
      const isExact = curRating === n;
      const isFilled = curRating > 0 && n < curRating;
      btn.classList.toggle("active", isExact);
      btn.classList.toggle("filled", isFilled);
      btn.setAttribute("aria-pressed", isExact ? "true" : "false");
    });

    const ratingValEl = document.getElementById("drawerRatingValue");
    if (ratingValEl) {
      ratingValEl.textContent = curRating ? `★ ${curRating} / 10` : "Без оценки";
      ratingValEl.classList.toggle("has-rating", Boolean(curRating));
    }

    if (opts.syncSummary) {
      const summarySlot = document.getElementById("drawerSummarySlot");
      if (summarySlot) summarySlot.innerHTML = buildDrawerSummaryInnerHtml(item);
    }

    if (opts.syncTags) {
      const tagsSection = document.getElementById("drawerTagsSection");
      if (tagsSection) tagsSection.innerHTML = buildDrawerTagsInnerHtml(item);
    }

    if (!opts.skipNoteInput) {
      const noteInp = document.getElementById("drawerNoteInput");
      if (noteInp && document.activeElement !== noteInp) {
        noteInp.value = parseMeta(item.meta).user_note || "";
      }
    }
  }

  function renderDetailDrawer() {
    if (state.drawerItemId === null && !state.triageCompletedView) {
      drawerOverlay.classList.add("hidden");
      drawerOverlay.setAttribute("aria-hidden", "true");
      drawerBody.innerHTML = "";
      delete drawerBody.dataset.renderedItemId;
      if (drawerLuckyAgainBtn) drawerLuckyAgainBtn.classList.add("hidden");
      syncTelegramBackButton();
      return;
    }

    if (state.triageCompletedView) {
      drawerCategoryLabel.textContent = "Разбор входящих";
      if (drawerPrevBtn) drawerPrevBtn.disabled = true;
      if (drawerNextBtn) drawerNextBtn.disabled = true;
      if (drawerLuckyAgainBtn) drawerLuckyAgainBtn.classList.add("hidden");
      delete drawerBody.dataset.renderedItemId;
      drawerBody.innerHTML = `
        <div class="triage-done-card">
          <div class="triage-done-emoji">🎉</div>
          <h3>Все входящие разобраны!</h3>
          <p>Обработано записей: <b>${state.triageProcessed}</b>. Порядок наведён.</p>
          <button type="button" class="auth-submit-btn empty-cta-btn" data-triage-exit>Закрыть и вернуться</button>
        </div>
      `;
      drawerOverlay.classList.remove("hidden");
      drawerOverlay.setAttribute("aria-hidden", "false");
      syncTelegramBackButton();
      return;
    }

    const idx = state.items.findIndex((i) => Number(i.id) === Number(state.drawerItemId));
    const item = idx !== -1 ? state.items[idx] : findDrawerItem(state.drawerItemId);
    if (!item) {
      closeDetailDrawer();
      return;
    }

    if (drawerPrevBtn) drawerPrevBtn.disabled = idx <= 0;
    if (drawerNextBtn) drawerNextBtn.disabled = idx === -1 || idx >= state.items.length - 1;
    if (drawerLuckyAgainBtn) {
      drawerLuckyAgainBtn.classList.toggle("hidden", !(state.luckyMode && !state.triageMode));
    }

    const emoji = CATEGORY_EMOJI[item.category] || "📌";
    drawerCategoryLabel.textContent = CATEGORY_TITLES[item.category] || "Запись";

    const posterHtml = item.poster_url
      ? `<img src="${escapeHtml(item.poster_url)}" alt="${escapeHtml(item.title_ru || "")}" decoding="sync" data-lightbox-src="${escapeHtml(item.poster_url)}" />`
      : `<span>${emoji}</span>`;

    const yearStr = item.release_year ? ` (${item.release_year})` : "";
    const origLine =
      item.title_orig && item.title_orig.toLowerCase() !== (item.title_ru || "").toLowerCase()
        ? `<div class="drawer-orig">${escapeHtml(item.title_orig)}</div>`
        : "";

    const meta = parseMeta(item.meta);
    const subParts = [];
    if (shouldShowCreator(item)) subParts.push(`👤 ${escapeHtml(item.creator)}`);
    if (item.category === "series" && meta.seasons_count) {
      subParts.push(`📺 Сезонов: ${Number(meta.seasons_count)}`);
    }
    if (item.category === "book" && meta.page_count) {
      subParts.push(`📖 ${Number(meta.page_count)} стр.`);
    }
    let readTimeSpan = "";
    if (["article", "post"].includes(item.category)) {
      const domLabel = buildItemDomainLabel(item);
      if (domLabel) subParts.push(`🌐 ${escapeHtml(domLabel)}`);
      const readMin = estimateReadingMinutes(getDrawerReaderText(item));
      const readText = readMin ? `${subParts.length ? " · " : ""}⏱ ~${readMin} мин чтения` : "";
      readTimeSpan = `<span id="drawerReadTimeSlot">${readText}</span>`;
    }
    const creatorHtml =
      subParts.length || readTimeSpan
        ? `<div class="drawer-creator">${subParts.join(" · ")}${readTimeSpan}</div>`
        : "";
    const addedLabel = formatAddedDate(item.created_at);
    const addedDateHtml = addedLabel ? `<div class="drawer-date-meta">Добавлено ${escapeHtml(addedLabel)}</div>` : "";

    const ratingsHtml = buildRatingsHtml(item, { compact: false, includeSources: true });

    const tagsHtml = `<div class="drawer-section" id="drawerTagsSection">${buildDrawerTagsInnerHtml(item)}</div>`;
    const summaryEditHtml = `<div id="drawerSummarySlot">${buildDrawerSummaryInnerHtml(item)}</div>`;

    const userNote = meta.user_note || "";
    const noteSectionHtml = `
      <div class="drawer-section">
        <div class="drawer-note-head">
          <div class="drawer-section-title">✍️ Моя заметка</div>
          <span class="note-save-state" id="drawerNoteStatus"></span>
        </div>
        <textarea id="drawerNoteInput" class="drawer-note-textarea" rows="2" data-note-item-id="${item.id}" placeholder="Добавить личную заметку, кто посоветовал, мысли...">${escapeHtml(userNote)}</textarea>
      </div>
    `;

    const ytId = extractYouTubeId(getPrimarySourceUrl(item));
    const ytSectionHtml = ytId
      ? `
        <div class="drawer-section">
          ${
            item.poster_url
              ? `<button type="button" class="drawer-video-hero" data-play-yt="${escapeHtml(ytId)}" aria-label="Смотреть видео">
                  <img src="${escapeHtml(item.poster_url)}" alt="${escapeHtml(item.title_ru || "")}" />
                  <span class="poster-play-badge large">${UI_ICONS.play}</span>
                  <span class="drawer-video-hero-label">▶ Смотреть видео здесь</span>
                </button>`
              : `<button type="button" class="liquid-pill drawer-yt-btn" data-play-yt="${escapeHtml(ytId)}">▶️ Смотреть видео прямо здесь</button>`
          }
          <div id="drawerYtContainer"></div>
        </div>
      `
      : "";

    const readerHtml = `<div id="drawerReaderSlot">${buildDrawerReaderHtml(item)}</div>`;

    const activeStatus = item.status || "inbox";
    const statusPillsHtml = Object.entries(STATUS_META)
      .map(([k, v]) => {
        const active = activeStatus === k;
        return `<button type="button" class="drawer-status-pill ${active ? "active" : ""}" data-drawer-status-btn="${k}" data-id="${item.id}" aria-pressed="${active ? "true" : "false"}"><span style="display:inline-flex;color:${v.dot};">${v.svg}</span><span>${escapeHtml(v.label)}</span></button>`;
      })
      .join("");

    const curRating = Number(item.user_rating || 0);
    const ratingScaleHtml = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
      .map((n) => {
        const isExact = curRating === n;
        const isFilled = curRating > 0 && n < curRating;
        return `<button type="button" class="drawer-rate-btn ${isExact ? "active" : isFilled ? "filled" : ""}" data-drawer-rate-btn="${n}" data-id="${item.id}" aria-pressed="${isExact ? "true" : "false"}">${n}</button>`;
      })
      .join("");

    const triageBannerHtml = state.triageMode
      ? (() => {
          const total = Math.max(1, state.triageTotal);
          const curNum = Math.min(total, state.triageProcessed + 1);
          const pct = Math.min(100, Math.round((state.triageProcessed / total) * 100));
          return `
            <div class="drawer-triage-banner">
              <div class="triage-top-row">
                <span>⚡ Разбор входящих</span>
                <span>${curNum} из ${total}</span>
              </div>
              <div class="triage-progress-track">
                <div class="triage-progress-fill" style="width:${pct}%"></div>
              </div>
              <div class="triage-actions-row">
                <span class="triage-kbd-hint">1 Планы · 2 Процесс · 3 Готово · 4 Брошено · S Пропуск</span>
                <div class="triage-btns">
                  <button type="button" class="triage-mini-btn" data-triage-skip>Пропустить →</button>
                  <button type="button" class="triage-mini-btn" data-triage-exit>Выйти</button>
                </div>
              </div>
            </div>
          `;
        })()
      : "";

    drawerBody.dataset.renderedItemId = String(item.id);
    drawerBody.innerHTML = `
      ${triageBannerHtml}
      <div class="drawer-hero">
        <div class="drawer-poster">${posterHtml}</div>
        <div style="min-width:0;flex:1;">
          <div class="drawer-title-row">
            <h2 class="drawer-title" id="drawerTitle">${escapeHtml(item.title_ru)}${yearStr}</h2>
            <button type="button" class="icon-btn drawer-inline-edit-btn" data-drawer-edit-toggle title="Редактировать название и описание" aria-label="Редактировать">${UI_ICONS.edit}</button>
          </div>
          ${origLine}
          ${creatorHtml}
          ${addedDateHtml}
        </div>
      </div>

      ${ratingsHtml ? `<div class="ratings-bar">${ratingsHtml}</div>` : ""}
      ${ytSectionHtml}

      <div class="drawer-section">
        <div class="drawer-section-title">Статус</div>
        <div class="drawer-status-pills">${statusPillsHtml}</div>
      </div>

      <div class="drawer-section">
        <div class="drawer-rating-head">
          <div class="drawer-section-title">Моя оценка</div>
          <div class="drawer-rating-value ${curRating ? "has-rating" : ""}" id="drawerRatingValue">${curRating ? `★ ${curRating} / 10` : "Без оценки"}</div>
        </div>
        <div class="drawer-rating-scale">${ratingScaleHtml}</div>
      </div>

      ${summaryEditHtml}
      ${noteSectionHtml}
      ${readerHtml}
      ${tagsHtml}

      <div class="drawer-actions-footer" id="drawerActionsFooter">
        ${buildDrawerActionsFooterHtml(item)}
      </div>
    `;

    drawerOverlay.classList.remove("hidden");
    drawerOverlay.setAttribute("aria-hidden", "false");
    syncTelegramBackButton();
  }

  async function hydrateDrawerFullText(itemId) {
    const idNum = Number(itemId);
    const localItem = findDrawerItem(idNum);
    if (!localItem || localItem.extracted_text !== undefined) return;
    if (!["post", "article", "video", "idea"].includes(localItem.category)) return;
    try {
      const res = await fetch(`/api/items/${idNum}`, { headers: authHeaders() });
      if (!res.ok) return;
      const fresh = await res.json();
      const targetIdx = state.items.findIndex((i) => Number(i.id) === idNum);
      if (targetIdx !== -1) {
        state.items[targetIdx] = fresh;
      } else if (state.externalDrawerItem && Number(state.externalDrawerItem.id) === idNum) {
        state.externalDrawerItem = fresh;
      }
      if (Number(state.drawerItemId) === idNum && fresh.extracted_text) {
        const readerSlot = document.getElementById("drawerReaderSlot");
        if (readerSlot) {
          readerSlot.innerHTML = buildDrawerReaderHtml(fresh);
        }
        const readTimeSlot = document.getElementById("drawerReadTimeSlot");
        const readMin = estimateReadingMinutes(fresh.extracted_text);
        if (readTimeSlot && readMin) {
          const hasPrevText = Boolean(readTimeSlot.previousSibling && String(readTimeSlot.previousSibling.textContent || "").trim());
          readTimeSlot.textContent = `${hasPrevText ? " · " : ""}⏱ ~${readMin} мин чтения`;
        }
      }
    } catch {}
  }

  let activeHeroVtSeq = 0;

  function canRunHeroTransition() {
    return (
      typeof document.startViewTransition === "function" &&
      !(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches)
    );
  }

  function clearActiveHeroTransition(seq = null) {
    if (seq !== null && seq !== activeHeroVtSeq) return;
    document.documentElement.classList.remove("vt-drawer-active");
    document.querySelectorAll(".vt-source-card").forEach((el) => {
      el.classList.remove("vt-source-card");
    });
    document.querySelectorAll('[style*="view-transition-name"]').forEach((el) => {
      el.style.viewTransitionName = "";
    });
    if (state.drawerItemId === null && drawerOverlay) {
      drawerOverlay.classList.remove("vt-handled");
    }
  }

  function findCatalogPosterEl(itemId) {
    const grid = document.getElementById("catalogGrid");
    if (!grid || state.view !== "catalog") return null;
    const card = grid.querySelector(`[data-open-id="${Number(itemId)}"]`);
    if (!card) return null;
    const el = card.querySelector(
      ".poster-cover > img, .poster-box > img, .list-poster > img, .card-video-thumb > img, .kanban-poster > img"
    );
    if (!el || !el.complete || el.naturalWidth <= 0) return null;
    const r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0 || r.bottom <= 0 || r.top >= window.innerHeight) {
      return null;
    }
    return el;
  }

  function openDetailDrawer(itemId, opts = {}) {
    const {
      keepTriage = false,
      keepLucky = false,
      fallbackItem = null,
      skipUrlSync = false,
      replaceUrl = false,
      skipTransition = false,
    } = opts;
    const numId = Number(itemId);
    const wasClosed = state.drawerItemId === null;
    closeStatusPopover();
    closeRatingPopover();
    closeOpenSwipeRow();
    if (state.drawerItemId !== null && Number(state.drawerItemId) !== numId) {
      flushPendingNoteSave();
    }
    if (!keepTriage) {
      state.triageMode = false;
      state.triageCompletedView = false;
    }
    if (!keepLucky) {
      state.luckyMode = false;
    }
    if (fallbackItem && !state.items.some((i) => Number(i.id) === numId)) {
      state.externalDrawerItem = fallbackItem;
    }
    const sourcePoster = wasClosed && !skipTransition ? findCatalogPosterEl(numId) : null;
    state.drawerItemId = numId;
    state.drawerConfirmDelete = false;
    state.drawerEditMode = false;
    state.drawerAddTagMode = false;

    if (sourcePoster && canRunHeroTransition()) {
      const vtSeq = ++activeHeroVtSeq;
      clearActiveHeroTransition();
      const sourceCard = sourcePoster.closest(".poster-card, .item-card, .swipe-row-wrap");
      try {
        document.documentElement.classList.add("vt-drawer-active");
        if (drawerOverlay) drawerOverlay.classList.add("vt-handled");
        if (sourceCard) sourceCard.classList.add("vt-source-card");
        sourcePoster.style.viewTransitionName = "active-poster";
        const vt = document.startViewTransition(() => {
          sourcePoster.style.viewTransitionName = "";
          renderDetailDrawer();
          const dp = drawerBody ? drawerBody.querySelector(".drawer-poster > img") : null;
          if (dp) dp.style.viewTransitionName = "active-poster";
        });
        if (vt && vt.ready) vt.ready.catch(() => {});
        if (vt && vt.finished) {
          vt.finished.finally(() => clearActiveHeroTransition(vtSeq));
        } else {
          clearActiveHeroTransition(vtSeq);
        }
      } catch {
        clearActiveHeroTransition();
        if (drawerOverlay) drawerOverlay.classList.remove("vt-handled");
        renderDetailDrawer();
      }
    } else {
      if (wasClosed && drawerOverlay) drawerOverlay.classList.remove("vt-handled");
      renderDetailDrawer();
    }

    hydrateDrawerFullText(numId);
    if (!skipUrlSync) {
      syncStateToUrl({ push: wasClosed && !replaceUrl });
    }
    haptic("light");
  }

  async function openItemById(itemId, opts = {}) {
    const numId = Number(itemId);
    if (!numId) return;
    const existing = findDrawerItem(numId);
    if (existing) {
      openDetailDrawer(numId, opts);
      return;
    }
    try {
      const res = await fetch(`/api/items/${numId}`, { headers: authHeaders() });
      if (!res.ok) return;
      const item = await res.json();
      if (item && item.id) {
        openDetailDrawer(item.id, { ...opts, fallbackItem: item });
      }
    } catch {}
  }

  function closeDetailDrawer(opts = {}) {
    if (state.drawerItemId === null && !state.triageCompletedView) return;
    flushPendingNoteSave();
    const closingId = state.drawerItemId;
    const drawerPoster = !opts.skipTransition && drawerBody ? drawerBody.querySelector(".drawer-poster > img") : null;
    const targetPoster =
      !opts.skipTransition &&
      closingId !== null &&
      drawerPoster &&
      drawerPoster.complete &&
      drawerPoster.naturalWidth > 0
        ? findCatalogPosterEl(closingId)
        : null;

    state.drawerItemId = null;
    state.externalDrawerItem = null;
    state.drawerConfirmDelete = false;
    state.drawerEditMode = false;
    state.drawerAddTagMode = false;
    state.triageMode = false;
    state.triageCompletedView = false;
    state.luckyMode = false;

    if (drawerPoster && targetPoster && canRunHeroTransition()) {
      const vtSeq = ++activeHeroVtSeq;
      clearActiveHeroTransition();
      const targetCard = targetPoster.closest(".poster-card, .item-card, .swipe-row-wrap");
      try {
        document.documentElement.classList.add("vt-drawer-active");
        if (targetCard) targetCard.classList.add("vt-source-card");
        drawerPoster.style.viewTransitionName = "active-poster";
        const vt = document.startViewTransition(() => {
          renderDetailDrawer();
          targetPoster.style.viewTransitionName = "active-poster";
        });
        if (vt && vt.ready) vt.ready.catch(() => {});
        if (vt && vt.finished) {
          vt.finished.finally(() => clearActiveHeroTransition(vtSeq));
        } else {
          clearActiveHeroTransition(vtSeq);
        }
      } catch {
        clearActiveHeroTransition();
        renderDetailDrawer();
      }
    } else {
      clearActiveHeroTransition();
      renderDetailDrawer();
    }

    if (!opts.skipUrlSync) {
      syncStateToUrl({ push: false });
    }
  }

  document.getElementById("drawerCloseBtn").addEventListener("click", () => closeDetailDrawer());
  if (drawerLuckyAgainBtn) {
    drawerLuckyAgainBtn.addEventListener("click", () => pickRandomItem({ fromDrawer: true }));
  }
  if (drawerPrevBtn) drawerPrevBtn.addEventListener("click", () => navigateDrawer(-1));
  if (drawerNextBtn) drawerNextBtn.addEventListener("click", () => navigateDrawer(1));
  drawerOverlay.addEventListener("click", (e) => {
    if (e.target === drawerOverlay) closeDetailDrawer();
  });

  drawerBody.addEventListener("input", (e) => {
    if (e.target && e.target.id === "drawerNoteInput") {
      const inp = e.target;
      const id = Number(inp.dataset.noteItemId || state.drawerItemId);
      if (!id) return;
      pendingNoteDraft = { itemId: id, value: inp.value };
      setNoteSaveIndicator("Сохранение...");
      clearTimeout(noteSaveTimer);
      noteSaveTimer = setTimeout(() => {
        flushPendingNoteSave();
      }, 650);
    }
  });

  drawerBody.addEventListener("focusout", (e) => {
    if (e.target && e.target.id === "drawerNoteInput" && pendingNoteDraft) {
      flushPendingNoteSave();
    }
  });

  drawerBody.addEventListener("keydown", async (e) => {
    if (e.target && e.target.id === "drawerNewTagInput" && e.key === "Enter") {
      e.preventDefault();
      const submitBtn = drawerBody.querySelector("[data-drawer-add-tag-submit]");
      if (submitBtn) submitBtn.click();
    }
  });

  drawerBody.addEventListener("click", async (e) => {
    if (e.target.closest("[data-triage-skip]")) {
      advanceInboxTriage({ processed: false, currentId: state.drawerItemId });
      return;
    }

    if (e.target.closest("[data-triage-exit]")) {
      closeDetailDrawer();
      return;
    }

    const posterImg = e.target.closest("[data-lightbox-src]");
    if (posterImg) {
      openPosterLightbox(posterImg.dataset.lightboxSrc, posterImg.alt || "");
      return;
    }

    const ytBtn = e.target.closest("[data-play-yt]");
    if (ytBtn && ytBtn.dataset.playYt) {
      const ytBox = document.getElementById("drawerYtContainer");
      if (ytBox) {
        const vid = encodeURIComponent(ytBtn.dataset.playYt);
        ytBox.innerHTML = `<div class="drawer-yt-frame"><iframe src="https://www.youtube-nocookie.com/embed/${vid}?autoplay=1" allow="autoplay; encrypted-media; picture-in-picture" allowfullscreen></iframe></div>`;
        ytBtn.classList.add("hidden");
        haptic("light");
      }
      return;
    }

    const statusPill = e.target.closest("[data-drawer-status-btn]");
    if (statusPill && statusPill.dataset.id) {
      const id = Number(statusPill.dataset.id);
      const nextStatus = statusPill.dataset.drawerStatusBtn;
      haptic("selection");
      await patchItem(id, { status: nextStatus });
      if (state.triageMode && nextStatus !== "inbox") {
        advanceInboxTriage({ processed: true, currentId: id });
      }
      return;
    }

    const rateBtn = e.target.closest("[data-drawer-rate-btn]");
    if (rateBtn && rateBtn.dataset.id) {
      const id = Number(rateBtn.dataset.id);
      const val = Number(rateBtn.dataset.drawerRateBtn);
      const item = findDrawerItem(id);
      const nextRating = item && Number(item.user_rating || 0) === val ? 0 : val;
      haptic("selection");
      await patchItem(id, { user_rating: nextRating });
      return;
    }

    if (e.target.closest("[data-drawer-edit-toggle]")) {
      state.drawerEditMode = !state.drawerEditMode;
      const item = findDrawerItem(state.drawerItemId);
      const summarySlot = document.getElementById("drawerSummarySlot");
      if (item && summarySlot) {
        summarySlot.innerHTML = buildDrawerSummaryInnerHtml(item);
      } else {
        renderDetailDrawer();
      }
      if (state.drawerEditMode) {
        setTimeout(() => {
          const inp = document.getElementById("drawerEditTitleInput");
          if (inp) inp.focus();
        }, 20);
      }
      return;
    }

    if (e.target.closest("[data-drawer-edit-cancel]")) {
      state.drawerEditMode = false;
      const item = findDrawerItem(state.drawerItemId);
      const summarySlot = document.getElementById("drawerSummarySlot");
      if (item && summarySlot) {
        summarySlot.innerHTML = buildDrawerSummaryInnerHtml(item);
      } else {
        renderDetailDrawer();
      }
      return;
    }

    const editSaveBtn = e.target.closest("[data-drawer-edit-save]");
    if (editSaveBtn) {
      const id = editSaveBtn.dataset.drawerEditSave;
      const tInp = document.getElementById("drawerEditTitleInput");
      const sInp = document.getElementById("drawerEditSummaryInput");
      state.drawerEditMode = false;
      await patchItem(
        id,
        {
          title_ru: tInp ? tInp.value : undefined,
          summary: sInp ? sInp.value : undefined,
        },
        { syncSummary: true }
      );
      return;
    }

    if (e.target.closest("[data-drawer-add-tag-toggle]")) {
      state.drawerAddTagMode = !state.drawerAddTagMode;
      const item = findDrawerItem(state.drawerItemId);
      const tagsSection = document.getElementById("drawerTagsSection");
      if (item && tagsSection) {
        tagsSection.innerHTML = buildDrawerTagsInnerHtml(item);
      } else {
        renderDetailDrawer();
      }
      if (state.drawerAddTagMode) {
        setTimeout(() => {
          const inp = document.getElementById("drawerNewTagInput");
          if (inp) inp.focus();
        }, 20);
      }
      return;
    }

    const addTagSubmit = e.target.closest("[data-drawer-add-tag-submit]");
    if (addTagSubmit) {
      const id = Number(addTagSubmit.dataset.drawerAddTagSubmit);
      const inp = document.getElementById("drawerNewTagInput");
      const cleanTag = (inp ? inp.value : "").replace(/^#+/, "").trim().toLowerCase();
      const item = findDrawerItem(id);
      if (cleanTag && item) {
        const nextTags = [...new Set([...(item.tags || []), cleanTag])];
        state.drawerAddTagMode = false;
        await patchItem(id, { tags: nextTags });
      }
      return;
    }

    const remTagBtn = e.target.closest("[data-remove-tag]");
    if (remTagBtn) {
      e.stopPropagation();
      const tagToRemove = (remTagBtn.dataset.removeTag || "").toLowerCase();
      const item = findDrawerItem(state.drawerItemId);
      if (item && tagToRemove) {
        const nextTags = (item.tags || []).filter((t) => String(t).toLowerCase() !== tagToRemove);
        await patchItem(item.id, { tags: nextTags });
      }
      return;
    }

    const tagEl = e.target.closest("[data-drawer-tag]");
    if (tagEl) {
      closeDetailDrawer();
      toggleTagFilter(tagEl.dataset.drawerTag || "");
      return;
    }

    if (e.target.closest("[data-drawer-delete-ask]")) {
      state.drawerConfirmDelete = true;
      const item = findDrawerItem(state.drawerItemId);
      const footer = document.getElementById("drawerActionsFooter");
      if (item && footer) footer.innerHTML = buildDrawerActionsFooterHtml(item);
      return;
    }

    if (e.target.closest("[data-drawer-delete-cancel]")) {
      state.drawerConfirmDelete = false;
      const item = findDrawerItem(state.drawerItemId);
      const footer = document.getElementById("drawerActionsFooter");
      if (item && footer) footer.innerHTML = buildDrawerActionsFooterHtml(item);
      return;
    }

    const delConfirm = e.target.closest("[data-drawer-delete-confirm]");
    if (delConfirm) {
      const id = Number(delConfirm.dataset.drawerDeleteConfirm);
      const wasTriage = state.triageMode;
      if (wasTriage) {
        await deleteItem(id);
        advanceInboxTriage({ processed: true, currentId: id });
      } else {
        closeDetailDrawer();
        await deleteItem(id);
      }
    }
  });

  // ==================== МОБИЛЬНАЯ ШТОРКА ФИЛЬТРОВ ====================

  const filtersSheetOverlay = document.getElementById("filtersSheetOverlay");
  const filtersSheetBody = document.getElementById("filtersSheetBody");

  function toggleTagFilter(rawTag) {
    const normalized = String(rawTag || "").replace(/^#+/, "").trim().toLowerCase();
    if (!normalized) {
      state.tags = [];
    } else if (state.tags.includes(normalized)) {
      state.tags = state.tags.filter((t) => t !== normalized);
    } else {
      state.tags = [...state.tags, normalized];
    }
    if (state.view !== "catalog") {
      state.view = "catalog";
    }
    syncNavigationState();
    renderTagBar();
    if (state.filtersSheetOpen) renderFiltersSheet();
    syncStateToUrl({ push: true });
    loadItems();
  }

  function toggleSmartView(smartKey) {
    const key = SMART_VIEWS_META[smartKey] ? smartKey : "";
    if (!key || state.smart === key) {
      state.smart = "";
    } else {
      state.smart = key;
      state.view = "catalog";
      state.status = "all";
    }
    syncNavigationState();
    renderActiveSmartBanner();
    if (state.filtersSheetOpen) renderFiltersSheet();
    syncStateToUrl({ push: true });
    loadItems();
  }

  function renderActiveSmartBanner() {
    const banner = document.getElementById("activeSmartBanner");
    if (!banner) return;
    const meta = state.smart ? SMART_VIEWS_META[state.smart] : null;
    if (state.view !== "catalog" || !meta) {
      banner.classList.add("hidden");
      banner.innerHTML = "";
      return;
    }
    banner.classList.remove("hidden");
    banner.innerHTML = `
      <div class="active-smart-meta">
        <span>${escapeHtml(meta.label)}</span>
        <span class="active-smart-desc">${escapeHtml(meta.desc)}</span>
      </div>
      <button type="button" class="smart-banner-clear" id="clearSmartViewBtn">Сбросить</button>
    `;
  }

  function renderFiltersSheet() {
    const categoryOpts = [
      { v: "", l: "Все" },
      { v: "movies", l: "🎬 Кино" },
      { v: "books", l: "📚 Книги" },
      { v: "video", l: "▶️ YouTube" },
      { v: "article", l: "📰 Статьи" },
      { v: "ideas", l: "💡 Идеи" },
    ];
    const smartOpts = Object.entries(SMART_VIEWS_META).map(([v, m]) => ({ v, l: m.label }));
    const tabCounts = state.statusCountsByTab[state.tab || ""] || null;
    const statusOpts = [
      { v: "all", l: "Все" },
      { v: "inbox", l: "📥 Входящие" },
      { v: "planned", l: "📌 В планах" },
      { v: "in_progress", l: "▶️ В процессе" },
      { v: "done", l: "✅ Готово" },
      { v: "dropped", l: "🚫 Брошено" },
    ].map((s) => {
      const cnt = tabCounts && tabCounts[s.v] != null ? ` (${tabCounts[s.v]})` : "";
      return { v: s.v, l: `${s.l}${cnt}` };
    });
    const sortOpts = [
      { v: "created", l: "По дате ↓" },
      { v: "updated", l: "По обновлению ↓" },
      { v: "imdb", l: "IMDb / Goodreads ↓" },
      { v: "kp", l: "КП / FantLab ↓" },
      { v: "rt", l: "Rotten Tomatoes ↓" },
      { v: "user", l: "Моя оценка ↓" },
      { v: "year", l: "Год выхода ↓" },
      { v: "title", l: "По алфавиту А–Я" },
    ];
    const modeOpts = [
      { v: "list", l: "☰ Список" },
      { v: "posters", l: "🖼 Постеры" },
      { v: "cards", l: "⊞ Карточки" },
      { v: "kanban", l: "▥ Канбан" },
    ];
    const effectiveTheme = resolveEffectiveTheme();
    const hasTgAuto = Boolean((tg && tg.colorScheme) || state.themeMode === "auto");
    const themeOpts = [
      { v: "light", l: "☀️ Светлая", active: state.themeMode === "light" || (!hasTgAuto && effectiveTheme === "light") },
      { v: "dark", l: "🌙 Тёмная", active: state.themeMode === "dark" || (!hasTgAuto && effectiveTheme === "dark") },
    ];
    if (hasTgAuto) {
      themeOpts.push({ v: "auto", l: "🌗 Авто (TG)", active: state.themeMode === "auto" });
    }
    const sortedTags = [...state.allTags].sort((a, b) => b.count - a.count || a.tag.localeCompare(b.tag));

    filtersSheetBody.innerHTML = `
      <div class="drawer-section">
        <div class="drawer-section-title">Вид отображения</div>
        <div class="sheet-pills-grid">
          ${modeOpts
            .map(
              (m) =>
                `<button type="button" class="sheet-pill ${state.viewMode === m.v ? "active" : ""}" data-sheet-mode="${m.v}">${m.l}</button>`
            )
            .join("")}
        </div>
      </div>

      <div class="drawer-section">
        <div class="drawer-section-title">Тема оформления</div>
        <div class="sheet-pills-grid">
          ${themeOpts
            .map(
              (t) =>
                `<button type="button" class="sheet-pill ${t.active ? "active" : ""}" data-sheet-theme="${t.v}">${t.l}</button>`
            )
            .join("")}
        </div>
      </div>

      ${
        state.view === "catalog"
          ? `
        <div class="drawer-section">
          <div class="drawer-section-title">Умные списки</div>
          <div class="sheet-pills-grid">
            ${smartOpts
              .map(
                (sm) =>
                  `<button type="button" class="sheet-pill ${state.smart === sm.v ? "active" : ""}" data-sheet-smart="${sm.v}">${escapeHtml(sm.l)}</button>`
              )
              .join("")}
          </div>
        </div>

        <div class="drawer-section">
          <div class="drawer-section-title">Категория</div>
          <div class="sheet-pills-grid">
            ${categoryOpts
              .map(
                (c) =>
                  `<button type="button" class="sheet-pill ${state.tab === c.v ? "active" : ""}" data-sheet-tab="${c.v}">${c.l}</button>`
              )
              .join("")}
          </div>
        </div>

        <div class="drawer-section">
          <div class="drawer-section-title">Статус</div>
          <div class="sheet-pills-grid">
            ${statusOpts
              .map(
                (s) =>
                  `<button type="button" class="sheet-pill ${state.status === s.v ? "active" : ""}" data-sheet-status="${s.v}">${s.l}</button>`
              )
              .join("")}
          </div>
        </div>

        ${
          sortedTags.length
            ? `
        <div class="drawer-section">
          <div class="drawer-section-title">Теги</div>
          <div class="sheet-pills-grid sheet-tags-grid">
            <button type="button" class="sheet-pill ${state.tags.length === 0 ? "active" : ""}" data-sheet-tag="">Все теги</button>
            ${sortedTags
              .map(
                (t) =>
                  `<button type="button" class="sheet-pill ${state.tags.includes(String(t.tag).toLowerCase()) ? "active" : ""}" data-sheet-tag="${escapeHtml(t.tag)}">#${escapeHtml(t.tag)} (${t.count})</button>`
              )
              .join("")}
          </div>
        </div>
        `
            : ""
        }

        <div class="drawer-section">
          <div class="drawer-section-title">Сортировка</div>
          <div class="sheet-pills-grid">
            ${sortOpts
              .map(
                (s) =>
                  `<button type="button" class="sheet-pill ${state.sort === s.v ? "active" : ""}" data-sheet-sort="${s.v}">${s.l}</button>`
              )
              .join("")}
          </div>
        </div>

        <div style="display:flex;flex-direction:column;gap:8px;">
          ${
            state.items.length
              ? `<button type="button" class="confirm-cancel-btn" id="sheetBulkToggleBtn" style="width:100%;padding:10px;">
                  ${state.selectedIds.size ? `Снять выделение (${state.selectedIds.size})` : "☑ Мультивыбор записей"}
                </button>`
              : ""
          }
          <button type="button" class="confirm-cancel-btn" id="sheetResetFiltersBtn" style="width:100%;padding:10px;">
            Сбросить фильтры
          </button>
          ${
            isTgWebApp && tg && typeof tg.requestFullscreen === "function"
              ? `<button type="button" class="confirm-cancel-btn" id="sheetTmaFullscreenBtn" style="width:100%;padding:10px;">
                  ${tg.isFullscreen ? "🗗 Выйти из полного экрана" : "⛶ На весь экран (Telegram)"}
                </button>`
              : ""
          }
          ${
            isTgWebApp && tmaHomeScreenCanAdd
              ? `<button type="button" class="confirm-cancel-btn" id="sheetTmaHomeScreenBtn" style="width:100%;padding:10px;">
                  📲 Ярлык на главный экран
                </button>`
              : ""
          }
          ${
            deferredInstallPrompt
              ? `<button type="button" class="auth-submit-btn" id="sheetInstallPwaBtn" style="width:100%;padding:10px;">
                  📲 Установить приложение (PWA)
                </button>`
              : ""
          }
        </div>
      `
          : `<div class="drawer-section"><p style="font-size:13.5px;color:var(--muted);">Фильтры по категориям, статусу, тегам и сортировке доступны в разделе «Каталог».</p></div>`
      }
    `;
  }

  function openFiltersSheet() {
    closeStatusPopover();
    closeRatingPopover();
    closeOpenSwipeRow();
    state.filtersSheetOpen = true;
    renderFiltersSheet();
    filtersSheetOverlay.classList.remove("hidden");
    filtersSheetOverlay.setAttribute("aria-hidden", "false");
    syncTelegramBackButton();
    haptic("light");
  }

  function closeFiltersSheet() {
    if (!state.filtersSheetOpen) return;
    state.filtersSheetOpen = false;
    filtersSheetOverlay.classList.add("hidden");
    filtersSheetOverlay.setAttribute("aria-hidden", "true");
    syncTelegramBackButton();
  }

  document.getElementById("filtersCloseBtn").addEventListener("click", closeFiltersSheet);
  filtersSheetOverlay.addEventListener("click", (e) => {
    if (e.target === filtersSheetOverlay) closeFiltersSheet();
  });

  filtersSheetBody.addEventListener("click", async (e) => {
    if (e.target.closest("#sheetTmaFullscreenBtn")) {
      toggleTmaFullscreen();
      closeFiltersSheet();
      return;
    }

    if (e.target.closest("#sheetTmaHomeScreenBtn")) {
      triggerTmaHomeScreen();
      closeFiltersSheet();
      return;
    }

    if (e.target.closest("#sheetInstallPwaBtn")) {
      if (deferredInstallPrompt) {
        const promptEvt = deferredInstallPrompt;
        deferredInstallPrompt = null;
        try {
          promptEvt.prompt();
          await promptEvt.userChoice;
        } catch {}
      }
      closeFiltersSheet();
      return;
    }

    if (e.target.closest("#sheetBulkToggleBtn")) {
      if (state.selectedIds.size > 0) {
        clearBulkSelection();
      } else if (state.items.length > 0) {
        toggleBulkSelect(state.items[0].id);
      }
      closeFiltersSheet();
      return;
    }
    const modeBtn = e.target.closest("[data-sheet-mode]");
    if (modeBtn) {
      setViewMode(modeBtn.dataset.sheetMode);
      renderFiltersSheet();
      return;
    }

    const themeBtn = e.target.closest("[data-sheet-theme]");
    if (themeBtn) {
      setThemeMode(themeBtn.dataset.sheetTheme);
      return;
    }

    const smartBtn = e.target.closest("[data-sheet-smart]");
    if (smartBtn) {
      toggleSmartView(smartBtn.dataset.sheetSmart || "");
      haptic("selection");
      return;
    }

    const tabBtn = e.target.closest("[data-sheet-tab]");
    if (tabBtn) {
      state.tab = tabBtn.dataset.sheetTab || "";
      state.tags = [];
      state.viewMode = getViewModeForTab(state.tab);
      syncStateToUrl({ push: true });
      refreshCurrentView();
      renderFiltersSheet();
      haptic("selection");
      return;
    }

    const stBtn = e.target.closest("[data-sheet-status]");
    if (stBtn) {
      state.status = stBtn.dataset.sheetStatus;
      syncNavigationState();
      renderFiltersSheet();
      syncStateToUrl({ push: true });
      loadItems();
      return;
    }

    const tagBtn = e.target.closest("[data-sheet-tag]");
    if (tagBtn) {
      toggleTagFilter(tagBtn.dataset.sheetTag || "");
      haptic("selection");
      return;
    }

    const sortBtn = e.target.closest("[data-sheet-sort]");
    if (sortBtn) {
      state.sort = sortBtn.dataset.sheetSort;
      document.getElementById("sortSelect").value = state.sort;
      const mobSort = document.getElementById("mobileSortSelect");
      if (mobSort) mobSort.value = state.sort;
      syncNavigationState();
      renderFiltersSheet();
      syncStateToUrl({ push: true });
      loadItems();
      return;
    }

    if (e.target.id === "sheetResetFiltersBtn") {
      state.tab = "";
      state.smart = "";
      state.status = "all";
      state.sort = "created";
      state.tags = [];
      state.viewMode = getViewModeForTab("");
      document.getElementById("sortSelect").value = "created";
      const mobSort = document.getElementById("mobileSortSelect");
      if (mobSort) mobSort.value = "created";
      syncStateToUrl({ push: true });
      refreshCurrentView();
      renderFiltersSheet();
    }
  });

  // ==================== ТЕГИ И РЕНДЕР КАТАЛОГА (LIST / CARDS / KANBAN) ====================

  function renderTagBar() {
    const container = document.getElementById("tagBar");
    const sorted = [...state.allTags].sort((a, b) => b.count - a.count || a.tag.localeCompare(b.tag));
    if (!sorted.length && !state.tags.length) {
      container.innerHTML = "";
      return;
    }

    const isMobile = window.innerWidth <= 820;
    const maxInline = isMobile ? 7 : 12;

    const inlineTags = sorted.slice(0, maxInline);
    const overflowTags = sorted.slice(maxInline);

    state.tags.forEach((activeTag) => {
      if (!inlineTags.some((t) => String(t.tag).toLowerCase() === activeTag)) {
        const activeIdx = overflowTags.findIndex((t) => String(t.tag).toLowerCase() === activeTag);
        if (activeIdx !== -1) {
          const [activeItem] = overflowTags.splice(activeIdx, 1);
          inlineTags.push(activeItem);
        }
      }
    });

    const extraUnknownTags = state.tags.filter(
      (activeTag) => !sorted.some((t) => String(t.tag).toLowerCase() === activeTag)
    );

    let html = `<button type="button" class="chip ${state.tags.length === 0 ? "active" : ""}" data-tag="">Все теги</button>`;
    inlineTags.forEach((t) => {
      const norm = String(t.tag).toLowerCase();
      const isAct = state.tags.includes(norm);
      const closeX = isAct ? `<span class="chip-x" aria-hidden="true">×</span>` : "";
      html += `<button type="button" class="chip ${isAct ? "active" : ""}" data-tag="${escapeHtml(t.tag)}">${escapeHtml(t.tag)} (${t.count})${closeX}</button>`;
    });
    extraUnknownTags.forEach((tagName) => {
      html += `<button type="button" class="chip active" data-tag="${escapeHtml(tagName)}">${escapeHtml(tagName)}<span class="chip-x" aria-hidden="true">×</span></button>`;
    });

    if (overflowTags.length > 0) {
      const selectedInOverflow = overflowTags.some((t) => state.tags.includes(String(t.tag).toLowerCase()));
      html += `<select id="moreTagsSelect" class="more-tags-select ${selectedInOverflow ? "active" : ""}">`;
      html += `<option value="">Ещё (${overflowTags.length})...</option>`;
      overflowTags.forEach((t) => {
        const sel = state.tags.includes(String(t.tag).toLowerCase()) ? "selected" : "";
        html += `<option value="${escapeHtml(t.tag)}" ${sel}>${escapeHtml(t.tag)} (${t.count})</option>`;
      });
      html += `</select>`;
    }

    container.innerHTML = html;
  }

  function updateCountLabels(text, shortCount) {
    const desk = document.getElementById("totalCountLabel");
    const mob = document.getElementById("mobileCountLabel");
    if (desk) desk.textContent = text;
    if (mob) mob.textContent = String(shortCount);
  }

  function shouldShowCreator(item) {
    if (!item || !item.creator) return false;
    const cat = (item.category || "").toLowerCase();
    if (cat === "post" || cat === "idea") return false;
    if (String(item.creator).trim().startsWith("@")) return false;
    return true;
  }

  function collectItemTags(item) {
    const out = [];
    const seen = new Set();
    [...(item.genres || []), ...(item.tags || [])].forEach((raw) => {
      const clean = String(raw || "").trim();
      const key = clean.toLowerCase();
      if (clean && !seen.has(key)) {
        seen.add(key);
        out.push(clean);
      }
    });
    return out;
  }

  function buildTagsLineHtml(item, containerClass, pillClass = "genre-pill") {
    const allTags = collectItemTags(item);
    if (!allTags.length) return "";
    const isExpanded = state.expandedTagIds.has(Number(item.id));
    return `<div class="${containerClass}${isExpanded ? " tags-expanded" : ""}" data-tags-item-id="${item.id}">${allTags
      .map((g) => `<span class="${pillClass}" data-tag="${escapeHtml(g)}">#${escapeHtml(g)}</span>`)
      .join("")}</div>`;
  }

  function applyMobileSingleLineTags() {
    const isMobile = window.innerWidth <= 820;
    const containers = document.querySelectorAll("#catalogGrid .list-tags[data-tags-item-id], #catalogGrid .genres-line[data-tags-item-id]");
    containers.forEach((el) => {
      el.querySelectorAll(".tags-expand-btn").forEach((b) => b.remove());
      const pills = Array.from(el.querySelectorAll(".genre-pill"));
      pills.forEach((p) => p.classList.remove("tag-overflow-hidden", "tag-first-cap"));

      const itemId = Number(el.dataset.tagsItemId);
      const isExpanded = state.expandedTagIds.has(itemId);
      el.classList.toggle("tags-expanded", isExpanded);

      if (!isMobile || isExpanded || pills.length <= 1) return;

      const firstTop = pills[0].offsetTop;
      if (!pills.some((p) => p.offsetTop > firstTop + 4)) return;

      const expandBtn = document.createElement("button");
      expandBtn.type = "button";
      expandBtn.className = el.classList.contains("list-tags")
        ? "genre-pill list-tag-pill tags-expand-btn"
        : "genre-pill tags-expand-btn";
      expandBtn.dataset.action = "expand-tags";
      expandBtn.dataset.id = String(itemId);
      expandBtn.title = "Показать все теги";
      expandBtn.setAttribute("aria-label", "Показать все теги");
      expandBtn.textContent = "...";
      el.appendChild(expandBtn);

      for (let i = pills.length - 1; i >= 1; i--) {
        pills[i].classList.add("tag-overflow-hidden");
        const prev = pills[i - 1];
        if (expandBtn.offsetTop <= firstTop + 4 && prev.offsetTop <= firstTop + 4) {
          break;
        }
      }
      if (expandBtn.offsetTop > firstTop + 4) {
        pills[0].classList.add("tag-first-cap");
      }
    });
  }

  function buildBulkCheckboxHtml(item) {
    const numId = Number(item.id);
    const isSel = state.selectedIds.has(numId);
    return `<button type="button" class="bulk-select-cb${isSel ? " checked" : ""}" data-bulk-toggle="${numId}" aria-label="Выбрать запись" aria-pressed="${isSel ? "true" : "false"}">${isSel ? "✓" : ""}</button>`;
  }

  function renderListRow(item) {
    const isSel = state.selectedIds.has(Number(item.id));
    const emoji = CATEGORY_EMOJI[item.category] || "📌";
    const catClass = `cat-${escapeHtml(item.category || "idea")}`;
    const isVideo = isVideoItem(item);
    const isTextOnly = isTextOnlyCategory(item);
    const primaryUrl = getPrimarySourceUrl(item);
    const sourceVisual = resolveSourceVisual(primaryUrl);

    let leftVisualHtml = "";
    if (isTextOnly) {
      const innerIco = sourceVisual ? sourceVisual.iconHtml : `<span>${emoji}</span>`;
      leftVisualHtml = `<div class="list-type-badge">${innerIco}</div>`;
    } else if (isVideo) {
      const posterHtml = item.poster_url
        ? `<img src="${escapeHtml(item.poster_url)}" alt="" loading="lazy" />`
        : `<span>${emoji}</span>`;
      leftVisualHtml = `<div class="list-poster poster-video">${posterHtml}<span class="poster-play-badge">${UI_ICONS.play}</span></div>`;
    } else {
      const posterHtml = item.poster_url
        ? `<img src="${escapeHtml(item.poster_url)}" alt="" loading="lazy" />`
        : `<span>${emoji}</span>`;
      leftVisualHtml = `<div class="list-poster">${posterHtml}</div>`;
    }

    const yearHtml = item.release_year ? `<span class="list-year">(${item.release_year})</span>` : "";
    const origHtml =
      item.title_orig && item.title_orig.toLowerCase() !== (item.title_ru || "").toLowerCase()
        ? `<span class="list-orig">${escapeHtml(item.title_orig)}</span>`
        : "";

    const meta = parseMeta(item.meta);
    const subParts = [];
    if (shouldShowCreator(item)) subParts.push(escapeHtml(item.creator));
    if (item.category === "series" && meta.seasons_count) {
      subParts.push(`Сезонов: ${Number(meta.seasons_count)}`);
    }
    if (item.category === "book" && meta.page_count) {
      subParts.push(`${Number(meta.page_count)} стр.`);
    }

    const cleanSummary = (item.summary || "").trim();
    const showSnippet =
      isTextOnly &&
      cleanSummary &&
      cleanSummary.toLowerCase() !== (item.title_ru || "").trim().toLowerCase();
    const snippetHtml = showSnippet
      ? `<div class="list-summary-snippet">${escapeHtml(cleanSummary)}</div>`
      : "";

    const ratingsHtml = buildRatingsHtml(item, { compact: false, includeSources: false });
    const noteBadgeHtml = meta.user_note
      ? `<div class="list-note-badge" title="${escapeHtml(meta.user_note)}">✍️ ${escapeHtml(meta.user_note)}</div>`
      : "";
    const tagsHtml = buildTagsLineHtml(item, "list-tags", "genre-pill list-tag-pill");
    const cornerSourceHtml = buildCornerSourceHtml(item);
    const desktopActionsHtml = buildCardActionsHtml(item, "list-actions");
    const mobileActionsHtml = buildCardActionsHtml(item, "mobile-inline");

    const rightActions = getSwipeRightActions(item.status);
    const leftTrayBtns = rightActions
      .map(
        (act, idx) =>
          `<button type="button" class="swipe-tray-btn ${act.tone} ${idx === 0 ? "is-primary" : "is-secondary"}" data-swipe-status="${act.status}" data-id="${item.id}">${act.svg}<span>${escapeHtml(act.label)}</span></button>`
      )
      .join("");
    const rightTrayBtns = `
      <button type="button" class="swipe-tray-btn st-tone-rate is-secondary" data-swipe-rate="${item.id}">${UI_ICONS.starFilled}<span>Оценка</span></button>
      <button type="button" class="swipe-tray-btn st-tone-delete is-primary" data-swipe-delete="${item.id}">${UI_ICONS.trash}<span>Удалить</span></button>
    `;

    return `
      <div class="swipe-row-wrap" data-swipe-id="${item.id}">
        <div class="swipe-tray swipe-tray-left" aria-hidden="true">${leftTrayBtns}</div>
        <div class="swipe-tray swipe-tray-right" aria-hidden="true">${rightTrayBtns}</div>
        <article class="list-row cat-accent ${catClass}${isSel ? " is-selected" : ""}" data-open-id="${item.id}">
          ${buildBulkCheckboxHtml(item)}
          ${leftVisualHtml}
          <div class="list-main">
            <div class="list-title-line">
              <span class="list-title">${escapeHtml(item.title_ru)}</span>${yearHtml ? ` ${yearHtml}` : ""}${origHtml ? ` ${origHtml}` : ""}${cornerSourceHtml ? ` ${cornerSourceHtml}` : ""}
            </div>
            ${subParts.length ? `<div class="list-subline">${subParts.join(" · ")}</div>` : ""}
            ${snippetHtml}
            ${ratingsHtml ? `<div class="list-ratings">${ratingsHtml}</div>` : ""}
            ${noteBadgeHtml}
            ${tagsHtml}
            <div class="list-mobile-actions">${mobileActionsHtml}</div>
          </div>
          <div class="list-right">
            ${desktopActionsHtml}
          </div>
        </article>
      </div>
    `;
  }

  function renderEditorialCard(item) {
    const isSel = state.selectedIds.has(Number(item.id));
    const emoji = CATEGORY_EMOJI[item.category] || "📌";
    const catClass = `cat-${escapeHtml(item.category || "idea")}`;
    const isVideo = isVideoItem(item);
    const isTextOnly = isTextOnlyCategory(item);
    const posterHtml = item.poster_url
      ? `<img src="${escapeHtml(item.poster_url)}" alt="" loading="lazy" />`
      : `<span>${emoji}</span>`;

    const origLine =
      item.title_orig && item.title_orig.toLowerCase() !== (item.title_ru || "").toLowerCase()
        ? `<div class="card-orig">${escapeHtml(item.title_orig)}</div>`
        : "";

    const yearStr = item.release_year ? ` (${item.release_year})` : "";
    const meta = parseMeta(item.meta);
    const subParts = [];
    if (shouldShowCreator(item)) subParts.push(`👤 ${escapeHtml(item.creator)}`);
    if (item.category === "series" && meta.seasons_count) {
      subParts.push(`📺 Сезонов: ${Number(meta.seasons_count)}`);
    }
    if (item.category === "book" && meta.page_count) {
      subParts.push(`📖 ${Number(meta.page_count)} стр.`);
    }
    const creatorLine = subParts.length ? `<div class="card-creator">${subParts.join(" · ")}</div>` : "";

    const genresHtml = buildTagsLineHtml(item, "genres-line", "genre-pill");

    const noteBadgeHtml = meta.user_note
      ? `<div class="list-note-badge" title="${escapeHtml(meta.user_note)}">✍️ ${escapeHtml(meta.user_note)}</div>`
      : "";
    const summaryHtml = item.summary ? `<div class="summary-text">${escapeHtml(item.summary)}</div>` : "";
    const ratingsHtml = buildRatingsHtml(item, { compact: false, includeSources: false });
    const cornerSourceHtml = buildCornerSourceHtml(item);

    let topBlockHtml = "";
    if (isVideo && item.poster_url) {
      topBlockHtml = `
        <div class="card-video-thumb">
          <img src="${escapeHtml(item.poster_url)}" alt="" loading="lazy" />
          <span class="poster-play-badge large">${UI_ICONS.play}</span>
        </div>
        <div class="card-info">
          <div class="card-title">${escapeHtml(item.title_ru)}${yearStr}${cornerSourceHtml ? ` ${cornerSourceHtml}` : ""}</div>
          ${origLine}
          ${creatorLine}
          ${ratingsHtml ? `<div class="ratings-bar">${ratingsHtml}</div>` : ""}
          ${noteBadgeHtml}
        </div>
      `;
    } else if (isTextOnly) {
      const visual = resolveSourceVisual(getPrimarySourceUrl(item));
      const eyebrowIco = visual ? visual.iconHtml : `<span>${emoji}</span>`;
      const eyebrowLabel = visual ? visual.safeLabel : escapeHtml(CATEGORY_TITLES[item.category] || "Запись");
      topBlockHtml = `
        <div class="card-info">
          <div class="card-eyebrow">${eyebrowIco}<span>${eyebrowLabel}</span></div>
          <div class="card-title">${escapeHtml(item.title_ru)}${yearStr}${cornerSourceHtml ? ` ${cornerSourceHtml}` : ""}</div>
          ${origLine}
          ${creatorLine}
          ${ratingsHtml ? `<div class="ratings-bar">${ratingsHtml}</div>` : ""}
          ${noteBadgeHtml}
        </div>
      `;
    } else {
      topBlockHtml = `
        <div class="card-top">
          <div class="poster-box">${posterHtml}</div>
          <div class="card-info">
            <div class="card-title">${escapeHtml(item.title_ru)}${yearStr}${cornerSourceHtml ? ` ${cornerSourceHtml}` : ""}</div>
            ${origLine}
            ${creatorLine}
            ${ratingsHtml ? `<div class="ratings-bar">${ratingsHtml}</div>` : ""}
            ${noteBadgeHtml}
          </div>
        </div>
      `;
    }

    return `
      <article class="item-card cat-accent ${catClass}${isVideo ? " is-video" : ""}${isSel ? " is-selected" : ""}" data-open-id="${item.id}">
        ${buildBulkCheckboxHtml(item)}
        ${topBlockHtml}
        ${genresHtml}
        ${summaryHtml}
        <div class="card-footer">
          ${buildCardActionsHtml(item)}
        </div>
      </article>
    `;
  }

  function renderPosterCard(item) {
    const isSel = state.selectedIds.has(Number(item.id));
    const emoji = CATEGORY_EMOJI[item.category] || "📌";
    const catClass = `cat-${escapeHtml(item.category || "idea")}`;
    const isVideo = isVideoItem(item);
    const stMeta = STATUS_META[item.status] || STATUS_META.inbox;
    const scoreBadge = getPrimaryPosterScore(item);
    const cornerSourceHtml = buildCornerSourceHtml(item);
    const meta = parseMeta(item.meta);

    let coverInner = "";
    if (item.poster_url) {
      const playBadge = isVideo ? `<span class="poster-play-badge large">${UI_ICONS.play}</span>` : "";
      coverInner = `<img src="${escapeHtml(item.poster_url)}" alt="${escapeHtml(item.title_ru || "")}" loading="lazy" />${playBadge}`;
    } else {
      const visual = resolveSourceVisual(getPrimarySourceUrl(item));
      const fallbackHeadIco = visual ? visual.iconHtml : `<span>${emoji}</span>`;
      const fallbackHeadLabel = visual ? visual.safeLabel : escapeHtml(CATEGORY_TITLES[item.category] || "Запись");
      const snippet = item.summary ? `<div class="poster-fallback-snippet">${escapeHtml(item.summary)}</div>` : "";
      coverInner = `
        <div class="poster-fallback-cover">
          <div class="poster-fallback-head">${fallbackHeadIco}<span>${fallbackHeadLabel}</span></div>
          <div class="poster-fallback-title">${escapeHtml(item.title_ru || "Без названия")}</div>
          ${snippet}
        </div>
      `;
    }

    const scoreHtml = scoreBadge
      ? `<div class="poster-score-pill ${scoreBadge.isUser ? "is-user-score" : ""}">${escapeHtml(scoreBadge.text)}</div>`
      : "";

    const subParts = [];
    if (item.release_year) subParts.push(String(item.release_year));
    if (shouldShowCreator(item)) subParts.push(escapeHtml(item.creator));
    if (item.category === "series" && meta.seasons_count) {
      subParts.push(`${Number(meta.seasons_count)} сез.`);
    }
    if (!subParts.length) {
      const domLabel = buildItemDomainLabel(item);
      if (domLabel) subParts.push(escapeHtml(domLabel));
    }

    const currentRating = Number(item.user_rating || 0);
    const rateBtnLabel = currentRating ? `★ ${currentRating}` : "Оценка";

    return `
      <article class="poster-card ${catClass}${isVideo ? " is-video-poster" : ""}${isSel ? " is-selected" : ""}" data-open-id="${item.id}">
        <div class="poster-cover">
          ${coverInner}
          <button type="button" class="poster-status-dot-btn" data-action="status-menu" data-id="${item.id}" title="Статус: ${escapeHtml(stMeta.label)}" aria-label="Статус: ${escapeHtml(stMeta.label)}">
            <span style="display:inline-flex;color:${stMeta.dot};">${stMeta.svg}</span>
          </button>
          ${buildBulkCheckboxHtml(item)}
          ${scoreHtml}
          <div class="poster-hover-bar">
            <button type="button" class="poster-hover-btn" data-action="status-menu" data-id="${item.id}" aria-label="Статус">
              <span style="display:inline-flex;color:${stMeta.dot};">${stMeta.svg}</span>
              <span>${escapeHtml(stMeta.short)}</span>
            </button>
            <button type="button" class="poster-hover-btn" data-action="rating-menu" data-id="${item.id}" aria-label="Моя оценка">
              <span>${rateBtnLabel}</span>
            </button>
          </div>
        </div>
        <div class="poster-caption">
          <div class="poster-title-row">
            <div class="poster-title">${escapeHtml(item.title_ru || "Без названия")}</div>
            ${cornerSourceHtml}
          </div>
          ${subParts.length ? `<div class="poster-meta-line">${subParts.join(" · ")}</div>` : ""}
        </div>
      </article>
    `;
  }

  function renderKanbanCard(item) {
    const isSel = state.selectedIds.has(Number(item.id));
    const emoji = CATEGORY_EMOJI[item.category] || "📌";
    const catClass = `cat-${escapeHtml(item.category || "idea")}`;
    const isVideo = isVideoItem(item);
    const isTextOnly = isTextOnlyCategory(item);
    const posterHtml = item.poster_url
      ? `<img src="${escapeHtml(item.poster_url)}" alt="" loading="lazy" />`
      : `<span>${emoji}</span>`;
    const yearStr = item.release_year ? ` (${item.release_year})` : "";
    const ratingsHtml = buildRatingsHtml(item, { compact: false, includeSources: false });
    const cornerSourceHtml = buildCornerSourceHtml(item);

    const mediaBlock = isTextOnly
      ? ""
      : `<div class="kanban-poster${isVideo ? " poster-video" : ""}">${posterHtml}${isVideo ? `<span class="poster-play-badge">${UI_ICONS.play}</span>` : ""}</div>`;
    const cleanSummary = (item.summary || "").trim();
    const snippetHtml =
      isTextOnly && cleanSummary && cleanSummary.toLowerCase() !== (item.title_ru || "").trim().toLowerCase()
        ? `<div class="kanban-snippet">${escapeHtml(cleanSummary)}</div>`
        : "";

    return `
      <article class="kanban-card cat-accent ${catClass}${isSel ? " is-selected" : ""}" data-open-id="${item.id}" draggable="true" data-drag-id="${item.id}">
        ${buildBulkCheckboxHtml(item)}
        <div class="kanban-card-top">
          ${mediaBlock}
          <div class="kanban-card-meta">
            <div class="list-title" style="font-size:14.5px;">${escapeHtml(item.title_ru)}${yearStr}${cornerSourceHtml ? ` ${cornerSourceHtml}` : ""}</div>
            ${shouldShowCreator(item) ? `<div class="list-subline" style="font-size:12px;">${escapeHtml(item.creator)}</div>` : ""}
          </div>
        </div>
        ${snippetHtml}
        ${ratingsHtml ? `<div class="ratings-bar">${ratingsHtml}</div>` : ""}
        <div class="card-footer" style="padding-top:8px;">
          ${buildCardActionsHtml(item, "kanban-actions")}
        </div>
      </article>
    `;
  }

  function renderKanbanBoard() {
    const hasDropped = state.items.some((i) => i.status === "dropped");
    const cols = hasDropped
      ? ["inbox", "planned", "in_progress", "done", "dropped"]
      : ["inbox", "planned", "in_progress", "done"];
    const html = cols
      .map((statusKey) => {
        const meta = STATUS_META[statusKey];
        const colItems = state.items.filter((i) => (i.status || "inbox") === statusKey);
        return `
          <section class="kanban-col" data-kanban-status="${statusKey}">
            <div class="kanban-col-header">
              <div class="kanban-col-title">
                <span class="kanban-col-ico" style="color:${meta.dot};">${meta.svg}</span>
                <span>${escapeHtml(meta.label)}</span>
              </div>
              <span class="kanban-col-count">${colItems.length}</span>
            </div>
            <div class="kanban-cards">
              ${
                colItems.length
                  ? colItems.map(renderKanbanCard).join("")
                  : `<div class="kanban-empty">Нет записей</div>`
              }
            </div>
          </section>
        `;
      })
      .join("");
    return { html, colCount: cols.length };
  }

  function computeStatusCounts(list) {
    const counts = { all: list.length, inbox: 0, planned: 0, in_progress: 0, done: 0, dropped: 0 };
    list.forEach((it) => {
      const k = counts[it.status] !== undefined ? it.status : "inbox";
      counts[k] += 1;
    });
    return counts;
  }

  function renderStatusPillsBar() {
    const bar = document.getElementById("statusPillsBar");
    if (!bar) return;
    if (state.view !== "catalog") {
      bar.classList.add("hidden");
      bar.innerHTML = "";
      return;
    }
    bar.classList.remove("hidden");
    const tabKey = state.tab || "";
    const counts = state.statusCountsByTab[tabKey] || computeStatusCounts(state.items);
    const pills = [
      { key: "all", label: "Все", svg: "", dot: "var(--muted)" },
      { key: "inbox", label: STATUS_META.inbox.label, svg: STATUS_META.inbox.svg, dot: STATUS_META.inbox.dot },
      { key: "planned", label: STATUS_META.planned.label, svg: STATUS_META.planned.svg, dot: STATUS_META.planned.dot },
      { key: "in_progress", label: STATUS_META.in_progress.label, svg: STATUS_META.in_progress.svg, dot: STATUS_META.in_progress.dot },
      { key: "done", label: STATUS_META.done.label, svg: STATUS_META.done.svg, dot: STATUS_META.done.dot },
    ];
    if (counts.dropped > 0 || state.status === "dropped") {
      pills.push({
        key: "dropped",
        label: STATUS_META.dropped.label,
        svg: STATUS_META.dropped.svg,
        dot: STATUS_META.dropped.dot,
      });
    }

    const pillsHtml = pills
      .map((p) => {
        const isActive = state.status === p.key;
        const ico = p.svg ? `<span style="display:inline-flex;color:${p.dot};">${p.svg}</span>` : "";
        const cntText = counts[p.key] != null ? `<span class="status-pill-count">${counts[p.key]}</span>` : "";
        return `<button type="button" class="status-pill-chip ${isActive ? "active" : ""}" data-status-pill="${p.key}">${ico}<span>${escapeHtml(p.label)}</span>${cntText}</button>`;
      })
      .join("");

    const triageBtnHtml =
      counts.inbox > 0
        ? `<button type="button" class="status-pill-chip triage-chip" id="triageBtnBar" title="Быстрый разбор входящих (клавиша T)"><span>⚡ Разобрать (${counts.inbox})</span></button>`
        : "";

    const luckyBtnHtml = `<button type="button" class="status-pill-chip lucky-chip" id="luckyBtnBar" title="Выбрать случайную запись из текущего списка">${UI_ICONS.dice}<span>Мне повезёт</span></button>`;
    bar.innerHTML = pillsHtml + triageBtnHtml + luckyBtnHtml;
  }

  function renderSkeletonRows(count = 6) {
    const grid = document.getElementById("catalogGrid");
    const empty = document.getElementById("emptyState");
    if (!grid) return;
    if (empty) empty.classList.add("hidden");
    grid.className = "catalog-list view-list";
    grid.innerHTML = Array.from({ length: count })
      .map(
        () => `
        <div class="skeleton-row" aria-hidden="true">
          <div class="sk-poster"></div>
          <div class="sk-body">
            <div class="sk-line w-60"></div>
            <div class="sk-line w-40"></div>
            <div class="sk-line w-30"></div>
          </div>
        </div>
      `
      )
      .join("");
  }

  function pickRandomItem({ fromDrawer = false } = {}) {
    if (!state.items.length) return;
    if (!fromDrawer) {
      state.luckySeenIds = new Set();
    }
    const basePool =
      state.status === "all" && !state.smart
        ? state.items.filter((i) => i.status === "planned" || i.status === "inbox")
        : state.items;
    const pool = basePool.length ? basePool : state.items;

    let candidates = pool.filter(
      (i) =>
        !state.luckySeenIds.has(Number(i.id)) &&
        !(fromDrawer && pool.length > 1 && Number(i.id) === Number(state.drawerItemId))
    );
    if (!candidates.length) {
      state.luckySeenIds = new Set();
      candidates =
        fromDrawer && pool.length > 1
          ? pool.filter((i) => Number(i.id) !== Number(state.drawerItemId))
          : pool;
    }
    if (!candidates.length) candidates = pool;

    const chosen = candidates[Math.floor(Math.random() * candidates.length)];
    if (chosen) {
      state.luckySeenIds.add(Number(chosen.id));
      state.luckyMode = true;
      haptic("medium");
      openDetailDrawer(chosen.id, { keepLucky: true, replaceUrl: fromDrawer });
    }
  }

  function renderEmptyState() {
    const empty = document.getElementById("emptyState");
    if (!empty) return;
    const emojiEl = document.getElementById("emptyStateEmoji");
    const titleEl = document.getElementById("emptyStateTitle");
    const descEl = document.getElementById("emptyStateDesc");
    const actionsEl = document.getElementById("emptyStateActions");

    const hasFilters = Boolean(
      state.tab ||
        state.q ||
        (state.view === "catalog" && (state.status !== "all" || state.tags.length > 0 || Boolean(state.smart)))
    );

    if (emojiEl) {
      emojiEl.textContent = hasFilters ? "🔍" : "📖";
    }
    if (titleEl) {
      titleEl.textContent =
        state.view === "originals" ? "Оригиналов не найдено" : "Записей не найдено";
    }
    if (descEl) {
      descEl.textContent = hasFilters
        ? "Попробуйте изменить запрос или сбросить активные фильтры."
        : "В этом разделе пока пусто. Добавьте фильм, книгу, ссылку или заметку прямо здесь.";
    }
    if (actionsEl) {
      const btns = [];
      if (hasFilters) {
        btns.push(
          `<button type="button" class="confirm-cancel-btn empty-cta-btn" id="emptyResetFiltersBtn">Сбросить фильтры</button>`
        );
      }
      btns.push(
        `<button type="button" class="auth-submit-btn empty-cta-btn" id="emptyAddItemBtn">+ Добавить запись</button>`
      );
      actionsEl.innerHTML = btns.join("");
    }
    empty.classList.remove("hidden");
  }

  function syncBulkCardsInPlace() {
    const grid = document.getElementById("catalogGrid");
    if (!grid || state.view !== "catalog") return;
    grid.classList.toggle("bulk-selecting", state.selectedIds.size > 0);
    grid.querySelectorAll("[data-open-id]").forEach((card) => {
      const idNum = Number(card.dataset.openId);
      const isSel = state.selectedIds.has(idNum);
      card.classList.toggle("is-selected", isSel);
      const cb = card.querySelector("[data-bulk-toggle]");
      if (cb) {
        cb.classList.toggle("checked", isSel);
        cb.textContent = isSel ? "✓" : "";
        cb.setAttribute("aria-pressed", isSel ? "true" : "false");
      }
    });
  }

  function renderBulkActionBar() {
    const bar = document.getElementById("bulkActionBar");
    if (!bar) return;
    const cnt = state.selectedIds.size;
    if (state.view !== "catalog" || cnt === 0) {
      bar.classList.add("hidden");
      const sel = document.getElementById("bulkStatusSelect");
      if (sel) sel.value = "";
      return;
    }
    bar.classList.remove("hidden");
    const cntEl = document.getElementById("bulkCountLabel");
    if (cntEl) cntEl.textContent = `Выбрано: ${cnt}`;
    const allBtn = document.getElementById("bulkSelectAllBtn");
    if (allBtn) {
      allBtn.textContent = cnt >= state.items.length && state.items.length > 0 ? "Снять все" : "Выбрать все";
    }
    const tagWrap = document.getElementById("bulkTagWrap");
    if (tagWrap) tagWrap.classList.toggle("hidden", !state.bulkTagOpen);
    const delBtn = document.getElementById("bulkDeleteBtn");
    if (delBtn) {
      delBtn.classList.toggle("confirming", state.bulkDeleteConfirm);
      delBtn.textContent = state.bulkDeleteConfirm ? `Удалить (${cnt})?` : "Удалить";
    }
  }

  function clearBulkSelection() {
    if (state.selectedIds.size === 0 && !state.bulkDeleteConfirm && !state.bulkTagOpen) {
      renderBulkActionBar();
      return;
    }
    state.selectedIds.clear();
    state.lastSelectedId = null;
    state.bulkDeleteConfirm = false;
    state.bulkTagOpen = false;
    syncBulkCardsInPlace();
    renderBulkActionBar();
  }

  function selectAllVisible() {
    state.items.forEach((it) => state.selectedIds.add(Number(it.id)));
    state.bulkDeleteConfirm = false;
    syncBulkCardsInPlace();
    renderBulkActionBar();
    haptic("light");
  }

  function toggleBulkSelect(itemId, { shiftKey = false } = {}) {
    const numId = Number(itemId);
    if (!numId) return;
    if (shiftKey && state.lastSelectedId !== null && state.lastSelectedId !== numId) {
      const idxA = state.items.findIndex((i) => Number(i.id) === Number(state.lastSelectedId));
      const idxB = state.items.findIndex((i) => Number(i.id) === numId);
      if (idxA !== -1 && idxB !== -1) {
        const start = Math.min(idxA, idxB);
        const end = Math.max(idxA, idxB);
        for (let i = start; i <= end; i++) {
          state.selectedIds.add(Number(state.items[i].id));
        }
      } else {
        state.selectedIds.add(numId);
      }
    } else if (state.selectedIds.has(numId)) {
      state.selectedIds.delete(numId);
    } else {
      state.selectedIds.add(numId);
    }
    state.lastSelectedId = numId;
    state.bulkDeleteConfirm = false;
    if (state.selectedIds.size === 0) state.bulkTagOpen = false;
    syncBulkCardsInPlace();
    renderBulkActionBar();
    haptic("selection");
  }

  async function runBulkAction(payload) {
    const ids = [...state.selectedIds];
    if (!ids.length) return false;
    try {
      const res = await fetch("/api/items/bulk", {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ item_ids: ids, ...payload }),
      });
      if (res.status === 401 || res.status === 403) {
        showAuthModal(res.status === 403 && Boolean(tg && tg.initData));
        return false;
      }
      if (!res.ok) return false;
      clearCatalogCache();
      clearBulkSelection();
      haptic("medium");
      await loadItems();
      if (payload.add_tag !== undefined || payload.delete) {
        loadTags();
      }
      return true;
    } catch {
      return false;
    }
  }

  function renderLoadMoreBar() {
    const bar = document.getElementById("loadMoreBar");
    const btn = document.getElementById("loadMoreBtn");
    if (!bar || !btn) return;
    if (state.view !== "catalog" || !state.hasMoreItems || !state.items.length) {
      bar.classList.add("hidden");
      return;
    }
    bar.classList.remove("hidden");
    const remaining = Math.max(0, Number(state.itemsTotal || 0) - state.items.length);
    btn.disabled = Boolean(state.loadingMoreItems);
    btn.textContent = state.loadingMoreItems
      ? "Загрузка..."
      : remaining > 0
      ? `Загрузить ещё (осталось ${remaining})`
      : "Загрузить ещё";
  }

  function renderCatalog(opts = {}) {
    const { skipDrawer = false } = opts;
    openSwipeWrap = null;
    state.focusedIndex = -1;
    const visibleIds = new Set(state.items.map((i) => Number(i.id)));
    for (const sid of [...state.selectedIds]) {
      if (!visibleIds.has(sid)) state.selectedIds.delete(sid);
    }

    const container = document.getElementById("catalogContainer");
    const grid = document.getElementById("catalogGrid");
    const empty = document.getElementById("emptyState");

    const shownCount = state.items.length;
    const totalCount = Math.max(shownCount, Number(state.itemsTotal || shownCount));
    const countLabel =
      state.hasMoreItems && totalCount > shownCount
        ? `Показано ${shownCount} из ${totalCount}`
        : `Найдено записей: ${totalCount}`;
    updateCountLabels(countLabel, totalCount);
    renderActiveSmartBanner();
    renderStatusPillsBar();

    if (!state.items.length) {
      if (container) container.classList.remove("kanban-wide");
      grid.className = "catalog-list";
      grid.innerHTML = "";
      renderLoadMoreBar();
      renderBulkActionBar();
      renderEmptyState();
      return;
    }
    empty.classList.add("hidden");

    if (container) {
      container.classList.toggle("kanban-wide", state.viewMode === "kanban");
    }

    if (state.viewMode === "kanban") {
      const { html, colCount } = renderKanbanBoard();
      grid.className = `catalog-list view-kanban${colCount === 5 ? " cols-5" : ""}`;
      grid.innerHTML = html;
    } else if (state.viewMode === "posters") {
      const isWideVideo = state.tab === "video";
      grid.className = `catalog-list view-posters${isWideVideo ? " view-posters-wide" : ""}`;
      grid.innerHTML = state.items.map(renderPosterCard).join("");
    } else if (state.viewMode === "cards") {
      grid.className = "catalog-list view-cards";
      grid.innerHTML = state.items.map(renderEditorialCard).join("");
    } else {
      grid.className = "catalog-list view-list";
      grid.innerHTML = state.items.map(renderListRow).join("");
    }

    if (state.selectedIds.size > 0) {
      grid.classList.add("bulk-selecting");
    }
    renderLoadMoreBar();
    renderBulkActionBar();

    applyMobileSingleLineTags();

    if (!skipDrawer && state.drawerItemId !== null) {
      renderDetailDrawer();
    }
  }

  function renderOriginals() {
    const container = document.getElementById("catalogContainer");
    const grid = document.getElementById("catalogGrid");
    const empty = document.getElementById("emptyState");
    if (container) container.classList.remove("kanban-wide");
    renderLoadMoreBar();
    renderActiveSmartBanner();
    renderStatusPillsBar();
    renderBulkActionBar();

    updateCountLabels(`Оригиналов: ${state.originals.length}`, state.originals.length);

    if (!state.originals.length) {
      grid.className = "catalog-list";
      grid.innerHTML = "";
      renderEmptyState();
      return;
    }
    empty.classList.add("hidden");

    const catToCardClass = {
      movies: "cat-movie",
      books: "cat-book",
      video: "cat-video",
      article: "cat-article",
      ideas: "cat-idea",
    };

    grid.className = "catalog-list view-originals";
    grid.innerHTML = state.originals
      .map((orig) => {
        const topicLabel = TOPIC_LABELS[orig.topic_slug] || "💡 Идеи и посты";
        const catClass = catToCardClass[orig.topic_slug] || "cat-idea";
        const dateStr = (orig.created_at || "").slice(0, 16).replace("T", " ");
        const authorHtml = orig.author ? `<span class="orig-author">${escapeHtml(orig.author)}</span>` : "";
        const sourceBtnHtml = orig.source_url ? buildSourceBadgeHtml(orig.source_url, null) : "";
        const tgUrl = buildTelegramMessageLink(orig);
        const tgBtnHtml = tgUrl
          ? `<a class="liquid-pill liquid-chat-link chat-link orig-tg-link" href="${escapeHtml(tgUrl)}" target="_blank" rel="noopener noreferrer" title="Открыть пост в Telegram" aria-label="Открыть пост в Telegram">${SVC_ICONS.telegram}</a>`
          : "";
        const hasFooter = Boolean(sourceBtnHtml || tgBtnHtml);

        const rawTrim = (orig.raw_text || "").trim();
        const extTrim = (orig.extracted_text || "").trim();
        const showExtracted = extTrim && extTrim !== rawTrim;

        return `
          <article class="orig-card cat-accent ${catClass}" data-orig-id="${orig.id}">
            <div class="orig-header">
              <span class="orig-topic-pill">${topicLabel}</span>
              ${authorHtml}
              <span class="orig-date">${escapeHtml(dateStr)}</span>
              <button type="button" class="liquid-pill liquid-delete-btn delete-btn" data-action="delete-orig" data-orig-id="${orig.id}" title="Удалить" aria-label="Удалить">${UI_ICONS.trash}</button>
            </div>
            <div class="orig-raw-text">${linkifyText(rawTrim)}</div>
            ${
              showExtracted
                ? `<div class="orig-extracted-box"><div class="orig-extracted-label">Текст из источника:</div><div class="orig-extracted-text">${escapeHtml(extTrim)}</div></div>`
                : ""
            }
            ${
              hasFooter
                ? `<div class="orig-footer"><div class="orig-footer-left">${sourceBtnHtml}</div>${tgBtnHtml}</div>`
                : ""
            }
          </article>
        `;
      })
      .join("");
  }

  // ==================== СИНХРОНИЗАЦИЯ НАВИГАЦИИ И ДАННЫХ ====================

  function setViewMode(mode) {
    if (!VALID_VIEW_MODES.includes(mode)) return;
    closeStatusPopover();
    closeRatingPopover();
    closeOpenSwipeRow();
    state.viewMode = mode;
    saveViewModeForTab(state.tab, mode);
    syncNavigationState();
    if (state.view === "catalog") {
      withViewTransition(() => renderCatalog());
    }
    haptic("selection");
  }

  function cycleViewMode() {
    const order = VALID_VIEW_MODES;
    const next = order[(order.indexOf(state.viewMode) + 1) % order.length];
    setViewMode(next);
  }

  function syncNavigationState() {
    const isOriginals = state.view === "originals";
    const isStats = state.view === "stats";
    const isCatalog = !isOriginals && !isStats;

    document.querySelectorAll("#sidebarViewSwitch .nav-btn, #mobileBottomBar [data-view]").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.view === state.view);
    });

    document.querySelectorAll("#sidebarCategoryTabs .nav-btn, #mobileCategoryTabs .tab").forEach((btn) => {
      btn.classList.toggle("active", !isStats && (btn.dataset.tab || "") === state.tab);
    });

    document.querySelectorAll("#sidebarSmartViews .nav-btn[data-smart]").forEach((btn) => {
      btn.classList.toggle("active", isCatalog && btn.dataset.smart === state.smart);
    });

    document.querySelectorAll("#viewModeSwitchDesktop .mode-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.mode === state.viewMode);
    });

    const mobModeBtn = document.getElementById("viewModeSwitchMobile");
    const mobModeIcon = document.getElementById("viewModeIconMobile");
    const modeMeta = {
      list: { icon: "list", title: "Вид: Список (нажмите для смены)" },
      posters: { icon: "posters", title: "Вид: Постеры (нажмите для смены)" },
      cards: { icon: "grid", title: "Вид: Карточки (нажмите для смены)" },
      kanban: { icon: "kanban", title: "Вид: Канбан (нажмите для смены)" },
    }[state.viewMode] || { icon: "list", title: "Вид: Список (нажмите для смены)" };
    if (mobModeIcon && UI_ICONS[modeMeta.icon]) {
      mobModeIcon.innerHTML = UI_ICONS[modeMeta.icon];
    }
    if (mobModeBtn) {
      mobModeBtn.title = modeMeta.title;
      mobModeBtn.setAttribute("aria-label", modeMeta.title);
      mobModeBtn.classList.toggle("hidden", !isCatalog);
    }

    const controlsRowEl = document.querySelector(".controls-row");
    if (controlsRowEl) controlsRowEl.classList.toggle("hidden", isStats);
    const mobCatTabsEl = document.getElementById("mobileCategoryTabs");
    if (mobCatTabsEl) mobCatTabsEl.classList.toggle("hidden", isStats);

    document.getElementById("desktopCatalogControls").classList.toggle("hidden", !isCatalog);
    const mobSortWrap = document.getElementById("mobileSortWrap");
    if (mobSortWrap) mobSortWrap.classList.toggle("hidden", !isCatalog);
    const mobSortSelect = document.getElementById("mobileSortSelect");
    if (mobSortSelect) mobSortSelect.value = state.sort;
    document.getElementById("tagBar").classList.toggle("hidden", !isCatalog);

    document.getElementById("searchInput").placeholder = isOriginals
      ? "Простой поиск по оригиналам..."
      : "Поиск по названию, автору, описанию...";

    const hasActiveFilter =
      isCatalog &&
      (state.status !== "all" ||
        state.sort !== "created" ||
        state.tags.length > 0 ||
        Boolean(state.tab) ||
        Boolean(state.smart));
    const filterDot = document.getElementById("mobileFilterDot");
    if (filterDot) filterDot.classList.toggle("hidden", !hasActiveFilter);
  }

  function formatStatsMonthLabel(ym, full = false) {
    const MONTHS_SHORT = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"];
    const MONTHS_FULL = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"];
    const m = String(ym || "").match(/^(\d{4})-(\d{2})$/);
    if (!m) return ym || "Без даты";
    const yr = m[1];
    const mIdx = Math.max(0, Math.min(11, Number(m[2]) - 1));
    return full ? `${MONTHS_FULL[mIdx]} ${yr}` : MONTHS_SHORT[mIdx];
  }

  function renderStats() {
    const container = document.getElementById("catalogContainer");
    const grid = document.getElementById("catalogGrid");
    const empty = document.getElementById("emptyState");
    if (!grid) return;
    if (container) container.classList.remove("kanban-wide");
    if (empty) empty.classList.add("hidden");
    renderLoadMoreBar();
    renderActiveSmartBanner();
    renderStatusPillsBar();
    renderBulkActionBar();

    const data = state.statsData;
    if (!data || !data.summary) return;
    const s = data.summary;
    const years = Array.isArray(data.available_years) ? data.available_years : [];
    const pctDone = s.total > 0 ? Math.round((s.done / s.total) * 100) : 0;
    updateCountLabels(`Итоги · ${s.total} зап.`, s.total);

    const yearPillsHtml = [
      `<button type="button" class="stats-year-pill ${!state.statsYear ? "active" : ""}" data-stats-year="">Всё время</button>`,
      ...years.map(
        (yr) =>
          `<button type="button" class="stats-year-pill ${String(state.statsYear) === String(yr) ? "active" : ""}" data-stats-year="${yr}">${yr}</button>`
      ),
    ].join("");

    const dist = Array.isArray(data.ratings_distribution) ? data.ratings_distribution : [];
    const maxHist = Math.max(1, ...dist.map((d) => Number(d.count || 0)));
    const histHtml = dist
      .map((d) => {
        const cnt = Number(d.count || 0);
        const hPct = cnt > 0 ? Math.max(8, Math.round((cnt / maxHist) * 100)) : 4;
        const isHigh = Number(d.rating) >= 8 && cnt > 0;
        return `
          <div class="stats-hist-col" title="Оценка ${d.rating}: ${cnt}">
            <span class="stats-hist-cnt">${cnt || ""}</span>
            <div class="stats-hist-bar ${isHigh ? "high" : ""}" style="height:${hPct}%"></div>
            <span class="stats-hist-lbl">${d.rating}</span>
          </div>
        `;
      })
      .join("");

    const monthly = Array.isArray(data.monthly) ? data.monthly : [];
    const maxMonth = Math.max(
      1,
      ...monthly.map((m) => Math.max(Number(m.added || 0), Number(m.done || 0)))
    );
    const monthlyHtml = monthly.length
      ? monthly
          .map((m) => {
            const added = Number(m.added || 0);
            const done = Number(m.done || 0);
            const addedPct = added > 0 ? Math.max(8, Math.round((added / maxMonth) * 100)) : 4;
            const donePct = done > 0 ? Math.max(8, Math.round((done / maxMonth) * 100)) : 0;
            return `
              <div class="stats-month-col" title="${escapeHtml(formatStatsMonthLabel(m.month, true))}: добавлено ${added}, готово ${done}">
                <div class="stats-month-bars">
                  <div class="stats-month-bar-added" style="height:${addedPct}%"></div>
                  ${done > 0 ? `<div class="stats-month-bar-done" style="height:${donePct}%"></div>` : ""}
                </div>
                <span class="stats-month-lbl">${escapeHtml(formatStatsMonthLabel(m.month, false))}</span>
              </div>
            `;
          })
          .join("")
      : `<div style="font-size:13px;color:var(--muted);">Пока недостаточно данных по месяцам.</div>`;

    const cats = Array.isArray(data.by_category) ? data.by_category : [];
    const maxCat = Math.max(1, ...cats.map((c) => Number(c.total || 0)));
    const catsHtml = cats
      .map((c) => {
        const wPct = c.total > 0 ? Math.max(6, Math.round((c.total / maxCat) * 100)) : 0;
        const avgStr = c.avg_rating != null ? ` · ★ ${c.avg_rating}` : "";
        return `
          <button type="button" class="stats-cat-row" data-stats-jump-tab="${escapeHtml(c.tab)}">
            <div class="stats-cat-top">
              <span class="stats-cat-name">${escapeHtml(c.label)}</span>
              <span class="stats-cat-meta">${c.done}/${c.total} готово${avgStr}</span>
            </div>
            <div class="stats-cat-track"><div class="stats-cat-fill" style="width:${wPct}%"></div></div>
          </button>
        `;
      })
      .join("");

    const topTags = Array.isArray(data.top_tags) ? data.top_tags : [];
    const maxTag = Math.max(1, ...topTags.map((t) => Number(t.count || 0)));
    const tagsHtml = topTags.length
      ? topTags
          .map((t) => {
            const wPct = Math.max(8, Math.round((t.count / maxTag) * 100));
            return `
              <button type="button" class="stats-tag-row" data-stats-jump-tag="${escapeHtml(t.tag)}">
                <div class="stats-cat-top">
                  <span class="stats-cat-name">#${escapeHtml(t.tag)}</span>
                  <span class="stats-cat-meta">${t.count}</span>
                </div>
                <div class="stats-cat-track"><div class="stats-cat-fill" style="width:${wPct}%"></div></div>
              </button>
            `;
          })
          .join("")
      : `<div style="font-size:13px;color:var(--muted);">Тегов пока нет.</div>`;

    const diary = Array.isArray(data.diary) ? data.diary : [];
    let lastDiaryMonth = "";
    const diaryHtml = diary.length
      ? diary
          .map((d) => {
            const mKey = String(d.activity_date || "").slice(0, 7);
            const hdr =
              mKey && mKey !== lastDiaryMonth
                ? `<div class="stats-diary-month">${escapeHtml(formatStatsMonthLabel(mKey, true))}</div>`
                : "";
            lastDiaryMonth = mKey;
            const thumb = d.poster_url
              ? `<img src="${escapeHtml(d.poster_url)}" alt="" loading="lazy" />`
              : `<span>${CATEGORY_EMOJI[d.category] || "📌"}</span>`;
            const stLbl = (STATUS_META[d.status] || STATUS_META.done).label;
            const subParts = [stLbl, d.creator ? d.creator : "", String(d.activity_date || "").slice(0, 10)].filter(Boolean);
            const rateHtml = d.user_rating
              ? `<span class="stats-diary-rating">★ ${Number(d.user_rating)}</span>`
              : "";
            return `
              ${hdr}
              <button type="button" class="stats-diary-row" data-stats-open-id="${d.id}">
                <div class="stats-diary-poster">${thumb}</div>
                <div class="stats-diary-info">
                  <div class="stats-diary-title">${escapeHtml(d.title_ru || "Без названия")}${d.release_year ? ` (${d.release_year})` : ""}</div>
                  <div class="stats-diary-sub">${escapeHtml(subParts.join(" · "))}</div>
                </div>
                ${rateHtml}
              </button>
            `;
          })
          .join("")
      : `<div style="font-size:13px;color:var(--muted);">Здесь появятся завершённые и оценённые вами записи.</div>`;

    grid.className = "stats-dashboard";
    grid.innerHTML = `
      <div class="stats-header">
        <div>
          <h2 class="stats-heading">Итоги и дневник</h2>
          <div class="stats-subtitle">${state.statsYear ? `Статистика за ${state.statsYear} год` : "Сводка по всей личной базе"}</div>
        </div>
        <div class="stats-year-pills">${yearPillsHtml}</div>
      </div>

      <div class="stats-kpi-grid">
        <button type="button" class="stats-kpi-card" data-stats-jump-status="all">
          <span class="stats-kpi-label">Всего записей</span>
          <span class="stats-kpi-val">${s.total}</span>
          <span class="stats-kpi-sub">Планы: ${s.planned} · В процессе: ${s.in_progress}</span>
        </button>
        <button type="button" class="stats-kpi-card" data-stats-jump-status="done">
          <span class="stats-kpi-label">Завершено</span>
          <span class="stats-kpi-val">${s.done}</span>
          <span class="stats-kpi-sub">${pctDone}% от выбранного периода</span>
        </button>
        <button type="button" class="stats-kpi-card" data-stats-jump-smart="favorites">
          <span class="stats-kpi-label">Средняя оценка</span>
          <span class="stats-kpi-val">${s.avg_user_rating != null ? `★ ${s.avg_user_rating}` : "—"}</span>
          <span class="stats-kpi-sub">Оценено записей: ${s.rated_count}</span>
        </button>
        <button type="button" class="stats-kpi-card" data-stats-jump-smart="noted">
          <span class="stats-kpi-label">С личными заметками</span>
          <span class="stats-kpi-val">${s.noted_count}</span>
          <span class="stats-kpi-sub">Во входящих: ${s.inbox}</span>
        </button>
      </div>

      <div class="stats-bento-grid">
        <section class="stats-card">
          <div class="stats-card-title">Распределение оценок (1–10)</div>
          <div class="stats-histogram">${histHtml}</div>
        </section>
        <section class="stats-card">
          <div class="stats-card-title">Активность по месяцам</div>
          <div class="stats-monthly-chart">${monthlyHtml}</div>
        </section>
      </div>

      <div class="stats-bento-grid">
        <section class="stats-card">
          <div class="stats-card-title">По категориям</div>
          <div class="stats-cat-list">${catsHtml}</div>
        </section>
        <section class="stats-card">
          <div class="stats-card-title">Топ тегов и жанров</div>
          <div class="stats-tags-grid">${tagsHtml}</div>
        </section>
      </div>

      <section class="stats-diary-section">
        <div class="stats-card-title">Дневник просмотренного и оценённого</div>
        ${diaryHtml}
      </section>
    `;
  }

  async function loadStats() {
    if (statsAbort) statsAbort.abort();
    statsAbort = new AbortController();
    const { signal } = statsAbort;

    if (!state.statsData) {
      renderSkeletonRows(4);
    }

    const params = new URLSearchParams();
    if (state.statsYear) params.set("year", String(state.statsYear));
    const qs = params.toString();

    try {
      const res = await fetch(`/api/stats${qs ? `?${qs}` : ""}`, { headers: authHeaders(), signal });
      if (signal.aborted) return;
      if (res.status === 401 || res.status === 403) {
        if (res.status === 401) localStorage.removeItem("sb_access_key");
        if (authErrorMsg && getAccessKey()) authErrorMsg.classList.remove("hidden");
        showAuthModal(res.status === 403 && Boolean(tg && tg.initData));
        return;
      }
      if (!res.ok) return;
      hideAuthModal();
      const data = await res.json();
      if (signal.aborted) return;
      state.statsData = data;
      renderStats();
    } catch (err) {
      if (err && err.name === "AbortError") return;
      throw err;
    }
  }

  async function loadOriginals() {
    if (originalsAbort) originalsAbort.abort();
    originalsAbort = new AbortController();
    const { signal } = originalsAbort;

    const params = new URLSearchParams();
    if (state.tab) params.set("tab", state.tab);
    if (state.q) params.set("q", state.q);
    try {
      const res = await fetch(`/api/originals?${params.toString()}`, { headers: authHeaders(), signal });
      if (signal.aborted) return;
      if (res.status === 401 || res.status === 403) {
        if (res.status === 401) localStorage.removeItem("sb_access_key");
        if (authErrorMsg && getAccessKey()) authErrorMsg.classList.remove("hidden");
        showAuthModal(res.status === 403 && Boolean(tg && tg.initData));
        return;
      }
      if (!res.ok) return;
      hideAuthModal();
      const data = await res.json();
      if (signal.aborted) return;
      state.originals = data.items || [];
      if (data.tg_chat_id) state.tgChatId = data.tg_chat_id;
      renderOriginals();
    } catch (err) {
      if (err && err.name === "AbortError") return;
      throw err;
    }
  }

  function isDefaultCatalogQuery() {
    return (
      state.view === "catalog" &&
      state.tab === "" &&
      state.status === "all" &&
      state.tags.length === 0 &&
      state.smart === "" &&
      state.q === "" &&
      state.sort === "created"
    );
  }

  function saveItemsCache() {
    try {
      localStorage.setItem(
        "sb_cache_items_v1",
        JSON.stringify({ items: state.items.slice(0, 120), tgChatId: state.tgChatId })
      );
    } catch {}
  }

  function clearCatalogCache() {
    try {
      localStorage.removeItem("sb_cache_items_v1");
    } catch {}
  }

  let hydratedFromCache = false;
  function tryHydrateFromCache() {
    if (hydratedFromCache || !isDefaultCatalogQuery() || state.items.length > 0) return;
    hydratedFromCache = true;
    try {
      const rawItems = localStorage.getItem("sb_cache_items_v1");
      if (rawItems) {
        const parsed = JSON.parse(rawItems);
        if (parsed && Array.isArray(parsed.items) && parsed.items.length > 0) {
          state.items = parsed.items;
          state.tgChatId = parsed.tgChatId || 0;
          state.statusCountsByTab[""] = computeStatusCounts(state.items);
          renderCatalog();
        }
      }
      const rawTags = localStorage.getItem("sb_cache_tags_v1");
      if (rawTags) {
        const parsedTags = JSON.parse(rawTags);
        if (Array.isArray(parsedTags) && parsedTags.length > 0) {
          state.allTags = parsedTags;
          renderTagBar();
        }
      }
    } catch {}
  }

  async function loadTags() {
    if (tagsAbort) tagsAbort.abort();
    tagsAbort = new AbortController();
    const { signal } = tagsAbort;

    const params = new URLSearchParams();
    if (state.tab) params.set("tab", state.tab);
    try {
      const res = await fetch(`/api/tags?${params.toString()}`, { headers: authHeaders(), signal });
      if (signal.aborted || res.status === 401 || res.status === 403 || !res.ok) return;
      const data = await res.json();
      if (signal.aborted) return;
      state.allTags = data.tags || [];
      if (!state.tab) {
        try {
          localStorage.setItem("sb_cache_tags_v1", JSON.stringify(state.allTags));
        } catch {}
      }
      renderTagBar();
      if (state.filtersSheetOpen) {
        renderFiltersSheet();
      }
    } catch (err) {
      if (err && err.name === "AbortError") return;
      throw err;
    }
  }

  async function loadItems({ append = false } = {}) {
    if (append) {
      if (!state.hasMoreItems || state.loadingMoreItems) return;
      state.loadingMoreItems = true;
      renderLoadMoreBar();
    } else {
      state.loadingMoreItems = false;
      if (itemsAbort) itemsAbort.abort();
      itemsAbort = new AbortController();
      if (state.items.length === 0) {
        renderSkeletonRows();
      }
    }
    const controller = append ? new AbortController() : itemsAbort;
    const { signal } = controller;

    const params = new URLSearchParams();
    if (state.tab) params.set("tab", state.tab);
    if (state.smart) params.set("smart", state.smart);
    if (state.status && state.status !== "all") params.set("status", state.status);
    if (state.tags.length) params.set("tag", state.tags.join(","));
    if (state.q) params.set("q", state.q);
    if (state.sort) params.set("sort", state.sort);
    params.set("limit", String(CATALOG_PAGE_SIZE));
    params.set("offset", append ? String(state.items.length) : "0");

    try {
      const res = await fetch(`/api/items?${params.toString()}`, { headers: authHeaders(), signal });
      if (signal.aborted) return;
      if (res.status === 401 || res.status === 403) {
        if (res.status === 401) localStorage.removeItem("sb_access_key");
        if (authErrorMsg && getAccessKey()) authErrorMsg.classList.remove("hidden");
        showAuthModal(res.status === 403 && Boolean(tg && tg.initData));
        return;
      }
      if (!res.ok) return;
      hideAuthModal();
      const data = await res.json();
      if (signal.aborted) return;

      const batch = data.items || [];
      if (append) {
        const seen = new Set(state.items.map((i) => Number(i.id)));
        const fresh = batch.filter((i) => !seen.has(Number(i.id)));
        state.items = [...state.items, ...fresh];
        state.itemsTotal = Number(data.total != null ? data.total : state.items.length);
        state.hasMoreItems = Boolean(data.has_more) && fresh.length > 0;
        renderCatalog({ skipDrawer: true });
      } else {
        state.items = batch;
        state.tgChatId = data.tg_chat_id || 0;
        state.itemsTotal = Number(data.total != null ? data.total : state.items.length);
        state.hasMoreItems = Boolean(data.has_more);
        if (data.status_counts) {
          state.statusCountsByTab[state.tab || ""] = data.status_counts;
        } else if (state.status === "all" && !state.tags.length && !state.q && !state.smart) {
          state.statusCountsByTab[state.tab || ""] = computeStatusCounts(state.items);
        }
        if (isDefaultCatalogQuery()) {
          saveItemsCache();
        }
        renderCatalog();
      }
    } catch (err) {
      if (err && err.name === "AbortError") return;
      throw err;
    } finally {
      if (append) {
        state.loadingMoreItems = false;
        renderLoadMoreBar();
      }
    }
  }

  function showMobileTopbar() {
    const tb = document.getElementById("topbar");
    if (tb) tb.classList.remove("topbar-hidden");
  }

  async function refreshCurrentView() {
    closeStatusPopover();
    closeRatingPopover();
    closeOpenSwipeRow();
    showMobileTopbar();
    if (state.view !== "catalog") {
      clearBulkSelection();
    }
    syncNavigationState();
    if (state.view === "originals") {
      await loadOriginals();
    } else if (state.view === "stats") {
      await loadStats();
    } else {
      tryHydrateFromCache();
      await Promise.all([loadTags(), loadItems()]);
    }
  }

  function applyPayloadToItem(target, payload) {
    if (payload.status !== undefined) target.status = payload.status;
    if (payload.user_rating !== undefined) {
      target.user_rating = payload.user_rating === 0 ? null : Number(payload.user_rating);
    }
    if (payload.title_ru !== undefined && payload.title_ru.trim()) {
      target.title_ru = payload.title_ru.trim();
    }
    if (payload.summary !== undefined) {
      target.summary = payload.summary.trim() || null;
    }
    if (payload.tags !== undefined) {
      target.tags = [...payload.tags];
    }
    if (payload.user_note !== undefined) {
      const metaObj = parseMeta(target.meta);
      if (payload.user_note.trim()) {
        metaObj.user_note = payload.user_note.trim();
      } else {
        delete metaObj.user_note;
      }
      target.meta = metaObj;
    }
  }

  async function patchItem(itemId, payload, opts = {}) {
    const numId = Number(itemId);
    const idx = state.items.findIndex((i) => Number(i.id) === numId);
    const isExternal = idx === -1 && Boolean(state.externalDrawerItem && Number(state.externalDrawerItem.id) === numId);
    const prevSnapshot =
      idx !== -1
        ? JSON.parse(JSON.stringify(state.items[idx]))
        : isExternal
        ? JSON.parse(JSON.stringify(state.externalDrawerItem))
        : null;
    const syncTags = payload.tags !== undefined;
    const syncSummary = Boolean(opts.syncSummary);
    const skipNoteInput = Boolean(opts.fromNoteAutosave);
    const canUpdateTabCounts = state.status === "all" && !state.tags.length && !state.q && !state.smart;

    function rollbackPatch() {
      if (!prevSnapshot) return;
      if (idx !== -1) {
        state.items[idx] = prevSnapshot;
        if (canUpdateTabCounts) {
          state.statusCountsByTab[state.tab || ""] = computeStatusCounts(state.items);
        }
        renderCatalog({ skipDrawer: true });
      } else if (isExternal) {
        state.externalDrawerItem = prevSnapshot;
      }
      if (Number(state.drawerItemId) === numId) {
        syncDetailDrawerInPlace(prevSnapshot, { skipNoteInput, syncTags, syncSummary });
      }
    }

    // Оптимистично обновляем UI мгновенно
    if (idx !== -1) {
      const target = state.items[idx];
      applyPayloadToItem(target, payload);
      if (canUpdateTabCounts) {
        state.statusCountsByTab[state.tab || ""] = computeStatusCounts(state.items);
      }
      renderCatalog({ skipDrawer: true });
      if (Number(state.drawerItemId) === numId) {
        syncDetailDrawerInPlace(target, { skipNoteInput, syncTags, syncSummary });
      }
    } else if (isExternal) {
      applyPayloadToItem(state.externalDrawerItem, payload);
      if (Number(state.drawerItemId) === numId) {
        syncDetailDrawerInPlace(state.externalDrawerItem, { skipNoteInput, syncTags, syncSummary });
      }
    }

    let res;
    try {
      res = await fetch(`/api/items/${numId}`, {
        method: "PATCH",
        headers: authHeaders(),
        body: JSON.stringify(payload),
        keepalive: Boolean(opts.keepalive),
      });
    } catch {
      rollbackPatch();
      return false;
    }

    if (res.status === 401 || res.status === 403) {
      rollbackPatch();
      showAuthModal(res.status === 403 && Boolean(tg && tg.initData));
      return false;
    }
    if (res.ok) {
      const updated = await res.json();
      if (state.externalDrawerItem && Number(state.externalDrawerItem.id) === numId) {
        state.externalDrawerItem = updated;
      }
      const freshIdx = state.items.findIndex((i) => Number(i.id) === numId);
      if (freshIdx !== -1) {
        state.items[freshIdx] = updated;
        if (canUpdateTabCounts) {
          state.statusCountsByTab[state.tab || ""] = computeStatusCounts(state.items);
        }
        if (isDefaultCatalogQuery()) saveItemsCache();
        renderCatalog({ skipDrawer: true });
      }
      if (Number(state.drawerItemId) === numId) {
        syncDetailDrawerInPlace(updated, { skipNoteInput, syncTags, syncSummary });
      }
      if (payload.tags !== undefined) {
        loadTags();
      }
      haptic("light");
      return true;
    }
    rollbackPatch();
    return false;
  }

  // ==================== БЕЗОПАСНОЕ УДАЛЕНИЕ С UNDO-ТОСТОМ ====================

  const undoToastEl = document.getElementById("undoToast");
  const undoToastText = document.getElementById("undoToastText");
  const undoToastBtn = document.getElementById("undoToastBtn");
  let pendingDelete = null;

  async function commitPendingDelete(entry) {
    if (!entry) return;
    if (entry.type === "orig") {
      const res = await fetch(`/api/originals/${entry.id}`, {
        method: "DELETE",
        headers: authHeaders(),
        keepalive: true,
      });
      if (res.status === 401 || res.status === 403) {
        showAuthModal(res.status === 403 && Boolean(tg && tg.initData));
        return;
      }
      if (res.ok) {
        const data = await res.json().catch(() => ({}));
        const deletedIds = new Set((data.deleted_item_ids || []).map(Number));
        if (deletedIds.size > 0) {
          state.items = state.items.filter((i) => !deletedIds.has(Number(i.id)));
          if (state.view === "catalog") renderCatalog();
        }
        clearCatalogCache();
      }
      return;
    }

    const res = await fetch(`/api/items/${entry.id}`, {
      method: "DELETE",
      headers: authHeaders(),
      keepalive: true,
    });
    if (res.status === 401 || res.status === 403) {
      showAuthModal(res.status === 403 && Boolean(tg && tg.initData));
      return;
    }
    if (res.ok) {
      clearCatalogCache();
      loadTags();
    }
  }

  function flushPendingDelete() {
    if (!pendingDelete) return;
    const entry = pendingDelete;
    pendingDelete = null;
    clearTimeout(entry.timer);
    if (undoToastEl) undoToastEl.classList.add("hidden");
    commitPendingDelete(entry);
  }

  function showUndoToast(label, entry) {
    pendingDelete = entry;
    if (undoToastText) undoToastText.textContent = label;
    if (undoToastEl) undoToastEl.classList.remove("hidden");
    entry.timer = setTimeout(() => {
      if (pendingDelete === entry) {
        flushPendingDelete();
      }
    }, 5000);
  }

  if (undoToastBtn) {
    undoToastBtn.addEventListener("click", () => {
      if (!pendingDelete) return;
      const entry = pendingDelete;
      pendingDelete = null;
      clearTimeout(entry.timer);
      if (undoToastEl) undoToastEl.classList.add("hidden");
      if (entry.type === "orig") {
        const insertAt = Math.min(entry.index, state.originals.length);
        state.originals.splice(insertAt, 0, entry.snapshot);
        renderOriginals();
      } else if (entry.external) {
        state.externalDrawerItem = entry.snapshot;
      } else {
        const insertAt = Math.min(entry.index, state.items.length);
        state.items.splice(insertAt, 0, entry.snapshot);
        if (state.status === "all" && !state.tags.length && !state.q && !state.smart) {
          state.statusCountsByTab[state.tab || ""] = computeStatusCounts(state.items);
        }
        renderCatalog();
      }
      haptic("light");
    });
  }

  window.addEventListener("pagehide", () => {
    flushPendingDelete();
    flushPendingNoteSave({ keepalive: true });
  });

  async function deleteItem(itemId) {
    const numId = Number(itemId);
    const idx = state.items.findIndex((i) => Number(i.id) === numId);
    const isExternal = idx === -1 && Boolean(state.externalDrawerItem && Number(state.externalDrawerItem.id) === numId);
    if (idx === -1 && !isExternal) return;
    flushPendingDelete();

    const snapshot = isExternal ? state.externalDrawerItem : state.items[idx];
    if (isExternal) {
      state.externalDrawerItem = null;
    } else {
      state.items.splice(idx, 1);
      if (state.status === "all" && !state.tags.length && !state.q && !state.smart) {
        state.statusCountsByTab[state.tab || ""] = computeStatusCounts(state.items);
      }
      renderCatalog();
    }
    haptic("medium");

    const shortTitle = (snapshot.title_ru || "Запись").slice(0, 28);
    showUndoToast(`«${shortTitle}» удалена`, {
      type: "item",
      id: numId,
      index: isExternal ? 0 : idx,
      external: isExternal,
      snapshot,
      timer: null,
    });
  }

  async function deleteOriginal(origId) {
    const numId = Number(origId);
    const idx = state.originals.findIndex((o) => Number(o.id) === numId);
    if (idx === -1) return;
    flushPendingDelete();

    const snapshot = state.originals[idx];
    state.originals.splice(idx, 1);
    renderOriginals();
    haptic("medium");

    showUndoToast("Оригинал удалён", {
      type: "orig",
      id: numId,
      index: idx,
      snapshot,
      timer: null,
    });
  }

  function enableCarouselTouchScroll(el) {
    if (!el) return;
    el.addEventListener("touchstart", (e) => e.stopPropagation(), { passive: true });
    el.addEventListener("touchmove", (e) => e.stopPropagation(), { passive: true });
    el.addEventListener(
      "wheel",
      (e) => {
        if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) {
          el.scrollLeft += e.deltaY;
          e.preventDefault();
        }
      },
      { passive: false }
    );
  }

  // ==================== ОБРАБОТЧИКИ СОБЫТИЙ ====================

  document.getElementById("sidebarViewSwitch").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-view]");
    if (!btn) return;
    state.view = btn.dataset.view || "catalog";
    syncStateToUrl({ push: true });
    refreshCurrentView();
  });

  const sidebarSmartViewsEl = document.getElementById("sidebarSmartViews");
  if (sidebarSmartViewsEl) {
    sidebarSmartViewsEl.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-smart]");
      if (!btn) return;
      toggleSmartView(btn.dataset.smart || "");
      haptic("selection");
    });
  }

  const activeSmartBannerEl = document.getElementById("activeSmartBanner");
  if (activeSmartBannerEl) {
    activeSmartBannerEl.addEventListener("click", (e) => {
      if (e.target.closest("#clearSmartViewBtn")) {
        toggleSmartView("");
        haptic("selection");
      }
    });
  }

  const shortcutsHelpBtnDesktop = document.getElementById("shortcutsHelpBtnDesktop");
  if (shortcutsHelpBtnDesktop) {
    shortcutsHelpBtnDesktop.addEventListener("click", () => openShortcutsModal());
  }

  document.getElementById("mobileBottomBar").addEventListener("click", (e) => {
    const viewBtn = e.target.closest("[data-view]");
    if (viewBtn) {
      state.view = viewBtn.dataset.view || "catalog";
      syncStateToUrl({ push: true });
      refreshCurrentView();
      window.scrollTo({ top: 0, behavior: "smooth" });
      haptic("selection");
      return;
    }
    if (e.target.closest("#bottomFiltersBtn")) {
      openFiltersSheet();
      return;
    }
    if (e.target.closest("#bottomSearchBtn")) {
      if (state.view === "stats") {
        state.view = "catalog";
        syncStateToUrl({ push: true });
        refreshCurrentView();
      }
      window.scrollTo({ top: 0, behavior: "smooth" });
      setTimeout(() => document.getElementById("searchInput").focus(), 180);
    }
  });

  function bindCategoryContainer(containerId) {
    const el = document.getElementById(containerId);
    if (!el) return;
    el.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-tab]");
      if (!btn) return;
      state.view = "catalog";
      state.tab = btn.dataset.tab || "";
      state.tags = [];
      state.viewMode = getViewModeForTab(state.tab);
      syncStateToUrl({ push: true });
      refreshCurrentView();
      haptic("selection");
    });
  }
  bindCategoryContainer("sidebarCategoryTabs");
  bindCategoryContainer("mobileCategoryTabs");

  document.getElementById("viewModeSwitchDesktop").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-mode]");
    if (btn) setViewMode(btn.dataset.mode);
  });
  document.getElementById("viewModeSwitchMobile").addEventListener("click", cycleViewMode);

  document.getElementById("sortSelect").addEventListener("change", (e) => {
    state.sort = e.target.value;
    const mobSort = document.getElementById("mobileSortSelect");
    if (mobSort) mobSort.value = state.sort;
    syncNavigationState();
    syncStateToUrl({ push: true });
    loadItems();
  });

  const mobileSortSelectEl = document.getElementById("mobileSortSelect");
  if (mobileSortSelectEl) {
    mobileSortSelectEl.addEventListener("change", (e) => {
      state.sort = e.target.value;
      document.getElementById("sortSelect").value = state.sort;
      syncNavigationState();
      syncStateToUrl({ push: true });
      loadItems();
    });
  }

  document.getElementById("tagBar").addEventListener("click", (e) => {
    const btn = e.target.closest(".chip");
    if (!btn) return;
    toggleTagFilter(btn.dataset.tag || "");
    haptic("selection");
  });

  document.getElementById("tagBar").addEventListener("change", (e) => {
    if (e.target.id === "moreTagsSelect") {
      if (e.target.value) {
        toggleTagFilter(e.target.value);
        e.target.value = "";
      }
    }
  });

  const searchInput = document.getElementById("searchInput");
  const searchClearBtn = document.getElementById("searchClearBtn");
  const searchWrapEl = searchInput ? searchInput.closest(".search-wrap") : null;
  let searchTimer = null;

  function syncSearchQueryState(val) {
    if (searchClearBtn) searchClearBtn.classList.toggle("hidden", !val);
    if (searchWrapEl) searchWrapEl.classList.toggle("has-query", Boolean(val));
  }

  searchInput.addEventListener("input", (e) => {
    const val = e.target.value;
    syncSearchQueryState(val);
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.q = val.trim();
      syncStateToUrl({ push: false });
      if (state.view === "originals") {
        loadOriginals();
      } else {
        loadItems();
      }
    }, 260);
  });

  searchClearBtn.addEventListener("click", () => {
    searchInput.value = "";
    syncSearchQueryState("");
    state.q = "";
    syncStateToUrl({ push: false });
    if (state.view === "originals") {
      loadOriginals();
    } else {
      loadItems();
    }
    searchInput.focus();
  });

  document.getElementById("themeToggleDesktop").addEventListener("click", cycleThemeMode);
  document.getElementById("refreshBtnDesktop").addEventListener("click", refreshCurrentView);
  document.getElementById("refreshBtnMobile").addEventListener("click", refreshCurrentView);

  const statusPillsBarEl = document.getElementById("statusPillsBar");
  if (statusPillsBarEl) {
    statusPillsBarEl.addEventListener("click", (e) => {
      if (e.target.closest("#triageBtnBar")) {
        startInboxTriage();
        return;
      }
      if (e.target.closest("#luckyBtnBar")) {
        pickRandomItem();
        return;
      }
      const stPill = e.target.closest("[data-status-pill]");
      if (stPill) {
        state.status = stPill.dataset.statusPill || "all";
        if (state.smart === "top_planned" || state.smart === "unrated_done") {
          state.smart = "";
        }
        syncNavigationState();
        syncStateToUrl({ push: true });
        withViewTransition(() => loadItems());
        haptic("selection");
      }
    });
    enableCarouselTouchScroll(statusPillsBarEl);
  }

  const catalogGridEl = document.getElementById("catalogGrid");

  // ==================== KANBAN DRAG & DROP ====================
  let draggedKanbanId = null;

  catalogGridEl.addEventListener("dragstart", (e) => {
    const card = e.target.closest(".kanban-card[data-drag-id]");
    if (!card) return;
    draggedKanbanId = Number(card.dataset.dragId);
    card.classList.add("dragging");
    if (e.dataTransfer) {
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", String(draggedKanbanId));
    }
  });

  catalogGridEl.addEventListener("dragend", (e) => {
    const card = e.target.closest(".kanban-card[data-drag-id]");
    if (card) card.classList.remove("dragging");
    draggedKanbanId = null;
    catalogGridEl.querySelectorAll(".kanban-col.drag-over").forEach((c) => c.classList.remove("drag-over"));
  });

  catalogGridEl.addEventListener("dragover", (e) => {
    if (!draggedKanbanId) return;
    const col = e.target.closest(".kanban-col[data-kanban-status]");
    if (!col) return;
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = "move";
    catalogGridEl.querySelectorAll(".kanban-col.drag-over").forEach((c) => {
      if (c !== col) c.classList.remove("drag-over");
    });
    col.classList.add("drag-over");
  });

  catalogGridEl.addEventListener("dragleave", (e) => {
    const col = e.target.closest(".kanban-col[data-kanban-status]");
    if (col && !col.contains(e.relatedTarget)) {
      col.classList.remove("drag-over");
    }
  });

  catalogGridEl.addEventListener("drop", async (e) => {
    const col = e.target.closest(".kanban-col[data-kanban-status]");
    if (!col) return;
    e.preventDefault();
    col.classList.remove("drag-over");
    const targetStatus = col.dataset.kanbanStatus;
    const dropId = draggedKanbanId || Number(e.dataTransfer && e.dataTransfer.getData("text/plain"));
    draggedKanbanId = null;
    if (dropId && targetStatus) {
      const existing = state.items.find((i) => Number(i.id) === Number(dropId));
      if (existing && (existing.status || "inbox") !== targetStatus) {
        await patchItem(dropId, { status: targetStatus });
      }
    }
  });

  // ==================== QUICK ADD MODAL ====================
  const quickAddOverlay = document.getElementById("quickAddOverlay");
  const quickAddSheet = document.getElementById("quickAddSheet");
  const quickAddForm = document.getElementById("quickAddForm");
  const quickAddInput = document.getElementById("quickAddInput");
  const quickAddTopics = document.getElementById("quickAddTopics");
  const quickAddStatus = document.getElementById("quickAddStatus");
  const quickAddSubmitBtn = document.getElementById("quickAddSubmitBtn");
  let selectedAddTopic = "auto";

  function openQuickAddModal(opts = {}) {
    closeStatusPopover();
    closeRatingPopover();
    closeOpenSwipeRow();
    closeFiltersSheet();
    closeShortcutsModal();
    closeCmdPalette();
    state.quickAddOpen = true;
    const tabMap = { movies: "movies", books: "books", video: "video", article: "article", ideas: "ideas" };
    selectedAddTopic = tabMap[state.tab] || "auto";
    if (quickAddTopics) {
      quickAddTopics.querySelectorAll("[data-add-topic]").forEach((btn) => {
        btn.classList.toggle("active", btn.dataset.addTopic === selectedAddTopic);
      });
    }
    if (opts && typeof opts.prefillText === "string" && quickAddInput) {
      quickAddInput.value = opts.prefillText;
    }
    if (quickAddStatus) {
      quickAddStatus.textContent = "";
      quickAddStatus.classList.add("hidden");
      quickAddStatus.classList.remove("error");
    }
    if (quickAddOverlay) {
      quickAddOverlay.classList.remove("hidden");
      quickAddOverlay.setAttribute("aria-hidden", "false");
    }
    syncTelegramBackButton();
    setTimeout(() => quickAddInput && quickAddInput.focus(), 60);
    haptic("light");
  }

  function closeQuickAddModal() {
    if (!state.quickAddOpen) return;
    state.quickAddOpen = false;
    if (quickAddOverlay) {
      quickAddOverlay.classList.add("hidden");
      quickAddOverlay.setAttribute("aria-hidden", "true");
    }
    syncTelegramBackButton();
  }

  const openAddDeskBtn = document.getElementById("openAddModalDesktop");
  const openAddMobBtn = document.getElementById("openAddModalMobile");
  if (openAddDeskBtn) openAddDeskBtn.addEventListener("click", () => openQuickAddModal());
  if (openAddMobBtn) openAddMobBtn.addEventListener("click", () => openQuickAddModal());
  if (document.getElementById("quickAddCloseBtn")) {
    document.getElementById("quickAddCloseBtn").addEventListener("click", closeQuickAddModal);
  }
  if (document.getElementById("quickAddCancelBtn")) {
    document.getElementById("quickAddCancelBtn").addEventListener("click", closeQuickAddModal);
  }
  if (quickAddOverlay) {
    quickAddOverlay.addEventListener("click", (e) => {
      if (e.target === quickAddOverlay) closeQuickAddModal();
    });
  }
  if (quickAddTopics) {
    quickAddTopics.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-add-topic]");
      if (!btn) return;
      selectedAddTopic = btn.dataset.addTopic || "auto";
      quickAddTopics.querySelectorAll("[data-add-topic]").forEach((b) => {
        b.classList.toggle("active", b === btn);
      });
      haptic("selection");
    });
  }
  if (quickAddForm) {
    quickAddForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const rawText = (quickAddInput ? quickAddInput.value : "").trim();
      if (!rawText) return;
      if (quickAddSubmitBtn) {
        quickAddSubmitBtn.disabled = true;
        quickAddSubmitBtn.textContent = "Обработка...";
      }
      if (quickAddStatus) {
        quickAddStatus.textContent = "Ищу данные, рейтинги и теги...";
        quickAddStatus.classList.remove("hidden", "error");
      }
      try {
        const res = await fetch("/api/items", {
          method: "POST",
          headers: authHeaders(),
          body: JSON.stringify({ text: rawText, topic: selectedAddTopic }),
        });
        if (res.status === 401 || res.status === 403) {
          closeQuickAddModal();
          showAuthModal(res.status === 403 && Boolean(tg && tg.initData));
          return;
        }
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          if (quickAddStatus) {
            quickAddStatus.textContent = data.detail || "Не удалось добавить запись.";
            quickAddStatus.classList.remove("hidden");
            quickAddStatus.classList.add("error");
          }
          return;
        }
        if (quickAddInput) quickAddInput.value = "";
        clearCatalogCache();
        closeQuickAddModal();
        state.view = "catalog";
        refreshCurrentView();
        haptic("medium");
      } catch {
        if (quickAddStatus) {
          quickAddStatus.textContent = "Ошибка сети при сохранении.";
          quickAddStatus.classList.remove("hidden");
          quickAddStatus.classList.add("error");
        }
      } finally {
        if (quickAddSubmitBtn) {
          quickAddSubmitBtn.disabled = false;
          quickAddSubmitBtn.textContent = "Добавить в базу";
        }
      }
    });
  }

  // ==================== COMMAND PALETTE (CMD+K / CTRL+K) ====================
  const cmdOverlay = document.getElementById("cmdPaletteOverlay");
  const cmdInput = document.getElementById("cmdInput");
  const cmdList = document.getElementById("cmdList");
  const cmdTrigger = document.getElementById("cmdPaletteTrigger");
  let cmdActiveIndex = 0;
  let cmdEntries = [];
  let cmdRemoteItems = [];
  let cmdRemoteQuery = "";
  let cmdRemoteLoading = false;
  let cmdSearchTimer = null;
  let cmdSearchAbort = null;

  async function fetchGlobalCmdItems(rawQuery) {
    const q = (rawQuery || "").trim();
    if (q.length < 2) {
      if (cmdSearchAbort) cmdSearchAbort.abort();
      cmdSearchAbort = null;
      cmdRemoteItems = [];
      cmdRemoteQuery = "";
      cmdRemoteLoading = false;
      renderCmdList();
      return;
    }

    if (cmdSearchAbort) cmdSearchAbort.abort();
    cmdSearchAbort = new AbortController();
    const { signal } = cmdSearchAbort;

    cmdRemoteLoading = true;
    cmdRemoteQuery = q;
    renderCmdList();

    try {
      const res = await fetch(`/api/items?q=${encodeURIComponent(q)}&limit=12`, {
        headers: authHeaders(),
        signal,
      });
      if (signal.aborted) return;
      if (res.ok) {
        const data = await res.json();
        if (signal.aborted) return;
        cmdRemoteItems = data.items || [];
      } else {
        cmdRemoteItems = [];
      }
    } catch (err) {
      if (err && err.name === "AbortError") return;
      cmdRemoteItems = [];
    } finally {
      if (!signal.aborted) {
        cmdRemoteLoading = false;
        renderCmdList();
      }
    }
  }

  function buildCmdEntries(query) {
    const rawTrimmed = (query || "").trim();
    const q = rawTrimmed.toLowerCase();
    const cleanQ = q.replace(/^#+/, "");
    const actions = [
      { id: "act-add", group: "Действия", label: "➕ Добавить запись", sub: "Клавиша N", run: () => openQuickAddModal() },
      { id: "act-triage", group: "Действия", label: "⚡ Разобрать входящие", sub: "Клавиша T", run: () => startInboxTriage() },
      { id: "act-lucky", group: "Действия", label: "🎲 Мне повезёт", sub: "Клавиша L", run: () => pickRandomItem() },
      {
        id: "act-bulk",
        group: "Действия",
        label: state.selectedIds.size > 0 ? "☑ Снять мультивыбор" : "☑ Мультивыбор записей",
        sub: "Клавиша X",
        run: () => {
          if (state.selectedIds.size > 0) {
            clearBulkSelection();
            return;
          }
          if (state.view !== "catalog") {
            state.view = "catalog";
            syncStateToUrl({ push: true });
            refreshCurrentView();
          }
          if (state.items.length > 0) {
            toggleBulkSelect(state.items[0].id);
          }
        },
      },
      { id: "act-shortcuts", group: "Действия", label: "⌨️ Горячие клавиши", sub: "Клавиша ?", run: () => openShortcutsModal() },
      {
        id: "act-stats",
        group: "Разделы",
        label: "📊 Открыть Итоги и дневник",
        sub: "",
        run: () => {
          state.view = "stats";
          syncStateToUrl({ push: true });
          refreshCurrentView();
        },
      },
      { id: "act-list", group: "Вид", label: "☰ Вид: Список", sub: "", run: () => setViewMode("list") },
      { id: "act-posters", group: "Вид", label: "🖼 Вид: Постеры", sub: "", run: () => setViewMode("posters") },
      { id: "act-cards", group: "Вид", label: "⊞ Вид: Карточки", sub: "", run: () => setViewMode("cards") },
      { id: "act-kanban", group: "Вид", label: "▥ Вид: Канбан", sub: "", run: () => setViewMode("kanban") },
      { id: "act-theme", group: "Настройки", label: "🌗 Сменить тему (Бумага / Чернила)", sub: "", run: () => cycleThemeMode() },
      ...(deferredInstallPrompt
        ? [
            {
              id: "act-install-pwa",
              group: "Настройки",
              label: "📲 Установить приложение (PWA)",
              sub: "",
              run: async () => {
                if (!deferredInstallPrompt) return;
                const promptEvt = deferredInstallPrompt;
                deferredInstallPrompt = null;
                try {
                  promptEvt.prompt();
                  await promptEvt.userChoice;
                } catch {}
              },
            },
          ]
        : []),
      ...(isTgWebApp && tg && typeof tg.requestFullscreen === "function"
        ? [
            {
              id: "act-tma-fullscreen",
              group: "Настройки",
              label: tg.isFullscreen ? "🗗 Выйти из полного экрана" : "⛶ На весь экран (Telegram)",
              sub: "",
              run: () => toggleTmaFullscreen(),
            },
          ]
        : []),
      ...(isTgWebApp && tmaHomeScreenCanAdd
        ? [
            {
              id: "act-tma-homescreen",
              group: "Настройки",
              label: "📲 Ярлык на главный экран",
              sub: "",
              run: () => triggerTmaHomeScreen(),
            },
          ]
        : []),
      {
        id: "act-cat-all",
        group: "Категории",
        label: "📚 Все записи",
        sub: "",
        run: () => {
          state.view = "catalog";
          state.tab = "";
          state.smart = "";
          state.tags = [];
          state.viewMode = getViewModeForTab("");
          syncStateToUrl({ push: true });
          refreshCurrentView();
        },
      },
      {
        id: "act-cat-movies",
        group: "Категории",
        label: "🎬 Кино и сериалы",
        sub: "",
        run: () => {
          state.view = "catalog";
          state.tab = "movies";
          state.viewMode = getViewModeForTab("movies");
          syncStateToUrl({ push: true });
          refreshCurrentView();
        },
      },
      {
        id: "act-cat-books",
        group: "Категории",
        label: "📚 Книги",
        sub: "",
        run: () => {
          state.view = "catalog";
          state.tab = "books";
          state.viewMode = getViewModeForTab("books");
          syncStateToUrl({ push: true });
          refreshCurrentView();
        },
      },
      {
        id: "act-cat-orig",
        group: "Разделы",
        label: "📥 Открыть Оригиналы",
        sub: "",
        run: () => {
          state.view = "originals";
          syncStateToUrl({ push: true });
          refreshCurrentView();
        },
      },
    ];
    const smartActions = Object.entries(SMART_VIEWS_META).map(([key, meta]) => ({
      id: `smart-${key}`,
      group: "Умные списки",
      label: meta.label,
      sub: "",
      run: () => toggleSmartView(key),
    }));

    const filteredActions = q
      ? [...actions, ...smartActions].filter((a) => a.label.toLowerCase().includes(q))
      : [...actions.slice(0, 6), ...smartActions.slice(0, 3)];

    const localIds = new Set(state.items.map((i) => Number(i.id)));
    const matchedLocal = q
      ? state.items.filter((it) => {
          const noteText = parseMeta(it.meta).user_note || "";
          const tagsText = (it.tags || []).join(" ");
          const hay = `${it.title_ru || ""} ${it.title_orig || ""} ${it.creator || ""} ${it.summary || ""} ${tagsText} ${noteText}`.toLowerCase();
          return hay.includes(q) || (cleanQ && hay.includes(cleanQ));
        })
      : [];

    const combinedItems = [];
    const seenIds = new Set();
    for (const it of matchedLocal) {
      const idNum = Number(it.id);
      if (seenIds.has(idNum)) continue;
      seenIds.add(idNum);
      combinedItems.push(it);
      if (combinedItems.length >= 12) break;
    }

    if (q.length >= 2 && cmdRemoteQuery.trim().toLowerCase() === q) {
      for (const it of cmdRemoteItems) {
        const idNum = Number(it.id);
        if (seenIds.has(idNum)) continue;
        seenIds.add(idNum);
        combinedItems.push(it);
        if (combinedItems.length >= 12) break;
      }
    }

    const itemEntries = combinedItems.map((it) => ({
      id: `item-${it.id}`,
      group: localIds.has(Number(it.id)) ? "Записи" : "Вся база",
      label: `${CATEGORY_EMOJI[it.category] || "📌"} ${it.title_ru || "Без названия"}`,
      sub: (STATUS_META[it.status] || STATUS_META.inbox).label,
      run: () => openDetailDrawer(it.id, { fallbackItem: it }),
    }));

    return [...itemEntries, ...filteredActions];
  }

  function renderCmdList() {
    if (!cmdList) return;
    const rawVal = cmdInput ? cmdInput.value.trim() : "";
    cmdEntries = buildCmdEntries(rawVal);
    if (cmdActiveIndex >= cmdEntries.length) cmdActiveIndex = Math.max(0, cmdEntries.length - 1);
    const showLoadingHint = cmdRemoteLoading && rawVal.length >= 2;
    if (!cmdEntries.length && !showLoadingHint) {
      cmdList.innerHTML = `<div class="cmd-group-label">Ничего не найдено</div>`;
      return;
    }
    let lastGroup = "";
    const entriesHtml = cmdEntries
      .map((entry, idx) => {
        const hdr = entry.group !== lastGroup ? `<div class="cmd-group-label">${escapeHtml(entry.group)}</div>` : "";
        lastGroup = entry.group;
        return `${hdr}<button type="button" class="cmd-item ${idx === cmdActiveIndex ? "active" : ""}" data-cmd-idx="${idx}"><span>${escapeHtml(entry.label)}</span><span class="cmd-item-sub">${escapeHtml(entry.sub)}</span></button>`;
      })
      .join("");
    const loadingHtml = showLoadingHint ? `<div class="cmd-loading-hint">Поиск по всей базе…</div>` : "";
    cmdList.innerHTML = entriesHtml + loadingHtml;
  }

  function openCmdPalette() {
    closeStatusPopover();
    closeRatingPopover();
    closeShortcutsModal();
    clearTimeout(cmdSearchTimer);
    if (cmdSearchAbort) cmdSearchAbort.abort();
    cmdSearchAbort = null;
    cmdRemoteItems = [];
    cmdRemoteQuery = "";
    cmdRemoteLoading = false;
    state.cmdPaletteOpen = true;
    cmdActiveIndex = 0;
    if (cmdInput) cmdInput.value = "";
    renderCmdList();
    if (cmdOverlay) {
      cmdOverlay.classList.remove("hidden");
      cmdOverlay.setAttribute("aria-hidden", "false");
    }
    syncTelegramBackButton();
    setTimeout(() => cmdInput && cmdInput.focus(), 30);
  }

  function closeCmdPalette() {
    clearTimeout(cmdSearchTimer);
    if (cmdSearchAbort) cmdSearchAbort.abort();
    cmdSearchAbort = null;
    cmdRemoteLoading = false;
    if (!state.cmdPaletteOpen) return;
    state.cmdPaletteOpen = false;
    if (cmdOverlay) {
      cmdOverlay.classList.add("hidden");
      cmdOverlay.setAttribute("aria-hidden", "true");
    }
    syncTelegramBackButton();
  }

  if (cmdTrigger) cmdTrigger.addEventListener("click", openCmdPalette);
  if (cmdOverlay) {
    cmdOverlay.addEventListener("click", (e) => {
      if (e.target === cmdOverlay) closeCmdPalette();
    });
  }
  if (cmdInput) {
    cmdInput.addEventListener("input", () => {
      cmdActiveIndex = 0;
      const val = cmdInput.value;
      renderCmdList();
      clearTimeout(cmdSearchTimer);
      cmdSearchTimer = setTimeout(() => fetchGlobalCmdItems(val), 180);
    });
    cmdInput.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        if (cmdEntries.length) {
          cmdActiveIndex = (cmdActiveIndex + 1) % cmdEntries.length;
          renderCmdList();
        }
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        if (cmdEntries.length) {
          cmdActiveIndex = (cmdActiveIndex - 1 + cmdEntries.length) % cmdEntries.length;
          renderCmdList();
        }
      } else if (e.key === "Enter") {
        e.preventDefault();
        const chosen = cmdEntries[cmdActiveIndex];
        if (chosen) {
          closeCmdPalette();
          chosen.run();
        }
      }
    });
  }
  if (cmdList) {
    cmdList.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-cmd-idx]");
      if (!btn) return;
      const entry = cmdEntries[Number(btn.dataset.cmdIdx)];
      if (entry) {
        closeCmdPalette();
        entry.run();
      }
    });
  }

  // ==================== СВАЙПЫ ШТОРОК ВНИЗ И СТРОК В МОБИЛЬНОЙ ВЕРСИИ ====================
  function bindSheetSwipeToClose(sheetEl, onClose, options = {}) {
    if (!sheetEl) return;
    let startY = 0;
    let deltaY = 0;
    let active = false;

    sheetEl.addEventListener(
      "touchstart",
      (e) => {
        if (window.innerWidth > 820 || e.touches.length !== 1) return;
        const scroller = options.scrollEl ? options.scrollEl() : null;
        const inHandle = Boolean(e.target.closest(".sheet-handle, .drawer-header"));
        if (scroller && scroller.scrollTop > 2 && !inHandle) return;
        startY = e.touches[0].clientY;
        deltaY = 0;
        active = true;
      },
      { passive: true }
    );

    sheetEl.addEventListener(
      "touchmove",
      (e) => {
        if (!active || e.touches.length !== 1) return;
        const dy = e.touches[0].clientY - startY;
        if (dy > 0) {
          deltaY = dy;
          sheetEl.style.transition = "none";
          sheetEl.style.transform = `translateY(${Math.min(dy, 260)}px)`;
        }
      },
      { passive: true }
    );

    const finish = () => {
      if (!active) return;
      active = false;
      sheetEl.style.transition = "";
      sheetEl.style.transform = "";
      if (deltaY > 75) {
        onClose();
      }
      deltaY = 0;
    };
    sheetEl.addEventListener("touchend", finish, { passive: true });
    sheetEl.addEventListener("touchcancel", finish, { passive: true });
  }

  bindSheetSwipeToClose(drawerEl, () => closeDetailDrawer({ skipTransition: true }), { scrollEl: () => drawerBody });
  bindSheetSwipeToClose(document.getElementById("filtersSheet"), closeFiltersSheet, {
    scrollEl: () => filtersSheetBody,
  });
  bindSheetSwipeToClose(quickAddSheet, closeQuickAddModal);

  (function bindMobileRowSwipe() {
    const TRAY_WIDTH = 148;
    const SNAP_THRESHOLD = 52;

    let wrapEl = null;
    let rowEl = null;
    let leftTray = null;
    let rightTray = null;
    let itemId = null;
    let startX = 0;
    let startY = 0;
    let baseOffset = 0;
    let currentX = 0;
    let locked = null;
    let snapArmed = false;
    let fullArmed = false;

    function getFullThreshold(row) {
      return Math.max(175, Math.round((row.offsetWidth || 340) * 0.48));
    }

    catalogGridEl.addEventListener(
      "touchstart",
      (e) => {
        if (window.innerWidth > 820 || state.view !== "catalog" || state.viewMode !== "list") return;
        if (state.selectedIds.size > 0) return;
        if (e.touches.length !== 1) return;
        if (e.target.closest(".swipe-tray")) return;
        const x = e.touches[0].clientX;
        if (x < 24 || x > window.innerWidth - 24) return;
        if (e.target.closest("a, button, select, option, .list-tags")) return;
        const row = e.target.closest(".list-row[data-open-id]");
        if (!row) return;
        const wrap = row.closest(".swipe-row-wrap");
        if (!wrap) return;

        if (openSwipeWrap && openSwipeWrap !== wrap) {
          closeOpenSwipeRow(wrap);
        }

        wrapEl = wrap;
        rowEl = row;
        leftTray = wrap.querySelector(".swipe-tray-left");
        rightTray = wrap.querySelector(".swipe-tray-right");
        itemId = Number(row.dataset.openId);
        startX = x;
        startY = e.touches[0].clientY;
        baseOffset = wrap.classList.contains("swipe-open-left")
          ? TRAY_WIDTH
          : wrap.classList.contains("swipe-open-right")
          ? -TRAY_WIDTH
          : 0;
        currentX = baseOffset;
        locked = null;
        snapArmed = Math.abs(baseOffset) >= SNAP_THRESHOLD;
        fullArmed = false;
      },
      { passive: true }
    );

    catalogGridEl.addEventListener(
      "touchmove",
      (e) => {
        if (!rowEl || e.touches.length !== 1) return;
        const dx = e.touches[0].clientX - startX;
        const dy = e.touches[0].clientY - startY;
        if (locked === null) {
          if (Math.abs(dx) < 12 && Math.abs(dy) < 12) return;
          if (Math.abs(dx) > Math.abs(dy) * 1.6) {
            locked = "x";
            rowEl.classList.add("swiping");
            if (leftTray) leftTray.classList.remove("interactive");
            if (rightTray) rightTray.classList.remove("interactive");
          } else {
            locked = "y";
            wrapEl = null;
            rowEl = null;
            leftTray = null;
            rightTray = null;
            return;
          }
        }
        if (locked === "x") {
          const rawTarget = baseOffset + dx;
          const maxDrag = Math.max(220, Math.round((rowEl.offsetWidth || 360) * 0.72));
          if (Math.abs(rawTarget) > TRAY_WIDTH) {
            const sign = rawTarget > 0 ? 1 : -1;
            const extra = Math.abs(rawTarget) - TRAY_WIDTH;
            currentX = sign * Math.min(maxDrag, TRAY_WIDTH + extra * 0.85);
          } else {
            currentX = rawTarget;
          }

          rowEl.style.transform = `translateX(${Math.round(currentX)}px)`;
          const fullThreshold = getFullThreshold(rowEl);

          if (leftTray) {
            leftTray.classList.toggle("visible", currentX > 8);
            leftTray.classList.toggle("full-armed", currentX >= fullThreshold);
          }
          if (rightTray) {
            rightTray.classList.toggle("visible", currentX < -8);
            rightTray.classList.toggle("full-armed", currentX <= -fullThreshold);
          }

          const fullNow = Math.abs(currentX) >= fullThreshold;
          const snapNow = Math.abs(currentX) >= SNAP_THRESHOLD;
          if (fullNow && !fullArmed) {
            fullArmed = true;
            snapArmed = true;
            haptic("medium");
          } else if (!fullNow && fullArmed) {
            fullArmed = false;
          }
          if (snapNow && !snapArmed) {
            snapArmed = true;
            haptic("light");
          } else if (!snapNow && snapArmed) {
            snapArmed = false;
          }
        }
      },
      { passive: true }
    );

    const endSwipe = () => {
      if (!rowEl || !wrapEl) return;
      const targetWrap = wrapEl;
      const targetRow = rowEl;
      const targetLeft = leftTray;
      const targetRight = rightTray;
      const targetId = itemId;
      const xEnd = currentX;
      const wasLockedX = locked === "x";
      const fullThreshold = getFullThreshold(targetRow);

      wrapEl = null;
      rowEl = null;
      leftTray = null;
      rightTray = null;
      itemId = null;
      baseOffset = 0;
      currentX = 0;
      locked = null;
      snapArmed = false;
      fullArmed = false;

      targetRow.classList.remove("swiping");
      if (wasLockedX) {
        suppressSwipeClickUntil = Date.now() + 280;
      } else {
        return;
      }
      if (!targetId) return;

      if (xEnd >= fullThreshold) {
        targetRow.style.transform = "";
        targetWrap.classList.remove("swipe-open-left", "swipe-open-right");
        if (targetLeft) targetLeft.classList.remove("visible", "interactive", "full-armed");
        if (targetRight) targetRight.classList.remove("visible", "interactive", "full-armed");
        if (openSwipeWrap === targetWrap) openSwipeWrap = null;

        const it = state.items.find((i) => Number(i.id) === targetId);
        const primaryAct = getSwipeRightActions(it ? it.status : "inbox")[0];
        if (primaryAct) {
          haptic("medium");
          patchItem(targetId, { status: primaryAct.status });
        }
        return;
      }

      if (xEnd <= -fullThreshold) {
        targetRow.style.transform = "";
        targetWrap.classList.remove("swipe-open-left", "swipe-open-right");
        if (targetLeft) targetLeft.classList.remove("visible", "interactive", "full-armed");
        if (targetRight) targetRight.classList.remove("visible", "interactive", "full-armed");
        if (openSwipeWrap === targetWrap) openSwipeWrap = null;
        deleteItem(targetId);
        return;
      }

      if (xEnd >= SNAP_THRESHOLD) {
        targetRow.style.transform = `translateX(${TRAY_WIDTH}px)`;
        targetWrap.classList.add("swipe-open-left");
        targetWrap.classList.remove("swipe-open-right");
        if (targetLeft) {
          targetLeft.classList.add("visible", "interactive");
          targetLeft.classList.remove("full-armed");
        }
        if (targetRight) targetRight.classList.remove("visible", "interactive", "full-armed");
        openSwipeWrap = targetWrap;
        return;
      }

      if (xEnd <= -SNAP_THRESHOLD) {
        targetRow.style.transform = `translateX(-${TRAY_WIDTH}px)`;
        targetWrap.classList.add("swipe-open-right");
        targetWrap.classList.remove("swipe-open-left");
        if (targetRight) {
          targetRight.classList.add("visible", "interactive");
          targetRight.classList.remove("full-armed");
        }
        if (targetLeft) targetLeft.classList.remove("visible", "interactive", "full-armed");
        openSwipeWrap = targetWrap;
        return;
      }

      targetRow.style.transform = "";
      targetWrap.classList.remove("swipe-open-left", "swipe-open-right");
      if (targetLeft) targetLeft.classList.remove("visible", "interactive", "full-armed");
      if (targetRight) targetRight.classList.remove("visible", "interactive", "full-armed");
      if (openSwipeWrap === targetWrap) openSwipeWrap = null;
    };

    catalogGridEl.addEventListener("touchend", endSwipe, { passive: true });
    catalogGridEl.addEventListener("touchcancel", endSwipe, { passive: true });
  })();

  (function bindMobileLongPressSelect() {
    let lpTimer = null;
    let lpStartX = 0;
    let lpStartY = 0;

    function cancelLongPress() {
      if (lpTimer) {
        clearTimeout(lpTimer);
        lpTimer = null;
      }
    }

    catalogGridEl.addEventListener(
      "touchstart",
      (e) => {
        cancelLongPress();
        if (window.innerWidth > 820 || state.view !== "catalog" || e.touches.length !== 1) return;
        if (e.target.closest("a, button, select, option, .swipe-tray, .list-tags")) return;
        const card = e.target.closest(
          ".list-row[data-open-id], .item-card[data-open-id], .poster-card[data-open-id], .kanban-card[data-open-id]"
        );
        if (!card) return;
        const targetId = Number(card.dataset.openId);
        if (!targetId) return;
        lpStartX = e.touches[0].clientX;
        lpStartY = e.touches[0].clientY;
        lpTimer = setTimeout(() => {
          lpTimer = null;
          closeOpenSwipeRow();
          toggleBulkSelect(targetId);
          haptic("medium");
          suppressSwipeClickUntil = Date.now() + 380;
        }, 450);
      },
      { passive: true }
    );

    catalogGridEl.addEventListener(
      "touchmove",
      (e) => {
        if (!lpTimer || e.touches.length !== 1) return;
        const dx = e.touches[0].clientX - lpStartX;
        const dy = e.touches[0].clientY - lpStartY;
        if (Math.hypot(dx, dy) > 10) cancelLongPress();
      },
      { passive: true }
    );
    catalogGridEl.addEventListener("touchend", cancelLongPress, { passive: true });
    catalogGridEl.addEventListener("touchcancel", cancelLongPress, { passive: true });
  })();

  const bulkSelectAllBtnEl = document.getElementById("bulkSelectAllBtn");
  const bulkStatusSelectEl = document.getElementById("bulkStatusSelect");
  const bulkTagBtnEl = document.getElementById("bulkTagBtn");
  const bulkTagInputEl = document.getElementById("bulkTagInput");
  const bulkTagApplyBtnEl = document.getElementById("bulkTagApplyBtn");
  const bulkDeleteBtnEl = document.getElementById("bulkDeleteBtn");
  const bulkClearBtnEl = document.getElementById("bulkClearBtn");

  if (bulkSelectAllBtnEl) {
    bulkSelectAllBtnEl.addEventListener("click", () => {
      if (state.selectedIds.size >= state.items.length && state.items.length > 0) {
        clearBulkSelection();
      } else {
        selectAllVisible();
      }
    });
  }
  if (bulkStatusSelectEl) {
    bulkStatusSelectEl.addEventListener("change", async (e) => {
      const nextSt = e.target.value;
      if (!nextSt) return;
      await runBulkAction({ status: nextSt });
      e.target.value = "";
    });
  }
  if (bulkTagBtnEl) {
    bulkTagBtnEl.addEventListener("click", () => {
      state.bulkTagOpen = !state.bulkTagOpen;
      state.bulkDeleteConfirm = false;
      renderBulkActionBar();
      if (state.bulkTagOpen && bulkTagInputEl) {
        setTimeout(() => bulkTagInputEl.focus(), 20);
      }
    });
  }
  async function submitBulkTag() {
    if (!bulkTagInputEl) return;
    const raw = bulkTagInputEl.value.trim();
    if (!raw) return;
    const ok = await runBulkAction({ add_tag: raw });
    if (ok) bulkTagInputEl.value = "";
  }
  if (bulkTagApplyBtnEl) {
    bulkTagApplyBtnEl.addEventListener("click", submitBulkTag);
  }
  if (bulkTagInputEl) {
    bulkTagInputEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        submitBulkTag();
      }
    });
  }
  if (bulkDeleteBtnEl) {
    bulkDeleteBtnEl.addEventListener("click", async () => {
      if (!state.bulkDeleteConfirm) {
        state.bulkDeleteConfirm = true;
        renderBulkActionBar();
        haptic("light");
        return;
      }
      await runBulkAction({ delete: true });
    });
  }
  if (bulkClearBtnEl) {
    bulkClearBtnEl.addEventListener("click", clearBulkSelection);
  }

  catalogGridEl.addEventListener("click", (e) => {
    if (Date.now() < suppressSwipeClickUntil) return;

    if (state.view === "stats") {
      const yrBtn = e.target.closest("[data-stats-year]");
      if (yrBtn) {
        state.statsYear = yrBtn.dataset.statsYear || "";
        syncStateToUrl({ push: true });
        loadStats();
        haptic("selection");
        return;
      }
      const tabJump = e.target.closest("[data-stats-jump-tab]");
      if (tabJump) {
        state.view = "catalog";
        state.tab = tabJump.dataset.statsJumpTab || "";
        state.smart = "";
        state.status = "all";
        state.tags = [];
        state.viewMode = getViewModeForTab(state.tab);
        syncStateToUrl({ push: true });
        refreshCurrentView();
        haptic("selection");
        return;
      }
      const stJump = e.target.closest("[data-stats-jump-status]");
      if (stJump) {
        state.view = "catalog";
        state.tab = "";
        state.smart = "";
        state.status = stJump.dataset.statsJumpStatus || "all";
        state.tags = [];
        syncStateToUrl({ push: true });
        refreshCurrentView();
        haptic("selection");
        return;
      }
      const smartJump = e.target.closest("[data-stats-jump-smart]");
      if (smartJump) {
        state.view = "catalog";
        state.tab = "";
        state.status = "all";
        state.tags = [];
        state.smart = smartJump.dataset.statsJumpSmart || "";
        syncStateToUrl({ push: true });
        refreshCurrentView();
        haptic("selection");
        return;
      }
      const tagJump = e.target.closest("[data-stats-jump-tag]");
      if (tagJump) {
        state.view = "catalog";
        state.tab = "";
        state.smart = "";
        state.status = "all";
        state.tags = [];
        toggleTagFilter(tagJump.dataset.statsJumpTag || "");
        return;
      }
      const openStatsItem = e.target.closest("[data-stats-open-id]");
      if (openStatsItem) {
        openItemById(openStatsItem.dataset.statsOpenId);
        return;
      }
    }

    const bulkCb = e.target.closest("[data-bulk-toggle]");
    if (bulkCb) {
      e.stopPropagation();
      toggleBulkSelect(bulkCb.dataset.bulkToggle, { shiftKey: e.shiftKey });
      return;
    }

    const swipeStatusBtn = e.target.closest("[data-swipe-status]");
    if (swipeStatusBtn && swipeStatusBtn.dataset.id) {
      e.stopPropagation();
      const id = Number(swipeStatusBtn.dataset.id);
      const nextSt = swipeStatusBtn.dataset.swipeStatus;
      closeOpenSwipeRow();
      haptic("selection");
      patchItem(id, { status: nextSt });
      return;
    }

    const swipeRateBtn = e.target.closest("[data-swipe-rate]");
    if (swipeRateBtn && swipeRateBtn.dataset.swipeRate) {
      e.stopPropagation();
      const id = Number(swipeRateBtn.dataset.swipeRate);
      const wrap = swipeRateBtn.closest(".swipe-row-wrap");
      const anchor = wrap
        ? wrap.querySelector(".list-mobile-actions .liquid-rating-btn") || wrap.querySelector(".list-row")
        : swipeRateBtn;
      closeOpenSwipeRow();
      if (anchor) openRatingPopover(id, anchor);
      return;
    }

    const swipeDelBtn = e.target.closest("[data-swipe-delete]");
    if (swipeDelBtn && swipeDelBtn.dataset.swipeDelete) {
      e.stopPropagation();
      const id = Number(swipeDelBtn.dataset.swipeDelete);
      closeOpenSwipeRow();
      deleteItem(id);
      return;
    }

    if (openSwipeWrap && !e.target.closest(".swipe-tray")) {
      const clickedOpenRow = openSwipeWrap.contains(e.target);
      closeOpenSwipeRow();
      if (clickedOpenRow) return;
    }

    const stBtn = e.target.closest("[data-action='status-menu']");
    if (stBtn && stBtn.dataset.id) {
      e.stopPropagation();
      openStatusPopover(stBtn.dataset.id, stBtn);
      return;
    }

    const rtBtn = e.target.closest("[data-action='rating-menu']");
    if (rtBtn && rtBtn.dataset.id) {
      e.stopPropagation();
      openRatingPopover(rtBtn.dataset.id, rtBtn);
      return;
    }

    const delBtn = e.target.closest("[data-action='delete']");
    if (delBtn && delBtn.dataset.id) {
      e.stopPropagation();
      closeStatusPopover();
      closeRatingPopover();
      deleteItem(delBtn.dataset.id);
      return;
    }

    const delOrigBtn = e.target.closest("[data-action='delete-orig']");
    if (delOrigBtn && delOrigBtn.dataset.origId) {
      e.stopPropagation();
      deleteOriginal(delOrigBtn.dataset.origId);
      return;
    }

    const expandTagsBtn = e.target.closest("[data-action='expand-tags']");
    if (expandTagsBtn && expandTagsBtn.dataset.id) {
      e.stopPropagation();
      state.expandedTagIds.add(Number(expandTagsBtn.dataset.id));
      applyMobileSingleLineTags();
      return;
    }

    const pill = e.target.closest(".genre-pill");
    if (pill) {
      e.stopPropagation();
      closeStatusPopover();
      closeRatingPopover();
      toggleTagFilter(pill.dataset.tag || "");
      haptic("selection");
      return;
    }

    if (e.target.closest("a, select, option, button")) {
      return;
    }

    const card = e.target.closest("[data-open-id]");
    if (card) {
      if (state.selectedIds.size > 0) {
        toggleBulkSelect(card.dataset.openId, { shiftKey: e.shiftKey });
        return;
      }
      openDetailDrawer(card.dataset.openId);
    }
  });

  const emptyStateActionsEl = document.getElementById("emptyStateActions");
  if (emptyStateActionsEl) {
    emptyStateActionsEl.addEventListener("click", (e) => {
      if (e.target.closest("#emptyResetFiltersBtn")) {
        state.tab = "";
        state.smart = "";
        state.status = "all";
        state.sort = "created";
        state.tags = [];
        state.q = "";
        if (searchInput) {
          searchInput.value = "";
          syncSearchQueryState("");
        }
        const deskSort = document.getElementById("sortSelect");
        if (deskSort) deskSort.value = "created";
        const mobSort = document.getElementById("mobileSortSelect");
        if (mobSort) mobSort.value = "created";
        state.viewMode = getViewModeForTab("");
        syncStateToUrl({ push: true });
        refreshCurrentView();
        haptic("selection");
        return;
      }
      if (e.target.closest("#emptyAddItemBtn")) {
        openQuickAddModal();
      }
    });
  }

  document.addEventListener("click", (e) => {
    if (!e.target.closest("#statusPopover") && !e.target.closest("[data-action='status-menu']")) {
      closeStatusPopover();
    }
    if (!e.target.closest("#ratingPopover") && !e.target.closest("[data-action='rating-menu']")) {
      closeRatingPopover();
    }
    if (openSwipeWrap && !openSwipeWrap.contains(e.target)) {
      closeOpenSwipeRow();
    }
  });

  function openShortcutsModal() {
    closeStatusPopover();
    closeRatingPopover();
    closeCmdPalette();
    closeQuickAddModal();
    closeFiltersSheet();
    state.shortcutsOpen = true;
    if (shortcutsOverlay) {
      shortcutsOverlay.classList.remove("hidden");
      shortcutsOverlay.setAttribute("aria-hidden", "false");
    }
    syncTelegramBackButton();
  }

  function closeShortcutsModal() {
    if (!state.shortcutsOpen) return;
    state.shortcutsOpen = false;
    if (shortcutsOverlay) {
      shortcutsOverlay.classList.add("hidden");
      shortcutsOverlay.setAttribute("aria-hidden", "true");
    }
    syncTelegramBackButton();
  }

  const shortcutsCloseBtn = document.getElementById("shortcutsCloseBtn");
  if (shortcutsCloseBtn) {
    shortcutsCloseBtn.addEventListener("click", closeShortcutsModal);
  }
  if (shortcutsOverlay) {
    shortcutsOverlay.addEventListener("click", (e) => {
      if (e.target === shortcutsOverlay) closeShortcutsModal();
    });
  }

  function clearListFocus() {
    state.focusedIndex = -1;
    if (catalogGridEl) {
      catalogGridEl.querySelectorAll(".kb-focused").forEach((el) => el.classList.remove("kb-focused"));
    }
  }

  function moveListFocus(delta) {
    if (!catalogGridEl || state.view !== "catalog") return;
    const nodes = Array.from(
      catalogGridEl.querySelectorAll(
        ".list-row[data-open-id], .item-card[data-open-id], .poster-card[data-open-id], .kanban-card[data-open-id]"
      )
    );
    if (!nodes.length) return;
    nodes.forEach((n) => n.classList.remove("kb-focused"));
    let nextIdx;
    if (state.focusedIndex < 0 || state.focusedIndex >= nodes.length) {
      nextIdx = delta >= 0 ? 0 : nodes.length - 1;
    } else {
      nextIdx = Math.max(0, Math.min(nodes.length - 1, state.focusedIndex + delta));
    }
    state.focusedIndex = nextIdx;
    const targetNode = nodes[nextIdx];
    targetNode.classList.add("kb-focused");
    if (typeof targetNode.scrollIntoView === "function") {
      targetNode.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }

  document.addEventListener("keydown", async (e) => {
    const keyLower = (e.key || "").toLowerCase();
    if ((e.metaKey || e.ctrlKey) && keyLower === "k") {
      e.preventDefault();
      if (state.cmdPaletteOpen) closeCmdPalette();
      else openCmdPalette();
      return;
    }

    const activeEl = document.activeElement;
    const activeTag = (activeEl && activeEl.tagName ? activeEl.tagName : "").toLowerCase();
    const isTyping =
      activeTag === "input" ||
      activeTag === "textarea" ||
      activeTag === "select" ||
      Boolean(activeEl && activeEl.isContentEditable);

    if ((e.metaKey || e.ctrlKey) && keyLower === "a" && !isTyping && state.view === "catalog" && state.selectedIds.size > 0) {
      e.preventDefault();
      selectAllVisible();
      return;
    }

    if (e.key === "Escape") {
      const lightboxOpen = posterLightbox && !posterLightbox.classList.contains("hidden");
      if (
        state.selectedIds.size > 0 &&
        !lightboxOpen &&
        state.drawerItemId === null &&
        !state.cmdPaletteOpen &&
        !state.quickAddOpen &&
        !state.shortcutsOpen &&
        !state.filtersSheetOpen
      ) {
        clearBulkSelection();
        return;
      }
      closeStatusPopover();
      closeRatingPopover();
      closeOpenSwipeRow();
      closePosterLightbox();
      closeShortcutsModal();
      closeCmdPalette();
      closeQuickAddModal();
      closeDetailDrawer();
      closeFiltersSheet();
      clearListFocus();
      return;
    }

    if (isTyping || e.isComposing) return;

    const noMod = !e.ctrlKey && !e.metaKey && !e.altKey;

    if (e.key === "?" && noMod) {
      e.preventDefault();
      if (state.shortcutsOpen) closeShortcutsModal();
      else openShortcutsModal();
      return;
    }

    if (state.drawerItemId !== null && noMod) {
      if (e.key === "ArrowLeft") {
        e.preventDefault();
        navigateDrawer(-1);
        return;
      }
      if (e.key === "ArrowRight") {
        e.preventDefault();
        navigateDrawer(1);
        return;
      }
      const statusKeys = {
        "1": "planned",
        "2": "in_progress",
        "3": "done",
        "4": "dropped",
        "0": "inbox",
      };
      if (statusKeys[e.key]) {
        e.preventDefault();
        const curId = state.drawerItemId;
        const nextSt = statusKeys[e.key];
        const wasTriage = state.triageMode;
        await patchItem(curId, { status: nextSt });
        if (wasTriage && nextSt !== "inbox") {
          advanceInboxTriage({ processed: true, currentId: curId });
        }
        return;
      }
      if (keyLower === "e" || e.code === "KeyE") {
        const editBtn = drawerBody ? drawerBody.querySelector("[data-drawer-edit-toggle]") : null;
        if (editBtn) {
          e.preventDefault();
          editBtn.click();
        }
        return;
      }
      if (keyLower === "m" || e.code === "KeyM") {
        const noteInp = document.getElementById("drawerNoteInput");
        if (noteInp) {
          e.preventDefault();
          noteInp.focus();
        }
        return;
      }
      if ((keyLower === "s" || e.code === "KeyS") && state.triageMode) {
        e.preventDefault();
        advanceInboxTriage({ processed: false, currentId: state.drawerItemId });
        return;
      }
    }

    const noModalOpen =
      !state.quickAddOpen &&
      !state.cmdPaletteOpen &&
      !state.shortcutsOpen &&
      !state.filtersSheetOpen &&
      state.drawerItemId === null;

    if (noModalOpen && noMod) {
      if (e.key === "/") {
        e.preventDefault();
        if (searchInput) searchInput.focus();
        return;
      }
      if (keyLower === "n" || e.code === "KeyN") {
        e.preventDefault();
        openQuickAddModal();
        return;
      }
      if (keyLower === "t" || e.code === "KeyT") {
        e.preventDefault();
        startInboxTriage();
        return;
      }
      if (keyLower === "l" || e.code === "KeyL") {
        e.preventDefault();
        pickRandomItem();
        return;
      }
      if (state.view === "catalog") {
        if (keyLower === "j" || e.code === "KeyJ" || e.key === "ArrowDown") {
          e.preventDefault();
          moveListFocus(1);
          return;
        }
        if (keyLower === "k" || e.code === "KeyK" || e.key === "ArrowUp") {
          e.preventDefault();
          moveListFocus(-1);
          return;
        }
        if (keyLower === "x" || e.code === "KeyX") {
          e.preventDefault();
          const focused = state.focusedIndex >= 0 && catalogGridEl ? catalogGridEl.querySelector(".kb-focused[data-open-id]") : null;
          if (focused) {
            toggleBulkSelect(focused.dataset.openId, { shiftKey: e.shiftKey });
          } else if (state.items.length > 0) {
            toggleBulkSelect(state.items[0].id);
          }
          return;
        }
        if (e.key === "Enter" && state.focusedIndex >= 0 && catalogGridEl) {
          const focused = catalogGridEl.querySelector(".kb-focused[data-open-id]");
          if (focused) {
            e.preventDefault();
            openDetailDrawer(focused.dataset.openId);
          }
        }
      }
    }
  });

  window.addEventListener("resize", () => {
    closeStatusPopover();
    closeRatingPopover();
    if (window.innerWidth > 820) showMobileTopbar();
    if (state.view === "catalog") {
      renderTagBar();
      applyMobileSingleLineTags();
    }
  });

  (function initMobileAutoHideTopbar() {
    const tb = document.getElementById("topbar");
    if (!tb) return;
    let lastScrollY = window.scrollY || 0;

    window.addEventListener(
      "scroll",
      () => {
        closeStatusPopover();
        closeRatingPopover();
        closeOpenSwipeRow();
        if (window.innerWidth > 820) {
          tb.classList.remove("topbar-hidden");
          lastScrollY = window.scrollY || 0;
          return;
        }
        const y = window.scrollY || 0;
        const isAnyOverlayOpen =
          state.drawerItemId !== null ||
          state.filtersSheetOpen ||
          state.quickAddOpen ||
          state.cmdPaletteOpen ||
          state.shortcutsOpen ||
          document.activeElement === searchInput;

        if (isAnyOverlayOpen || y < 48) {
          tb.classList.remove("topbar-hidden");
          lastScrollY = y;
          return;
        }

        const delta = y - lastScrollY;
        if (delta > 14) {
          tb.classList.add("topbar-hidden");
          lastScrollY = y;
        } else if (delta < -8) {
          tb.classList.remove("topbar-hidden");
          lastScrollY = y;
        }
      },
      { passive: true }
    );
  })();

  window.addEventListener("popstate", () => {
    const urlItemId = restoreStateFromUrl();
    syncSearchQueryState(state.q);
    if (urlItemId === null && state.drawerItemId !== null) {
      closeDetailDrawer({ skipUrlSync: true });
    }
    refreshCurrentView();
    if (urlItemId !== null && Number(state.drawerItemId) !== urlItemId) {
      openItemById(urlItemId, { skipUrlSync: true });
    }
  });

  const loadMoreBarEl = document.getElementById("loadMoreBar");
  const loadMoreBtnEl = document.getElementById("loadMoreBtn");
  if (loadMoreBtnEl) {
    loadMoreBtnEl.addEventListener("click", () => loadItems({ append: true }));
  }
  if (loadMoreBarEl && typeof IntersectionObserver === "function") {
    const loadMoreObserver = new IntersectionObserver(
      (entries) => {
        if (entries.some((en) => en.isIntersecting) && state.view === "catalog" && state.hasMoreItems && !state.loadingMoreItems) {
          loadItems({ append: true });
        }
      },
      { rootMargin: "260px" }
    );
    loadMoreObserver.observe(loadMoreBarEl);
  }

  const liveToastEl = document.getElementById("liveToast");
  const liveToastTextEl = document.getElementById("liveToastText");
  const liveToastActionBtnEl = document.getElementById("liveToastActionBtn");
  let liveToastTimer = null;
  let liveToastActionFn = null;

  function hideLiveToast() {
    clearTimeout(liveToastTimer);
    liveToastTimer = null;
    liveToastActionFn = null;
    if (liveToastEl) liveToastEl.classList.add("hidden");
    if (liveToastActionBtnEl) liveToastActionBtnEl.classList.add("hidden");
  }

  function showLiveToast(text, opts = {}) {
    const { actionLabel = "", onAction = null, durationMs = 4200 } = opts;
    clearTimeout(liveToastTimer);
    liveToastTimer = null;
    if (!liveToastEl || !liveToastTextEl) return;
    liveToastTextEl.textContent = text;
    liveToastActionFn = typeof onAction === "function" ? onAction : null;
    if (liveToastActionBtnEl) {
      if (actionLabel && liveToastActionFn) {
        liveToastActionBtnEl.textContent = actionLabel;
        liveToastActionBtnEl.classList.remove("hidden");
      } else {
        liveToastActionBtnEl.classList.add("hidden");
      }
    }
    liveToastEl.classList.remove("hidden");
    if (durationMs > 0) {
      liveToastTimer = setTimeout(hideLiveToast, durationMs);
    }
  }

  if (liveToastActionBtnEl) {
    liveToastActionBtnEl.addEventListener("click", () => {
      const fn = liveToastActionFn;
      hideLiveToast();
      if (fn) fn();
    });
  }

  async function quickIngestFromDropOrPaste(rawText) {
    const trimmed = String(rawText || "").trim();
    if (!trimmed) return;
    const preview = trimmed.length > 40 ? `${trimmed.slice(0, 40)}…` : trimmed;
    showLiveToast(`✨ Сохраняю: «${preview}»`, { durationMs: 0 });

    const tabMap = { movies: "movies", books: "books", video: "video", article: "article", ideas: "ideas" };
    const topic = tabMap[state.tab] || "auto";

    try {
      const res = await fetch("/api/items", {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ text: trimmed, topic }),
      });
      if (res.status === 401 || res.status === 403) {
        hideLiveToast();
        showAuthModal(res.status === 403 && Boolean(tg && tg.initData));
        return;
      }
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        showLiveToast(data.detail || "Не удалось сохранить запись.", { durationMs: 4200 });
        return;
      }

      clearCatalogCache();
      const savedItem = data.item || null;
      const savedTitle = (savedItem && savedItem.title_ru) || preview;
      const label = data.status === "duplicate" ? `ℹ️ Уже в базе: «${savedTitle}»` : `✅ Добавлено: «${savedTitle}»`;
      haptic("medium");
      if (state.view === "catalog") {
        refreshCurrentView();
      }
      showLiveToast(label, {
        actionLabel: savedItem && savedItem.id ? "Открыть" : "",
        onAction: savedItem && savedItem.id ? () => openItemById(savedItem.id, { fallbackItem: savedItem }) : null,
        durationMs: 4500,
      });
    } catch {
      showLiveToast("Ошибка сети при сохранении.", { durationMs: 4200 });
    }
  }

  document.addEventListener("paste", (e) => {
    if (authModal && !authModal.classList.contains("hidden")) return;
    if (
      state.quickAddOpen ||
      state.cmdPaletteOpen ||
      state.shortcutsOpen ||
      state.filtersSheetOpen ||
      state.drawerItemId !== null
    ) {
      return;
    }
    const activeEl = document.activeElement;
    const activeTag = (activeEl && activeEl.tagName ? activeEl.tagName : "").toLowerCase();
    const isTyping =
      activeTag === "input" ||
      activeTag === "textarea" ||
      activeTag === "select" ||
      Boolean(activeEl && activeEl.isContentEditable);
    if (isTyping) return;

    const rawText =
      e.clipboardData && typeof e.clipboardData.getData === "function"
        ? (e.clipboardData.getData("text/plain") || "").trim()
        : "";
    if (!rawText) return;
    e.preventDefault();
    quickIngestFromDropOrPaste(rawText);
  });

  const globalDropOverlayEl = document.getElementById("globalDropOverlay");
  let globalDragDepth = 0;

  function isExternalTextDrag(e) {
    if (draggedKanbanId !== null) return false;
    if (authModal && !authModal.classList.contains("hidden")) return false;
    const dt = e.dataTransfer;
    if (!dt || !dt.types) return false;
    const types = Array.from(dt.types);
    return types.includes("text/uri-list") || types.includes("text/plain");
  }

  function hideGlobalDropOverlay() {
    globalDragDepth = 0;
    if (globalDropOverlayEl) {
      globalDropOverlayEl.classList.add("hidden");
      globalDropOverlayEl.setAttribute("aria-hidden", "true");
    }
  }

  window.addEventListener("dragenter", (e) => {
    if (!isExternalTextDrag(e)) return;
    e.preventDefault();
    globalDragDepth += 1;
    if (globalDropOverlayEl) {
      globalDropOverlayEl.classList.remove("hidden");
      globalDropOverlayEl.setAttribute("aria-hidden", "false");
    }
  });

  window.addEventListener("dragover", (e) => {
    if (!isExternalTextDrag(e)) return;
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = "copy";
  });

  window.addEventListener("dragleave", () => {
    if (globalDragDepth <= 0) return;
    globalDragDepth -= 1;
    if (globalDragDepth === 0) hideGlobalDropOverlay();
  });

  window.addEventListener("drop", (e) => {
    const active = globalDragDepth > 0 || isExternalTextDrag(e);
    if (!active) return;
    e.preventDefault();
    hideGlobalDropOverlay();
    const dt = e.dataTransfer;
    const raw = dt ? (dt.getData("text/uri-list") || dt.getData("text/plain") || "").trim() : "";
    if (raw) {
      quickIngestFromDropOrPaste(raw);
    }
  });

  window.addEventListener("blur", hideGlobalDropOverlay);

  (function initPullToRefresh() {
    const indicatorEl = document.getElementById("pullRefreshIndicator");
    const textEl = document.getElementById("pullRefreshText");
    if (!indicatorEl || !textEl) return;

    const TRIGGER_PX = 56;
    let startX = 0;
    let startY = 0;
    let pulling = false;
    let armed = false;
    let ptrRefreshing = false;
    let pullDist = 0;

    function resetIndicator() {
      pulling = false;
      armed = false;
      pullDist = 0;
      indicatorEl.classList.remove("pulling");
      if (!ptrRefreshing) {
        indicatorEl.style.height = "0px";
        textEl.textContent = "Потяните для обновления";
      }
    }

    document.addEventListener(
      "touchstart",
      (e) => {
        if (window.innerWidth > 820 || ptrRefreshing || e.touches.length !== 1) return;
        if ((window.scrollY || 0) > 2 || openSwipeWrap) return;
        const anyOverlay =
          state.drawerItemId !== null ||
          state.filtersSheetOpen ||
          state.quickAddOpen ||
          state.cmdPaletteOpen ||
          state.shortcutsOpen ||
          (authModal && !authModal.classList.contains("hidden"));
        if (anyOverlay) return;
        if (e.target.closest("#statusPillsBar, #tagBar, #mobileCategoryTabs, input, textarea, select")) return;
        startX = e.touches[0].clientX;
        startY = e.touches[0].clientY;
        pullDist = 0;
        pulling = true;
        armed = false;
      },
      { passive: true }
    );

    document.addEventListener(
      "touchmove",
      (e) => {
        if (!pulling || ptrRefreshing || e.touches.length !== 1) return;
        const dx = e.touches[0].clientX - startX;
        const dy = e.touches[0].clientY - startY;
        if (dy <= 0 || Math.abs(dx) > Math.abs(dy)) {
          if (pullDist === 0 && dy < -8) pulling = false;
          return;
        }
        if ((window.scrollY || 0) > 2) {
          resetIndicator();
          return;
        }
        if (dy < 14) return;
        pullDist = Math.min(84, Math.round((dy - 14) * 0.55));
        indicatorEl.classList.add("pulling");
        indicatorEl.style.height = `${pullDist}px`;
        const isArmedNow = pullDist >= TRIGGER_PX;
        if (isArmedNow && !armed) {
          armed = true;
          haptic("light");
        } else if (!isArmedNow && armed) {
          armed = false;
        }
        textEl.textContent = armed ? "Отпустите для обновления" : "Потяните для обновления";
      },
      { passive: true }
    );

    async function endPull() {
      if (!pulling) return;
      const shouldRefresh = armed && !ptrRefreshing;
      pulling = false;
      armed = false;
      pullDist = 0;
      indicatorEl.classList.remove("pulling");

      if (!shouldRefresh) {
        indicatorEl.style.height = "0px";
        textEl.textContent = "Потяните для обновления";
        return;
      }

      ptrRefreshing = true;
      indicatorEl.classList.add("refreshing");
      indicatorEl.style.height = "44px";
      textEl.textContent = "Обновление...";
      try {
        await refreshCurrentView();
      } catch {} finally {
        ptrRefreshing = false;
        indicatorEl.classList.remove("refreshing");
        indicatorEl.style.height = "0px";
        textEl.textContent = "Потяните для обновления";
      }
    }

    document.addEventListener("touchend", endPull, { passive: true });
    document.addEventListener("touchcancel", endPull, { passive: true });
  })();

  enableCarouselTouchScroll(document.getElementById("mobileCategoryTabs"));
  enableCarouselTouchScroll(document.getElementById("tagBar"));

  hydrateIcons();
  applyTheme();
  const initialItemId = restoreStateFromUrl();
  syncSearchQueryState(state.q);
  hydrateFromTgCloudStorage();
  refreshCurrentView();
  if (initialItemId !== null) {
    openItemById(initialItemId, { skipUrlSync: true });
  }
})();
