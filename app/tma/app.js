(() => {
  const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  if (tg) {
    tg.ready();
    tg.expand();
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
    }
    return headers;
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
    sources.forEach((s, idx) => {
      if (s.source_url) {
        const lbl = sources.length === 1 ? "🔗 Источник" : `🔗 Источник ${idx + 1}`;
        badges.push(`<a class="rating-badge" href="${s.source_url}" target="_blank">${lbl}</a>`);
      }
    });

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
        const creatorLine = item.creator
          ? `<div class="card-creator">👤 ${escapeHtml(item.creator)}</div>`
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
          ? `<a class="rating-badge" href="${escapeHtml(orig.source_url)}" target="_blank">🔗 Открыть ссылку</a>`
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
    if (!res.ok) return;
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
    if (!res.ok) return;
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
    if (res.ok) {
      state.originals = state.originals.filter((o) => o.id !== Number(origId));
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
