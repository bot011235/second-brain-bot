(() => {
  const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  if (tg) {
    tg.ready();
    tg.expand();
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

  const state = {
    view: "catalog",
    tab: "",
    status: "all",
    tag: "",
    q: "",
    sort: "created",
    items: [],
    originals: [],
    allTags: [],
    tgChatId: 0,
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
        authPasswordInput.focus();
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
      } catch (err) {
        if (authErrorMsg) {
          authErrorMsg.textContent = "Ошибка сети или сервера. Попробуйте снова.";
          authErrorMsg.classList.remove("hidden");
        }
      }
    });
  }

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

  const SVC_ICONS = {
    threads: `<svg class="svc-svg" viewBox="0 0 192 192" width="14" height="14" fill="currentColor"><path d="M141.537 88.9883C140.71 88.5919 139.87 88.2104 139.019 87.8451C137.537 60.5382 122.616 44.905 97.5619 44.745C97.4184 44.7443 97.2748 44.7443 97.1313 44.745C75.8062 44.745 59.4975 58.115 54.4363 79.475C49.375 100.835 56.685 125.145 74.0537 137.955C89.1762 149.11 110.126 150.315 125.753 141.455L120.436 129.565C108.575 136.295 92.4287 135.215 80.6975 126.565C67.6663 116.955 62.1587 97.975 66.1762 81.015C70.1937 64.055 82.5275 53.485 97.2287 53.485C115.111 53.605 125.961 65.615 127.166 88.295C124.717 89.475 122.137 90.725 119.431 92.055C102.774 100.225 84.7212 109.085 86.8537 127.835C87.9725 137.665 96.0825 145.415 106.004 145.415C116.541 145.415 126.136 138.445 131.789 129.745C136.529 138.515 143.725 143.265 152.923 143.265C166.456 143.265 177.346 132.375 177.346 118.842C177.346 95.845 159.957 88.025 141.537 88.9883ZM120.916 117.815C117.476 123.965 111.451 127.675 104.931 127.675C99.8825 127.675 95.8362 124.085 95.3425 119.745C94.2787 110.375 104.382 104.935 118.736 97.895C120.479 97.039 122.203 96.1983 123.904 95.3725C124.496 103.585 123.496 113.205 120.916 117.815Z"/></svg>`,
    youtube: `<svg class="svc-svg" viewBox="0 0 24 24" width="15" height="15" fill="#ef4444"><path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/></svg>`,
    instagram: `<svg class="svc-svg" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="#e1306c" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="20" rx="5" ry="5"></rect><path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z"></path><line x1="17.5" y1="6.5" x2="17.51" y2="6.5"></line></svg>`,
    telegram: `<svg class="svc-svg" viewBox="0 0 24 24" width="14" height="14" fill="#0284c7"><path d="m20.665 3.717-17.73 6.837c-1.21.486-1.203 1.161-.222 1.462l4.552 1.42 10.532-6.645c.498-.303.953-.14.579.192l-8.533 7.701h-.002l-.313 4.673c.46 0 .663-.211.921-.46l2.211-2.15 4.599 3.397c.848.467 1.457.227 1.668-.785l3.019-14.228c.309-1.239-.473-1.8-1.282-1.414z"/></svg>`,
    x: `<svg class="svc-svg" viewBox="0 0 24 24" width="13" height="13" fill="currentColor"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>`,
    reddit: `<svg class="svc-svg" viewBox="0 0 24 24" width="14" height="14" fill="#ea580c"><circle cx="12" cy="12" r="10"/><path fill="#fff" d="M17 11.5a1.5 1.5 0 0 0-2.5-1.1c-.8-.5-1.8-.8-3-.9l.5-2.5 2 .4a1 1 0 1 0 .2-.7l-2.4-.5a.5.5 0 0 0-.6.4l-.7 3.2c-1.1.1-2.2.4-3 .9A1.5 1.5 0 0 0 5 11.5c0 .6.3 1.1.8 1.3 0 .2 0 .4 0 .7 0 2.2 2.7 4 6 4s6-1.8 6-4c0-.3 0-.5 0-.7.5-.2.8-.7.8-1.3zM9 11.5a1 1 0 1 1 2 0 1 1 0 0 1-2 0zm5.8 3.3c-.6.6-1.7.7-2.8.7s-2.2-.1-2.8-.7a.3.3 0 0 1 .4-.4c.5.5 1.4.6 2.4.6s1.9-.1 2.4-.6a.3.3 0 0 1 .4.4zm.2-2.3a1 1 0 1 1 0-2 1 1 0 0 1 0 2z"/></svg>`,
    github: `<svg class="svc-svg" viewBox="0 0 24 24" width="14" height="14" fill="currentColor"><path fill-rule="evenodd" clip-rule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"/></svg>`,
    tiktok: `<svg class="svc-svg" viewBox="0 0 24 24" width="14" height="14" fill="currentColor"><path d="M19.589 6.686a4.793 4.793 0 0 1-3.77-4.245V2h-3.445v13.672a2.896 2.896 0 0 1-2.883 2.87 2.896 2.896 0 0 1-2.884-2.87 2.896 2.896 0 0 1 2.884-2.87c.29 0 .57.042.836.12v-3.52a6.376 6.376 0 0 0-.836-.056C5.932 9.436 3 12.38 3 16.012c0 3.633 2.932 6.578 6.547 6.578 3.616 0 6.548-2.945 6.548-6.578V9.167a8.21 8.21 0 0 0 4.887 1.583v-3.44a4.83 4.83 0 0 1-1.393-.624z"/></svg>`,
    globe: `<svg class="svc-svg" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="2" y1="12" x2="22" y2="12"></line><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path></svg>`,
  };

  function buildSourceBadgeHtml(url, index = null) {
    if (!url) return "";
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
      iconHtml = `<span style="font-weight:800;font-size:11px;">M</span>`;
      label = "Medium";
    } else if (domain.includes("wikipedia.org")) {
      iconHtml = SVC_ICONS.globe;
      label = "Википедия";
    }

    if (index != null) {
      label += ` ${index}`;
    }

    const safeUrl = escapeHtml(url);
    const safeLabel = escapeHtml(label);
    return `<a class="rating-badge source-badge" href="${safeUrl}" target="_blank" rel="noopener noreferrer" title="${safeLabel}: ${safeUrl}">${iconHtml}<span>${safeLabel}</span></a>`;
  }

  function buildRatingsHtml(item) {
    const meta = parseMeta(item.meta);
    const badges = [];

    if (item.category === "book") {
      const rFl = meta.rating_fantlab ?? item.rating_kp;
      const uFl = meta.url_fantlab || "#";
      if (rFl != null) {
        badges.push(
          `<a class="rating-badge ${badgeTone(rFl, 10)}" href="${uFl}" target="_blank">🐉 FantLab ${rFl}</a>`
        );
      }
      const rGr = meta.rating_goodreads ?? item.rating_imdb;
      const uGr = meta.url_goodreads || "#";
      if (rGr != null) {
        badges.push(
          `<a class="rating-badge ${badgeTone(rGr, 5)}" href="${uGr}" target="_blank">📖 Goodreads ${rGr}</a>`
        );
      }
      if (meta.info_link) {
        badges.push(`<a class="rating-badge" href="${meta.info_link}" target="_blank">🌐 Вики</a>`);
      }
    } else if (item.category === "movie" || item.category === "series") {
      if (item.rating_imdb != null || item.imdb_id) {
        const url = item.imdb_id ? `https://www.imdb.com/title/${item.imdb_id}/` : "#";
        const label = item.rating_imdb != null ? `⭐ IMDb ${item.rating_imdb}` : "⭐ IMDb";
        badges.push(
          `<a class="rating-badge ${badgeTone(item.rating_imdb, 10)}" href="${url}" target="_blank">${label}</a>`
        );
      }
      const kpQuery = encodeURIComponent((item.title_ru || item.title_orig || "").trim());
      const kpUrl = item.kp_id
        ? `https://www.kinopoisk.ru/film/${item.kp_id}/`
        : kpQuery
        ? `https://www.kinopoisk.ru/index.php?kp_query=${kpQuery}`
        : "#";
      const kpLabel = item.rating_kp != null ? `🟠 КП ${item.rating_kp}` : "🟠 КП";
      badges.push(
        `<a class="rating-badge ${badgeTone(item.rating_kp, 10)}" href="${kpUrl}" target="_blank">${kpLabel}</a>`
      );
      if (meta.rating_tmdb != null) {
        const tmdbType = item.category === "series" ? "tv" : "movie";
        const url = meta.tmdb_id ? `https://www.themoviedb.org/${tmdbType}/${meta.tmdb_id}` : "#";
        badges.push(
          `<a class="rating-badge ${badgeTone(meta.rating_tmdb, 10)}" href="${url}" target="_blank">🎞 TMDB ${meta.rating_tmdb}</a>`
        );
      }
      if (item.rating_rt != null || item.url_rt) {
        const url = item.url_rt || "#";
        const label = item.rating_rt != null ? `🍅 RT ${item.rating_rt}%` : "🍅 RT";
        badges.push(
          `<a class="rating-badge ${badgeTone(item.rating_rt, 100)}" href="${url}" target="_blank">${label}</a>`
        );
      }
    }

    const sources = item.sources || [];
    const seenUrls = new Set();
    sources.forEach((s, idx) => {
      if (s.source_url && !seenUrls.has(s.source_url)) {
        seenUrls.add(s.source_url);
        badges.push(buildSourceBadgeHtml(s.source_url, sources.length > 1 ? idx + 1 : null));
      }
    });
    if (item.canonical_url && !seenUrls.has(item.canonical_url)) {
      seenUrls.add(item.canonical_url);
      badges.push(buildSourceBadgeHtml(item.canonical_url, null));
    }

    return badges.join("");
  }

  function buildTelegramMessageLink(item) {
    if (!state.tgChatId || !item.tg_message_id) return "";
    const cleanChat = String(state.tgChatId).replace(/^-100/, "");
    const topicPart = item.tg_topic_id ? `${item.tg_topic_id}/` : "";
    return `https://t.me/c/${cleanChat}/${topicPart}${item.tg_message_id}`;
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str || "";
    return div.innerHTML;
  }

  function renderTagBar() {
    const container = document.getElementById("tagBar");
    // Сортируем строго по убыванию количества (count DESC)
    const sorted = [...state.allTags].sort((a, b) => b.count - a.count || a.tag.localeCompare(b.tag));
    if (!sorted.length) {
      container.innerHTML = "";
      return;
    }

    // Выводим жанры/теги в горизонтальную прокручиваемую карусель (на телефоне и ПК)
    const maxInline = 25;
    const inlineTags = sorted.slice(0, maxInline);
    const overflowTags = sorted.slice(maxInline);

    let html = `<button class="chip ${state.tag === "" ? "active" : ""}" data-tag="">Все жанры/теги</button>`;
    inlineTags.forEach((t) => {
      const isAct = state.tag === t.tag ? "active" : "";
      html += `<button class="chip ${isAct}" data-tag="${escapeHtml(t.tag)}">${escapeHtml(t.tag)} (${t.count})</button>`;
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

  function renderCatalog() {
    const grid = document.getElementById("catalogGrid");
    const empty = document.getElementById("emptyState");
    const countLabel = document.getElementById("totalCountLabel");

    countLabel.textContent = `Найдено записей: ${state.items.length}`;

    if (!state.items.length) {
      grid.innerHTML = "";
      empty.classList.remove("hidden");
      return;
    }
    empty.classList.add("hidden");

    grid.innerHTML = state.items
      .map((item) => {
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
        if (item.creator) {
          subParts.push(`👤 ${escapeHtml(item.creator)}`);
        }
        if (item.category === "series" && meta.seasons_count) {
          subParts.push(`📺 Сезонов: ${Number(meta.seasons_count)}`);
        }
        const creatorLine = subParts.length
          ? `<div class="card-creator">${subParts.join(" · ")}</div>`
          : "";

        const allTags = [...(item.genres || []), ...(item.tags || [])];
        const genresHtml = allTags.length
          ? `<div class="genres-line">${allTags
              .map((g) => `<span class="genre-pill" data-tag="${escapeHtml(g)}">#${escapeHtml(g)}</span>`)
              .join("")}</div>`
          : "";

        const summaryHtml = item.summary
          ? `<div class="summary-text" title="Нажмите, чтобы развернуть">${escapeHtml(item.summary)}</div>`
          : "";

        const chatUrl = buildTelegramMessageLink(item);
        const chatLinkHtml = chatUrl
          ? `<a class="chat-link" href="${chatUrl}" target="_blank">💬 В чате</a>`
          : "";

        // Оценка без "/10"
        const userRatingOptions = [0, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1]
          .map((val) => {
            const selected = (item.user_rating || 0) === val ? "selected" : "";
            const label = val === 0 ? "⭐ Оценка" : `⭐ ${val}`;
            return `<option value="${val}" ${selected}>${label}</option>`;
          })
          .join("");

        return `
          <article class="item-card ${catClass}" data-id="${item.id}">
            <div class="card-top">
              <div class="poster-box">${posterHtml}</div>
              <div class="card-info">
                <div class="card-title">${emoji} ${escapeHtml(item.title_ru)}${yearStr}</div>
                ${origLine}
                ${creatorLine}
                <div class="ratings-bar">${buildRatingsHtml(item)}</div>
              </div>
            </div>
            ${genresHtml}
            ${summaryHtml}
            <div class="card-actions">
              <select class="status-select" data-action="status" data-id="${item.id}">
                <option value="inbox" ${item.status === "inbox" ? "selected" : ""}>📥 Входящие</option>
                <option value="planned" ${item.status === "planned" ? "selected" : ""}>📌 В планах</option>
                <option value="in_progress" ${item.status === "in_progress" ? "selected" : ""}>▶️ В процессе</option>
                <option value="done" ${item.status === "done" ? "selected" : ""}>✅ Готово</option>
                <option value="dropped" ${item.status === "dropped" ? "selected" : ""}>🚫 Брошено</option>
              </select>
              <select class="user-rating-select" data-action="rating" data-id="${item.id}">
                ${userRatingOptions}
              </select>
              <div class="card-actions-right">
                ${chatLinkHtml}
                <button type="button" class="delete-btn" data-action="delete" data-id="${item.id}" title="Удалить">🗑</button>
              </div>
            </div>
          </article>
        `;
      })
      .join("");
  }

  function linkifyText(str) {
    const escaped = escapeHtml(str || "");
    return escaped.replace(
      /(https?:\/\/[^\s<]+)/gi,
      (url) => `<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>`
    );
  }

  function renderOriginals() {
    const grid = document.getElementById("catalogGrid");
    const empty = document.getElementById("emptyState");
    const countLabel = document.getElementById("totalCountLabel");

    countLabel.textContent = `Оригиналов: ${state.originals.length}`;

    if (!state.originals.length) {
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

    grid.innerHTML = state.originals
      .map((orig) => {
        const topicLabel = TOPIC_LABELS[orig.topic_slug] || "💡 Идеи и посты";
        const catClass = catToCardClass[orig.topic_slug] || "cat-idea";
        const dateStr = (orig.created_at || "").slice(0, 16).replace("T", " ");
        const authorHtml = orig.author ? `<span class="orig-author">${escapeHtml(orig.author)}</span>` : "";
        const sourceBtnHtml = orig.source_url
          ? buildSourceBadgeHtml(orig.source_url, null)
          : "";

        const rawTrim = (orig.raw_text || "").trim();
        const extTrim = (orig.extracted_text || "").trim();
        const showExtracted = extTrim && extTrim !== rawTrim;

        return `
          <article class="item-card orig-card ${catClass}" data-orig-id="${orig.id}">
            <div class="orig-header">
              <span class="orig-topic-pill">${topicLabel}</span>
              ${authorHtml}
              <span class="orig-date">${escapeHtml(dateStr)}</span>
              <button type="button" class="delete-btn" data-action="delete-orig" data-orig-id="${orig.id}" title="Удалить">🗑</button>
            </div>
            <div class="orig-raw-text">${linkifyText(rawTrim)}</div>
            ${
              showExtracted
                ? `<div class="orig-extracted-box"><div class="orig-extracted-label">Текст из источника:</div><div class="orig-extracted-text">${escapeHtml(extTrim)}</div></div>`
                : ""
            }
            ${sourceBtnHtml ? `<div class="orig-footer">${sourceBtnHtml}</div>` : ""}
          </article>
        `;
      })
      .join("");
  }

  function syncViewControls() {
    const isOriginals = state.view === "originals";
    document.getElementById("statusFilterSelect").classList.toggle("hidden", isOriginals);
    document.getElementById("sortSelect").classList.toggle("hidden", isOriginals);
    document.getElementById("tagBar").classList.toggle("hidden", isOriginals);
    document.getElementById("searchInput").placeholder = isOriginals
      ? "Простой поиск по оригиналам..."
      : "Поиск по названию, автору, описанию...";
  }

  async function loadOriginals() {
    const params = new URLSearchParams();
    if (state.tab) params.set("tab", state.tab);
    if (state.q) params.set("q", state.q);
    const res = await fetch(`/api/originals?${params.toString()}`, { headers: authHeaders() });
    if (res.status === 401 || res.status === 403) {
      if (res.status === 401) {
        localStorage.removeItem("sb_access_key");
      }
      if (authErrorMsg && getAccessKey()) {
        authErrorMsg.classList.remove("hidden");
      }
      showAuthModal(res.status === 403 && Boolean(tg && tg.initData));
      return;
    }
    if (!res.ok) return;
    hideAuthModal();
    const data = await res.json();
    state.originals = data.items || [];
    renderOriginals();
  }

  function refreshCurrentView() {
    syncViewControls();
    if (state.view === "originals") {
      loadOriginals();
    } else {
      loadTags();
      loadItems();
    }
  }
  async function loadTags() {
    const params = new URLSearchParams();
    if (state.tab) params.set("tab", state.tab);
    const res = await fetch(`/api/tags?${params.toString()}`, { headers: authHeaders() });
    if (res.status === 401 || res.status === 403) return;
    if (!res.ok) return;
    const data = await res.json();
    state.allTags = data.tags || [];
    renderTagBar();
  }

  async function loadItems() {
    const params = new URLSearchParams();
    if (state.tab) params.set("tab", state.tab);
    if (state.status && state.status !== "all") params.set("status", state.status);
    if (state.tag) params.set("tag", state.tag);
    if (state.q) params.set("q", state.q);
    if (state.sort) params.set("sort", state.sort);

    const res = await fetch(`/api/items?${params.toString()}`, { headers: authHeaders() });
    if (res.status === 401 || res.status === 403) {
      if (res.status === 401) {
        localStorage.removeItem("sb_access_key");
      }
      if (authErrorMsg && getAccessKey()) {
        authErrorMsg.classList.remove("hidden");
      }
      showAuthModal(res.status === 403 && Boolean(tg && tg.initData));
      return;
    }
    if (!res.ok) return;
    hideAuthModal();
    const data = await res.json();
    state.items = data.items || [];
    state.tgChatId = data.tg_chat_id || 0;
    renderCatalog();
  }

  async function patchItem(itemId, payload) {
    const res = await fetch(`/api/items/${itemId}`, {
      method: "PATCH",
      headers: authHeaders(),
      body: JSON.stringify(payload),
    });
    if (res.status === 401 || res.status === 403) {
      showAuthModal(res.status === 403 && Boolean(tg && tg.initData));
      return;
    }
    if (res.ok) {
      const updated = await res.json();
      const idx = state.items.findIndex((i) => i.id === Number(itemId));
      if (idx !== -1) {
        state.items[idx] = updated;
      }
    }
  }

  async function deleteItem(itemId) {
    const res = await fetch(`/api/items/${itemId}`, {
      method: "DELETE",
      headers: authHeaders(),
    });
    if (res.status === 401 || res.status === 403) {
      showAuthModal(res.status === 403 && Boolean(tg && tg.initData));
      return;
    }
    if (res.ok) {
      state.items = state.items.filter((i) => i.id !== Number(itemId));
      renderCatalog();
      loadTags();
    }
  }

  async function deleteOriginal(origId) {
    const res = await fetch(`/api/originals/${origId}`, {
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
      state.originals = state.originals.filter((o) => o.id !== Number(origId));
      if (deletedIds.size > 0) {
        state.items = state.items.filter((i) => !deletedIds.has(Number(i.id)));
      }
      renderOriginals();
    }
  }

  function enableCarouselTouchScroll(el) {
    if (!el) return;
    el.addEventListener(
      "touchstart",
      (e) => {
        e.stopPropagation();
      },
      { passive: true }
    );
    el.addEventListener(
      "touchmove",
      (e) => {
        e.stopPropagation();
      },
      { passive: true }
    );
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

  // Обработчики событий
  document.getElementById("viewSwitch").addEventListener("click", (e) => {
    const btn = e.target.closest(".view-btn");
    if (!btn) return;
    document.querySelectorAll("#viewSwitch .view-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    state.view = btn.dataset.view || "catalog";
    refreshCurrentView();
  });

  document.getElementById("categoryTabs").addEventListener("click", (e) => {
    const btn = e.target.closest(".tab");
    if (!btn) return;
    document.querySelectorAll("#categoryTabs .tab").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    state.tab = btn.dataset.tab || "";
    state.tag = "";
    refreshCurrentView();
  });

  document.getElementById("statusFilterSelect").addEventListener("change", (e) => {
    state.status = e.target.value || "all";
    loadItems();
  });

  document.getElementById("sortSelect").addEventListener("change", (e) => {
    state.sort = e.target.value;
    loadItems();
  });

  document.getElementById("tagBar").addEventListener("click", (e) => {
    const btn = e.target.closest(".chip");
    if (!btn) return;
    state.tag = btn.dataset.tag || "";
    renderTagBar();
    loadItems();
  });

  document.getElementById("tagBar").addEventListener("change", (e) => {
    if (e.target.id === "moreTagsSelect") {
      state.tag = e.target.value || "";
      renderTagBar();
      loadItems();
    }
  });

  let searchTimer = null;
  document.getElementById("searchInput").addEventListener("input", (e) => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.q = e.target.value.trim();
      if (state.view === "originals") {
        loadOriginals();
      } else {
        loadItems();
      }
    }, 220);
  });

  document.getElementById("refreshBtn").addEventListener("click", () => {
    refreshCurrentView();
  });

  document.getElementById("catalogGrid").addEventListener("click", (e) => {
    const delBtn = e.target.closest("[data-action='delete']");
    if (delBtn && delBtn.dataset.id) {
      deleteItem(delBtn.dataset.id);
      return;
    }
    const delOrigBtn = e.target.closest("[data-action='delete-orig']");
    if (delOrigBtn && delOrigBtn.dataset.origId) {
      deleteOriginal(delOrigBtn.dataset.origId);
      return;
    }
    const summaryEl = e.target.closest(".summary-text");
    if (summaryEl) {
      summaryEl.classList.toggle("expanded");
      return;
    }
    const pill = e.target.closest(".genre-pill");
    if (pill) {
      state.tag = pill.dataset.tag || "";
      renderTagBar();
      loadItems();
    }
  });

  document.getElementById("catalogGrid").addEventListener("change", (e) => {
    const target = e.target;
    const itemId = target.dataset.id;
    if (!itemId) return;
    if (target.dataset.action === "status") {
      patchItem(itemId, { status: target.value });
    } else if (target.dataset.action === "rating") {
      patchItem(itemId, { user_rating: Number(target.value) });
    }
  });

  window.addEventListener("resize", () => {
    if (state.view === "catalog") renderTagBar();
  });

  enableCarouselTouchScroll(document.getElementById("categoryTabs"));
  enableCarouselTouchScroll(document.getElementById("tagBar"));

  refreshCurrentView();
})();
