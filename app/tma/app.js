(() => {
  const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  if (tg) {
    try {
      tg.ready();
      tg.expand();
    } catch {}
  }

  // Извлекаем ключ доступа из query-параметров (?key=...) и сохраняем в localStorage
  const urlParams = new URLSearchParams(window.location.search);
  const keyParam = urlParams.get("key");
  if (keyParam) {
    localStorage.setItem("sb_access_key", keyParam.trim());
    urlParams.delete("key");
    const cleanSearch = urlParams.toString();
    const cleanUrl = window.location.pathname + (cleanSearch ? `?${cleanSearch}` : "") + window.location.hash;
    window.history.replaceState({}, "", cleanUrl);
  }

  function getAccessKey() {
    return localStorage.getItem("sb_access_key") || "";
  }

  const isTgWebApp = Boolean(tg && tg.initData);

  const UI_ICONS = {
    library: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m16 6 4 14"/><path d="M12 6v14"/><path d="M8 8v12"/><path d="M4 4v16"/></svg>`,
    inbox: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/></svg>`,
    refresh: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/></svg>`,
    logout: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" x2="9" y1="12" y2="12"/></svg>`,
    search: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>`,
    sliders: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="4" x2="4" y1="21" y2="14"/><line x1="4" x2="4" y1="10" y2="3"/><line x1="12" x2="12" y1="21" y2="12"/><line x1="12" x2="12" y1="8" y2="3"/><line x1="20" x2="20" y1="21" y2="16"/><line x1="20" x2="20" y1="12" y2="3"/><line x1="2" x2="6" y1="14" y2="14"/><line x1="10" x2="14" y1="8" y2="8"/><line x1="18" x2="22" y1="16" y2="16"/></svg>`,
    list: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="8" x2="21" y1="6" y2="6"/><line x1="8" x2="21" y1="12" y2="12"/><line x1="8" x2="21" y1="18" y2="18"/><line x1="3" x2="3.01" y1="6" y2="6"/><line x1="3" x2="3.01" y1="12" y2="12"/><line x1="3" x2="3.01" y1="18" y2="18"/></svg>`,
    grid: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="7" height="7" x="3" y="3" rx="1"/><rect width="7" height="7" x="14" y="3" rx="1"/><rect width="7" height="7" x="14" y="14" rx="1"/><rect width="7" height="7" x="3" y="14" rx="1"/></svg>`,
    kanban: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="18" x="3" y="3" rx="2"/><path d="M8 7v7"/><path d="M12 7v4"/><path d="M16 7v9"/></svg>`,
    sun: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/></svg>`,
    moon: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/></svg>`,
    auto: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 3v18"/><path d="M12 8l5-3"/><path d="M12 13l6-3.5"/><path d="M12 18l5-3"/></svg>`,
    star: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l2.8 5.7 6.2.9-4.5 4.4 1.1 6.2L12 17.3l-5.6 2.9 1.1-6.2L3 9.6l6.2-.9L12 3Z"/></svg>`,
    starFilled: `<svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"><path d="M12 3l2.8 5.7 6.2.9-4.5 4.4 1.1 6.2L12 17.3l-5.6 2.9 1.1-6.2L3 9.6l6.2-.9L12 3Z"/></svg>`,
    trash: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12"/><path d="M9 7V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v3"/></svg>`,
    chevronDown: `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round"><path d="m7 10 5 5 5-5"/></svg>`,
  };

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

  const state = {
    view: "catalog",
    viewMode: ["list", "cards", "kanban"].includes(savedViewMode) ? savedViewMode : "list",
    themeMode: ["auto", "light", "dark"].includes(savedThemeMode)
      ? savedThemeMode
      : tg && tg.colorScheme
      ? "auto"
      : "light",
    tab: "",
    status: "all",
    tag: "",
    q: "",
    sort: "created",
    items: [],
    originals: [],
    allTags: [],
    tgChatId: 0,
    drawerItemId: null,
    drawerConfirmDelete: false,
    statusPopoverItemId: null,
    filtersSheetOpen: false,
  };

  let itemsAbort = null;
  let tagsAbort = null;
  let originalsAbort = null;

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
    const mobIcon = document.getElementById("themeIconMobile");
    if (deskIcon) deskIcon.innerHTML = UI_ICONS[iconKey];
    if (deskLabel) deskLabel.textContent = labelText;
    if (mobIcon) mobIcon.innerHTML = UI_ICONS[iconKey];

    if (tg) {
      const bgHex = effective === "dark" ? "#171513" : "#fbf8f3";
      try {
        if (typeof tg.setHeaderColor === "function") tg.setHeaderColor(bgHex);
        if (typeof tg.setBackgroundColor === "function") tg.setBackgroundColor(bgHex);
      } catch {}
    }
  }

  function cycleThemeMode() {
    if (tg && tg.colorScheme) {
      const order = ["auto", "light", "dark"];
      state.themeMode = order[(order.indexOf(state.themeMode) + 1) % order.length];
    } else {
      state.themeMode = resolveEffectiveTheme() === "dark" ? "light" : "dark";
    }
    localStorage.setItem("sb_theme_mode", state.themeMode);
    applyTheme();
    haptic("selection");
  }

  if (tg && typeof tg.onEvent === "function") {
    try {
      tg.onEvent("themeChanged", () => {
        if (state.themeMode === "auto") {
          applyTheme();
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

  function hideAuthModal() {
    if (authModal) authModal.classList.add("hidden");
    if (authErrorMsg) authErrorMsg.classList.add("hidden");
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
      if (rFl != null) {
        badges.push(
          `<a class="rating-badge ${badgeTone(rFl, 10)}" href="${uFl}" target="_blank" rel="noopener noreferrer">${BRAND_BADGES.fantlab}<span>${rFl}</span></a>`
        );
      }
      const rGr = meta.rating_goodreads ?? item.rating_imdb;
      const uGr = meta.url_goodreads || "#";
      if (rGr != null) {
        badges.push(
          `<a class="rating-badge ${badgeTone(rGr, 5)}" href="${uGr}" target="_blank" rel="noopener noreferrer">${BRAND_BADGES.goodreads}<span>${rGr}</span></a>`
        );
      }
      if (!compact && meta.info_link) {
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
      if (!compact && meta.rating_tmdb != null) {
        const tmdbType = item.category === "series" ? "tv" : "movie";
        const url = meta.tmdb_id ? `https://www.themoviedb.org/${tmdbType}/${meta.tmdb_id}` : "#";
        badges.push(
          `<a class="rating-badge ${badgeTone(meta.rating_tmdb, 10)}" href="${url}" target="_blank" rel="noopener noreferrer">${BRAND_BADGES.tmdb}<span>${meta.rating_tmdb}</span></a>`
        );
      }
      if (item.rating_rt != null || (!compact && item.url_rt)) {
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

  function openStatusPopover(itemId, anchorBtn) {
    if (!statusPopoverEl) return;
    const numId = Number(itemId);
    if (state.statusPopoverItemId === numId) {
      closeStatusPopover();
      return;
    }

    const item = state.items.find((i) => Number(i.id) === numId);
    if (!item) return;

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

  function buildCardActionsHtml(item, variant = "") {
    const stMeta = STATUS_META[item.status] || STATUS_META.inbox;
    const isStatusOpen = state.statusPopoverItemId === Number(item.id);

    const currentRating = item.user_rating || 0;
    const ratingOptions = [
      `<option value="0" ${currentRating === 0 ? "selected" : ""}>Оценка</option>`,
    ];
    for (let r = 10; r >= 1; r -= 1) {
      ratingOptions.push(
        `<option value="${r}" ${currentRating === r ? "selected" : ""}>${r}</option>`
      );
    }

    const delBtnHtml = `<button type="button" class="liquid-pill liquid-delete-btn delete-btn" data-action="delete" data-id="${item.id}" title="Удалить запись" aria-label="Удалить запись">${UI_ICONS.trash}</button>`;
    const starIcon = currentRating ? UI_ICONS.starFilled : UI_ICONS.star;
    const cls = variant ? `card-actions ${variant}` : "card-actions";

    return `
      <div class="${cls}">
        <button type="button" class="liquid-pill liquid-status-btn status-select ${isStatusOpen ? "open" : ""}" data-action="status-menu" data-id="${item.id}" aria-haspopup="listbox" aria-expanded="${isStatusOpen ? "true" : "false"}" aria-label="Статус">
          <span class="pill-st-ico" style="color:${stMeta.dot};">${stMeta.svg}</span>
          <span>${escapeHtml(stMeta.label)}</span>
          <span class="pill-st-chev">${UI_ICONS.chevronDown}</span>
        </button>
        <div class="liquid-pill liquid-select-wrap ${currentRating ? "has-rating" : ""}">
          <span class="pill-ico star-ico">${starIcon}</span>
          <select class="user-rating-select" data-action="rating" data-id="${item.id}" aria-label="Моя оценка">
            ${ratingOptions.join("")}
          </select>
          <span class="pill-chevron">${UI_ICONS.chevronDown}</span>
        </div>
        <span class="card-actions-right">
          ${delBtnHtml}
        </span>
      </div>
    `;
  }

  // ==================== ДЕТАЛЬНАЯ ШТОРКА (DETAIL DRAWER) ====================

  const drawerOverlay = document.getElementById("detailDrawerOverlay");
  const drawerBody = document.getElementById("drawerBody");
  const drawerCategoryLabel = document.getElementById("drawerCategoryLabel");

  function syncTelegramBackButton() {
    if (!tg || !tg.BackButton) return;
    try {
      if (state.drawerItemId !== null || state.filtersSheetOpen) {
        tg.BackButton.show();
      } else {
        tg.BackButton.hide();
      }
    } catch {}
  }

  if (tg && tg.BackButton) {
    try {
      tg.BackButton.onClick(() => {
        if (state.drawerItemId !== null) {
          closeDetailDrawer();
        } else if (state.filtersSheetOpen) {
          closeFiltersSheet();
        }
      });
    } catch {}
  }

  function renderDetailDrawer() {
    if (state.drawerItemId === null) {
      drawerOverlay.classList.add("hidden");
      drawerOverlay.setAttribute("aria-hidden", "true");
      drawerBody.innerHTML = "";
      syncTelegramBackButton();
      return;
    }

    const item = state.items.find((i) => Number(i.id) === Number(state.drawerItemId));
    if (!item) {
      closeDetailDrawer();
      return;
    }

    const emoji = CATEGORY_EMOJI[item.category] || "📌";
    drawerCategoryLabel.textContent = CATEGORY_TITLES[item.category] || "Запись";

    const posterHtml = item.poster_url
      ? `<img src="${escapeHtml(item.poster_url)}" alt="" />`
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
    const creatorHtml = subParts.length ? `<div class="drawer-creator">${subParts.join(" · ")}</div>` : "";

    const ratingsHtml = buildRatingsHtml(item, { compact: false, includeSources: true });
    const allTags = [...(item.genres || []), ...(item.tags || [])];
    const tagsHtml = allTags.length
      ? `
        <div class="drawer-section">
          <div class="drawer-section-title">Жанры и теги</div>
          <div class="genres-line">
            ${allTags.map((g) => `<span class="genre-pill" data-drawer-tag="${escapeHtml(g)}">#${escapeHtml(g)}</span>`).join("")}
          </div>
        </div>
      `
      : "";

    const summaryHtml = item.summary
      ? `
        <div class="drawer-section">
          <div class="drawer-section-title">Описание и заметка</div>
          <div class="drawer-summary">${linkifyText(item.summary)}</div>
        </div>
      `
      : "";

    const statusOptions = Object.entries(STATUS_META)
      .map(([k, v]) => `<option value="${k}" ${item.status === k ? "selected" : ""}>${escapeHtml(v.label)}</option>`)
      .join("");

    const ratingOptions = [0, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1]
      .map((val) => {
        const selected = (item.user_rating || 0) === val ? "selected" : "";
        const label = val === 0 ? "Без оценки" : `★ ${val}`;
        return `<option value="${val}" ${selected}>${label}</option>`;
      })
      .join("");

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

    drawerBody.innerHTML = `
      <div class="drawer-hero">
        <div class="drawer-poster">${posterHtml}</div>
        <div style="min-width:0;flex:1;">
          <h2 class="drawer-title" id="drawerTitle">${escapeHtml(item.title_ru)}${yearStr}</h2>
          ${origLine}
          ${creatorHtml}
        </div>
      </div>

      ${ratingsHtml ? `<div class="ratings-bar">${ratingsHtml}</div>` : ""}

      <div class="drawer-section">
        <div class="drawer-controls-grid">
          <div class="drawer-field">
            <label for="drawerStatusSelect">Статус</label>
            <select id="drawerStatusSelect" class="drawer-select" data-drawer-status="${item.id}">
              ${statusOptions}
            </select>
          </div>
          <div class="drawer-field">
            <label for="drawerRatingSelect">Моя оценка</label>
            <select id="drawerRatingSelect" class="drawer-select" data-drawer-rating="${item.id}">
              ${ratingOptions}
            </select>
          </div>
        </div>
      </div>

      ${summaryHtml}
      ${tagsHtml}

      <div class="drawer-actions-footer">
        ${chatHtml}
        ${deleteFooterHtml}
      </div>
    `;

    drawerOverlay.classList.remove("hidden");
    drawerOverlay.setAttribute("aria-hidden", "false");
    syncTelegramBackButton();
  }

  function openDetailDrawer(itemId) {
    closeStatusPopover();
    state.drawerItemId = Number(itemId);
    state.drawerConfirmDelete = false;
    renderDetailDrawer();
    haptic("light");
  }

  function closeDetailDrawer() {
    if (state.drawerItemId === null) return;
    state.drawerItemId = null;
    state.drawerConfirmDelete = false;
    renderDetailDrawer();
  }

  document.getElementById("drawerCloseBtn").addEventListener("click", closeDetailDrawer);
  drawerOverlay.addEventListener("click", (e) => {
    if (e.target === drawerOverlay) closeDetailDrawer();
  });

  drawerBody.addEventListener("change", async (e) => {
    const stSel = e.target.closest("[data-drawer-status]");
    if (stSel) {
      await patchItem(stSel.dataset.drawerStatus, { status: stSel.value });
      return;
    }
    const rtSel = e.target.closest("[data-drawer-rating]");
    if (rtSel) {
      await patchItem(rtSel.dataset.drawerRating, { user_rating: Number(rtSel.value) });
    }
  });

  drawerBody.addEventListener("click", async (e) => {
    const tagEl = e.target.closest("[data-drawer-tag]");
    if (tagEl) {
      state.tag = tagEl.dataset.drawerTag || "";
      closeDetailDrawer();
      renderTagBar();
      loadItems();
      return;
    }

    if (e.target.closest("[data-drawer-delete-ask]")) {
      state.drawerConfirmDelete = true;
      renderDetailDrawer();
      return;
    }

    if (e.target.closest("[data-drawer-delete-cancel]")) {
      state.drawerConfirmDelete = false;
      renderDetailDrawer();
      return;
    }

    const delConfirm = e.target.closest("[data-drawer-delete-confirm]");
    if (delConfirm) {
      const id = delConfirm.dataset.drawerDeleteConfirm;
      closeDetailDrawer();
      await deleteItem(id);
    }
  });

  // ==================== МОБИЛЬНАЯ ШТОРКА ФИЛЬТРОВ ====================

  const filtersSheetOverlay = document.getElementById("filtersSheetOverlay");
  const filtersSheetBody = document.getElementById("filtersSheetBody");

  function renderFiltersSheet() {
    const statusOpts = [
      { v: "all", l: "Все" },
      { v: "inbox", l: "📥 Входящие" },
      { v: "planned", l: "📌 В планах" },
      { v: "in_progress", l: "▶️ В процессе" },
      { v: "done", l: "✅ Готово" },
      { v: "dropped", l: "🚫 Брошено" },
    ];
    const sortOpts = [
      { v: "created", l: "По дате ↓" },
      { v: "imdb", l: "IMDb / Goodreads ↓" },
      { v: "kp", l: "КП / FantLab ↓" },
      { v: "rt", l: "Rotten Tomatoes ↓" },
      { v: "user", l: "Моя оценка ↓" },
    ];
    const modeOpts = [
      { v: "list", l: "☰ Список" },
      { v: "cards", l: "⊞ Карточки" },
      { v: "kanban", l: "▥ Канбан" },
    ];

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

      ${
        state.view === "catalog"
          ? `
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

        <button type="button" class="confirm-cancel-btn" id="sheetResetFiltersBtn" style="width:100%;padding:10px;">
          Сбросить фильтры
        </button>
      `
          : `<div class="drawer-section"><p style="font-size:13.5px;color:var(--muted);">Фильтры по статусу, сортировке и режимам отображения доступны в разделе «Каталог».</p></div>`
      }
    `;
  }

  function openFiltersSheet() {
    closeStatusPopover();
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

  filtersSheetBody.addEventListener("click", (e) => {
    const modeBtn = e.target.closest("[data-sheet-mode]");
    if (modeBtn) {
      setViewMode(modeBtn.dataset.sheetMode);
      renderFiltersSheet();
      return;
    }

    const stBtn = e.target.closest("[data-sheet-status]");
    if (stBtn) {
      state.status = stBtn.dataset.sheetStatus;
      document.getElementById("statusFilterSelect").value = state.status;
      syncNavigationState();
      renderFiltersSheet();
      loadItems();
      return;
    }

    const sortBtn = e.target.closest("[data-sheet-sort]");
    if (sortBtn) {
      state.sort = sortBtn.dataset.sheetSort;
      document.getElementById("sortSelect").value = state.sort;
      syncNavigationState();
      renderFiltersSheet();
      loadItems();
      return;
    }

    if (e.target.id === "sheetResetFiltersBtn") {
      state.status = "all";
      state.sort = "created";
      state.tag = "";
      document.getElementById("statusFilterSelect").value = "all";
      document.getElementById("sortSelect").value = "created";
      syncNavigationState();
      renderTagBar();
      renderFiltersSheet();
      loadItems();
    }
  });

  // ==================== ТЕГИ И РЕНДЕР КАТАЛОГА (LIST / CARDS / KANBAN) ====================

  function renderTagBar() {
    const container = document.getElementById("tagBar");
    const sorted = [...state.allTags].sort((a, b) => b.count - a.count || a.tag.localeCompare(b.tag));
    if (!sorted.length) {
      container.innerHTML = "";
      return;
    }

    const isMobile = window.innerWidth <= 820;
    const maxInline = isMobile ? 7 : 12;

    let inlineTags = sorted.slice(0, maxInline);
    const overflowTags = sorted.slice(maxInline);

    if (state.tag && !inlineTags.some((t) => t.tag === state.tag)) {
      const activeIdx = overflowTags.findIndex((t) => t.tag === state.tag);
      if (activeIdx !== -1) {
        const [activeItem] = overflowTags.splice(activeIdx, 1);
        inlineTags.push(activeItem);
      }
    }

    let html = `<button type="button" class="chip ${state.tag === "" ? "active" : ""}" data-tag="">Все теги</button>`;
    inlineTags.forEach((t) => {
      const isAct = state.tag === t.tag ? "active" : "";
      html += `<button type="button" class="chip ${isAct}" data-tag="${escapeHtml(t.tag)}">${escapeHtml(t.tag)} (${t.count})</button>`;
    });

    if (overflowTags.length > 0) {
      const selectedInOverflow = overflowTags.some((t) => t.tag === state.tag);
      html += `<select id="moreTagsSelect" class="more-tags-select ${selectedInOverflow ? "active" : ""}">`;
      html += `<option value="">Ещё (${overflowTags.length})...</option>`;
      overflowTags.forEach((t) => {
        const sel = state.tag === t.tag ? "selected" : "";
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

  function renderListRow(item) {
    const emoji = CATEGORY_EMOJI[item.category] || "📌";
    const catClass = `cat-${escapeHtml(item.category || "idea")}`;
    const posterHtml = item.poster_url
      ? `<img src="${escapeHtml(item.poster_url)}" alt="" loading="lazy" />`
      : `<span>${emoji}</span>`;

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
    const ratingsHtml = buildRatingsHtml(item, { compact: true, includeSources: false });
    const allTags = [...(item.genres || []), ...(item.tags || [])].slice(0, 4);
    const tagsHtml = allTags.length
      ? `<div class="list-tags">${allTags
          .map((g) => `<span class="genre-pill list-tag-pill" data-tag="${escapeHtml(g)}">#${escapeHtml(g)}</span>`)
          .join("")}</div>`
      : "";
    const cornerSourceHtml = buildCornerSourceHtml(item);
    const desktopActionsHtml = buildCardActionsHtml(item, "list-actions");
    const mobileActionsHtml = buildCardActionsHtml(item);

    return `
      <article class="list-row cat-accent ${catClass}" data-open-id="${item.id}">
        <div class="list-poster">${posterHtml}</div>
        <div class="list-main">
          <div class="list-head-row">
            <div class="list-title-line">
              <span class="list-title">${escapeHtml(item.title_ru)}</span>
              ${yearHtml}
              ${origHtml}
            </div>
            ${cornerSourceHtml}
          </div>
          ${subParts.length ? `<div class="list-subline">${subParts.join(" · ")}</div>` : ""}
          ${ratingsHtml ? `<div class="list-ratings">${ratingsHtml}</div>` : ""}
          ${tagsHtml}
        </div>
        <div class="list-right">
          ${desktopActionsHtml}
        </div>
        <div class="list-mobile-footer">
          ${mobileActionsHtml}
        </div>
      </article>
    `;
  }

  function renderEditorialCard(item) {
    const emoji = CATEGORY_EMOJI[item.category] || "📌";
    const catClass = `cat-${escapeHtml(item.category || "idea")}`;
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
    const creatorLine = subParts.length ? `<div class="card-creator">${subParts.join(" · ")}</div>` : "";

    const allTags = [...(item.genres || []), ...(item.tags || [])].slice(0, 5);
    const genresHtml = allTags.length
      ? `<div class="genres-line">${allTags
          .map((g) => `<span class="genre-pill" data-tag="${escapeHtml(g)}">#${escapeHtml(g)}</span>`)
          .join("")}</div>`
      : "";

    const summaryHtml = item.summary ? `<div class="summary-text">${escapeHtml(item.summary)}</div>` : "";
    const ratingsHtml = buildRatingsHtml(item, { compact: false, includeSources: false });
    const cornerSourceHtml = buildCornerSourceHtml(item);

    return `
      <article class="item-card cat-accent ${catClass}" data-open-id="${item.id}">
        <div class="card-top">
          <div class="poster-box">${posterHtml}</div>
          <div class="card-info">
            <div class="card-head-row">
              <div class="card-title">${escapeHtml(item.title_ru)}${yearStr}</div>
              ${cornerSourceHtml}
            </div>
            ${origLine}
            ${creatorLine}
            ${ratingsHtml ? `<div class="ratings-bar">${ratingsHtml}</div>` : ""}
          </div>
        </div>
        ${genresHtml}
        ${summaryHtml}
        <div class="card-footer">
          ${buildCardActionsHtml(item)}
        </div>
      </article>
    `;
  }

  function renderKanbanCard(item) {
    const emoji = CATEGORY_EMOJI[item.category] || "📌";
    const catClass = `cat-${escapeHtml(item.category || "idea")}`;
    const posterHtml = item.poster_url
      ? `<img src="${escapeHtml(item.poster_url)}" alt="" loading="lazy" />`
      : `<span>${emoji}</span>`;
    const yearStr = item.release_year ? ` (${item.release_year})` : "";
    const ratingsHtml = buildRatingsHtml(item, { compact: true, includeSources: false });
    const cornerSourceHtml = buildCornerSourceHtml(item);

    return `
      <article class="kanban-card cat-accent ${catClass}" data-open-id="${item.id}">
        <div class="kanban-card-top">
          <div class="kanban-poster">${posterHtml}</div>
          <div class="kanban-card-meta">
            <div class="card-head-row">
              <div class="list-title" style="font-size:14.5px;">${escapeHtml(item.title_ru)}${yearStr}</div>
              ${cornerSourceHtml}
            </div>
            ${shouldShowCreator(item) ? `<div class="list-subline" style="font-size:12px;">${escapeHtml(item.creator)}</div>` : ""}
          </div>
        </div>
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
          <section class="kanban-col">
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

  function renderCatalog() {
    const container = document.getElementById("catalogContainer");
    const grid = document.getElementById("catalogGrid");
    const empty = document.getElementById("emptyState");

    updateCountLabels(`Найдено записей: ${state.items.length}`, state.items.length);

    if (!state.items.length) {
      if (container) container.classList.remove("kanban-wide");
      grid.className = "catalog-list";
      grid.innerHTML = "";
      empty.classList.remove("hidden");
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
    } else if (state.viewMode === "cards") {
      grid.className = "catalog-list view-cards";
      grid.innerHTML = state.items.map(renderEditorialCard).join("");
    } else {
      grid.className = "catalog-list view-list";
      grid.innerHTML = state.items.map(renderListRow).join("");
    }

    if (state.drawerItemId !== null) {
      renderDetailDrawer();
    }
  }

  function renderOriginals() {
    const container = document.getElementById("catalogContainer");
    const grid = document.getElementById("catalogGrid");
    const empty = document.getElementById("emptyState");
    if (container) container.classList.remove("kanban-wide");

    updateCountLabels(`Оригиналов: ${state.originals.length}`, state.originals.length);

    if (!state.originals.length) {
      grid.className = "catalog-list";
      grid.innerHTML = "";
      empty.classList.remove("hidden");
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
    if (!["list", "cards", "kanban"].includes(mode)) return;
    closeStatusPopover();
    state.viewMode = mode;
    localStorage.setItem("sb_view_mode", mode);
    syncNavigationState();
    if (state.view === "catalog") {
      renderCatalog();
    }
    haptic("selection");
  }

  function syncNavigationState() {
    const isOriginals = state.view === "originals";

    document.querySelectorAll("#sidebarViewSwitch .nav-btn, #mobileBottomBar [data-view]").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.view === state.view);
    });

    document.querySelectorAll("#sidebarCategoryTabs .nav-btn, #mobileCategoryTabs .tab").forEach((btn) => {
      btn.classList.toggle("active", (btn.dataset.tab || "") === state.tab);
    });

    document.querySelectorAll("#viewModeSwitchDesktop .mode-btn, #viewModeSwitchMobile .mode-icon-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.mode === state.viewMode);
    });

    document.getElementById("desktopCatalogControls").classList.toggle("hidden", isOriginals);
    document.getElementById("viewModeSwitchMobile").classList.toggle("hidden", isOriginals);
    document.getElementById("mobileFilterBtn").classList.toggle("hidden", isOriginals);
    document.getElementById("tagBar").classList.toggle("hidden", isOriginals);

    document.getElementById("searchInput").placeholder = isOriginals
      ? "Простой поиск по оригиналам..."
      : "Поиск по названию, автору, описанию...";

    const hasActiveFilter = !isOriginals && (state.status !== "all" || state.sort !== "created" || Boolean(state.tag));
    const filterDot = document.getElementById("mobileFilterDot");
    if (filterDot) filterDot.classList.toggle("hidden", !hasActiveFilter);
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
      renderTagBar();
    } catch (err) {
      if (err && err.name === "AbortError") return;
      throw err;
    }
  }

  async function loadItems() {
    if (itemsAbort) itemsAbort.abort();
    itemsAbort = new AbortController();
    const { signal } = itemsAbort;

    const params = new URLSearchParams();
    if (state.tab) params.set("tab", state.tab);
    if (state.status && state.status !== "all") params.set("status", state.status);
    if (state.tag) params.set("tag", state.tag);
    if (state.q) params.set("q", state.q);
    if (state.sort) params.set("sort", state.sort);

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
      state.items = data.items || [];
      state.tgChatId = data.tg_chat_id || 0;
      renderCatalog();
    } catch (err) {
      if (err && err.name === "AbortError") return;
      throw err;
    }
  }

  function refreshCurrentView() {
    closeStatusPopover();
    syncNavigationState();
    if (state.view === "originals") {
      loadOriginals();
    } else {
      loadTags();
      loadItems();
    }
  }

  async function patchItem(itemId, payload) {
    const numId = Number(itemId);
    const idx = state.items.findIndex((i) => Number(i.id) === numId);
    const prevSnapshot = idx !== -1 ? { ...state.items[idx] } : null;

    // Оптимистично обновляем UI мгновенно
    if (idx !== -1) {
      if (payload.status !== undefined) state.items[idx].status = payload.status;
      if (payload.user_rating !== undefined) {
        state.items[idx].user_rating = payload.user_rating === 0 ? null : Number(payload.user_rating);
      }
      renderCatalog();
    }

    const res = await fetch(`/api/items/${numId}`, {
      method: "PATCH",
      headers: authHeaders(),
      body: JSON.stringify(payload),
    });
    if (res.status === 401 || res.status === 403) {
      if (prevSnapshot && idx !== -1) {
        state.items[idx] = prevSnapshot;
        renderCatalog();
      }
      showAuthModal(res.status === 403 && Boolean(tg && tg.initData));
      return;
    }
    if (res.ok) {
      const updated = await res.json();
      const freshIdx = state.items.findIndex((i) => Number(i.id) === numId);
      if (freshIdx !== -1) {
        state.items[freshIdx] = updated;
        renderCatalog();
      }
      haptic("light");
    } else if (prevSnapshot && idx !== -1) {
      state.items[idx] = prevSnapshot;
      renderCatalog();
    }
  }

  async function deleteItem(itemId) {
    const numId = Number(itemId);
    const res = await fetch(`/api/items/${numId}`, {
      method: "DELETE",
      headers: authHeaders(),
    });
    if (res.status === 401 || res.status === 403) {
      showAuthModal(res.status === 403 && Boolean(tg && tg.initData));
      return;
    }
    if (res.ok) {
      state.items = state.items.filter((i) => Number(i.id) !== numId);
      renderCatalog();
      loadTags();
      haptic("medium");
    }
  }

  async function deleteOriginal(origId) {
    const numId = Number(origId);
    const res = await fetch(`/api/originals/${numId}`, {
      method: "DELETE",
      headers: authHeaders(),
    });
    if (res.status === 401 || res.status === 403) {
      showAuthModal(res.status === 403 && Boolean(tg && tg.initData));
      return;
    }
    if (res.ok) {
      const data = await res.json().catch(() => ({}));
      const deletedIds = new Set((data.deleted_item_ids || []).map(Number));
      state.originals = state.originals.filter((o) => Number(o.id) !== numId);
      if (deletedIds.size > 0) {
        state.items = state.items.filter((i) => !deletedIds.has(Number(i.id)));
      }
      renderOriginals();
      haptic("medium");
    }
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
    refreshCurrentView();
  });

  document.getElementById("mobileBottomBar").addEventListener("click", (e) => {
    const viewBtn = e.target.closest("[data-view]");
    if (viewBtn) {
      state.view = viewBtn.dataset.view || "catalog";
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
      window.scrollTo({ top: 0, behavior: "smooth" });
      setTimeout(() => document.getElementById("searchInput").focus(), 180);
    }
  });

  document.getElementById("mobileFilterBtn").addEventListener("click", openFiltersSheet);

  function bindCategoryContainer(containerId) {
    const el = document.getElementById(containerId);
    if (!el) return;
    el.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-tab]");
      if (!btn) return;
      state.tab = btn.dataset.tab || "";
      state.tag = "";
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
  document.getElementById("viewModeSwitchMobile").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-mode]");
    if (btn) setViewMode(btn.dataset.mode);
  });

  document.getElementById("statusFilterSelect").addEventListener("change", (e) => {
    state.status = e.target.value || "all";
    syncNavigationState();
    loadItems();
  });

  document.getElementById("sortSelect").addEventListener("change", (e) => {
    state.sort = e.target.value;
    syncNavigationState();
    loadItems();
  });

  document.getElementById("tagBar").addEventListener("click", (e) => {
    const btn = e.target.closest(".chip");
    if (!btn) return;
    const clickedTag = btn.dataset.tag || "";
    state.tag = state.tag === clickedTag && clickedTag !== "" ? "" : clickedTag;
    syncNavigationState();
    renderTagBar();
    loadItems();
  });

  document.getElementById("tagBar").addEventListener("change", (e) => {
    if (e.target.id === "moreTagsSelect") {
      state.tag = e.target.value || "";
      syncNavigationState();
      renderTagBar();
      loadItems();
    }
  });

  const searchInput = document.getElementById("searchInput");
  const searchClearBtn = document.getElementById("searchClearBtn");
  let searchTimer = null;

  searchInput.addEventListener("input", (e) => {
    const val = e.target.value;
    searchClearBtn.classList.toggle("hidden", !val);
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.q = val.trim();
      if (state.view === "originals") {
        loadOriginals();
      } else {
        loadItems();
      }
    }, 260);
  });

  searchClearBtn.addEventListener("click", () => {
    searchInput.value = "";
    searchClearBtn.classList.add("hidden");
    state.q = "";
    if (state.view === "originals") {
      loadOriginals();
    } else {
      loadItems();
    }
    searchInput.focus();
  });

  document.getElementById("themeToggleDesktop").addEventListener("click", cycleThemeMode);
  document.getElementById("themeToggleMobile").addEventListener("click", cycleThemeMode);
  document.getElementById("refreshBtnDesktop").addEventListener("click", refreshCurrentView);
  document.getElementById("refreshBtnMobile").addEventListener("click", refreshCurrentView);

  const catalogGridEl = document.getElementById("catalogGrid");

  catalogGridEl.addEventListener("click", (e) => {
    const stBtn = e.target.closest("[data-action='status-menu']");
    if (stBtn && stBtn.dataset.id) {
      e.stopPropagation();
      openStatusPopover(stBtn.dataset.id, stBtn);
      return;
    }

    const delBtn = e.target.closest("[data-action='delete']");
    if (delBtn && delBtn.dataset.id) {
      e.stopPropagation();
      closeStatusPopover();
      deleteItem(delBtn.dataset.id);
      return;
    }

    const delOrigBtn = e.target.closest("[data-action='delete-orig']");
    if (delOrigBtn && delOrigBtn.dataset.origId) {
      e.stopPropagation();
      deleteOriginal(delOrigBtn.dataset.origId);
      return;
    }

    const pill = e.target.closest(".genre-pill");
    if (pill) {
      e.stopPropagation();
      closeStatusPopover();
      state.tag = pill.dataset.tag || "";
      syncNavigationState();
      renderTagBar();
      loadItems();
      return;
    }

    if (e.target.closest("a, select, option, button")) {
      return;
    }

    const card = e.target.closest("[data-open-id]");
    if (card) {
      openDetailDrawer(card.dataset.openId);
    }
  });

  catalogGridEl.addEventListener("change", (e) => {
    const ratingSel = e.target.closest("select[data-action='rating']");
    if (ratingSel && ratingSel.dataset.id) {
      e.stopPropagation();
      patchItem(ratingSel.dataset.id, { user_rating: Number(ratingSel.value) });
    }
  });

  document.addEventListener("click", (e) => {
    if (!e.target.closest("#statusPopover") && !e.target.closest("[data-action='status-menu']")) {
      closeStatusPopover();
    }
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      closeStatusPopover();
      closeDetailDrawer();
      closeFiltersSheet();
      return;
    }
    if (e.key === "/" && !e.ctrlKey && !e.metaKey && !e.altKey) {
      const tag = (document.activeElement && document.activeElement.tagName || "").toLowerCase();
      if (tag !== "input" && tag !== "textarea" && tag !== "select") {
        e.preventDefault();
        searchInput.focus();
      }
    }
  });

  window.addEventListener("resize", () => {
    closeStatusPopover();
    if (state.view === "catalog") renderTagBar();
  });

  window.addEventListener("scroll", closeStatusPopover, { passive: true });

  enableCarouselTouchScroll(document.getElementById("mobileCategoryTabs"));
  enableCarouselTouchScroll(document.getElementById("tagBar"));

  hydrateIcons();
  applyTheme();
  refreshCurrentView();
})();
