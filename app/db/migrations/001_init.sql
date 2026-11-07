-- 001_init.sql: Схема базы данных «Второй мозг» и Медиа-каталог (Этап 1)

CREATE TABLE IF NOT EXISTS items (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    category           TEXT NOT NULL CHECK (category IN ('movie','series','book','video','article','post','idea')),
    status             TEXT NOT NULL DEFAULT 'inbox'
                       CHECK (status IN ('inbox','planned','in_progress','done','dropped')),
    processing_status  TEXT NOT NULL DEFAULT 'pending'
                       CHECK (processing_status IN ('pending','ok','needs_choice','needs_input','failed')),
    processing_error   TEXT,

    title_ru           TEXT,
    title_orig         TEXT,
    normalized_title   TEXT NOT NULL,
    release_year       INTEGER,
    creator            TEXT,
    normalized_creator TEXT,

    imdb_id            TEXT UNIQUE,
    kp_id              INTEGER UNIQUE,
    google_books_id    TEXT UNIQUE,
    isbn13             TEXT,
    canonical_url      TEXT UNIQUE,

    rating_imdb        REAL,
    rating_kp          REAL,
    rating_rt          INTEGER,
    user_rating        INTEGER CHECK (user_rating BETWEEN 1 AND 10),

    summary            TEXT,
    poster_url         TEXT,
    poster_tg_file_id  TEXT,
    url_rt             TEXT,
    meta               TEXT,
    raw_input          TEXT,

    tg_topic_id        INTEGER,
    tg_message_id      INTEGER,

    created_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS item_sources (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id       INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    source_url    TEXT,
    source_type   TEXT NOT NULL CHECK (source_type IN ('threads','instagram','youtube','web','telegram','manual')),
    raw_text      TEXT,
    added_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (item_id, source_url)
);

CREATE TABLE IF NOT EXISTS item_tags (
    item_id  INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    kind     TEXT NOT NULL CHECK (kind IN ('genre','tag')),
    tag      TEXT NOT NULL,
    PRIMARY KEY (item_id, kind, tag)
);

CREATE TABLE IF NOT EXISTS processed_updates (
    update_id     INTEGER PRIMARY KEY,
    processed_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bot_state (
    key    TEXT PRIMARY KEY,
    value  TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(
    title_ru, title_orig, creator, summary, tags, sources_text,
    tokenize = 'unicode61 remove_diacritics 2'
);

CREATE INDEX IF NOT EXISTS idx_items_dedup        ON items(category, normalized_title, release_year);
CREATE INDEX IF NOT EXISTS idx_items_book_dedup   ON items(normalized_title, normalized_creator) WHERE category = 'book';
CREATE INDEX IF NOT EXISTS idx_items_cat_status   ON items(category, status);
CREATE INDEX IF NOT EXISTS idx_items_created      ON items(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_items_rating_imdb  ON items(rating_imdb DESC);
CREATE INDEX IF NOT EXISTS idx_items_rating_kp    ON items(rating_kp DESC);
CREATE INDEX IF NOT EXISTS idx_items_rating_rt    ON items(rating_rt DESC);
CREATE INDEX IF NOT EXISTS idx_items_processing   ON items(processing_status) WHERE processing_status <> 'ok';
CREATE INDEX IF NOT EXISTS idx_tags_tag           ON item_tags(kind, tag);
CREATE INDEX IF NOT EXISTS idx_sources_item       ON item_sources(item_id);

CREATE TRIGGER IF NOT EXISTS trg_items_updated_at
AFTER UPDATE ON items FOR EACH ROW WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE items SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;
