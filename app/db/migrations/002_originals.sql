-- 002_originals.sql: Архив всех оригинальных сообщений пользователя из Telegram

CREATE TABLE IF NOT EXISTS original_messages (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_slug     TEXT NOT NULL DEFAULT 'ideas'
                   CHECK (topic_slug IN ('movies','books','video','article','ideas')),
    tg_topic_id    INTEGER,
    tg_message_id  INTEGER,
    raw_text       TEXT NOT NULL,
    source_url     TEXT,
    source_type    TEXT NOT NULL DEFAULT 'manual',
    author         TEXT,
    extracted_text TEXT,
    created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_originals_topic_created ON original_messages(topic_slug, created_at DESC);

INSERT INTO original_messages (topic_slug, tg_topic_id, tg_message_id, raw_text, source_url, source_type, created_at)
SELECT
    CASE
        WHEN i.category IN ('movie', 'series') THEN 'movies'
        WHEN i.category = 'book' THEN 'books'
        WHEN i.category = 'video' THEN 'video'
        WHEN i.category = 'article' THEN 'article'
        ELSE 'ideas'
    END,
    i.tg_topic_id,
    i.tg_message_id,
    i.raw_input,
    i.canonical_url,
    COALESCE((SELECT s.source_type FROM item_sources s WHERE s.item_id = i.id LIMIT 1), 'manual'),
    i.created_at
FROM items i
WHERE i.raw_input IS NOT NULL AND TRIM(i.raw_input) <> '';
