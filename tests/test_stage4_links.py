from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.bot.handlers import split_batch_lines
from app.clients.scraper import parse_html_metadata
from app.utils.urls import extract_youtube_video_id, normalize_url


class TestStage4Links(unittest.TestCase):
    def test_youtube_and_threads_url_normalization(self) -> None:
        self.assertEqual(
            normalize_url("https://youtu.be/dQw4w9WgXcQ?si=abc123&utm_source=tg"),
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        )
        self.assertEqual(
            normalize_url("https://m.youtube.com/shorts/dQw4w9WgXcQ?feature=share"),
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        )
        self.assertEqual(extract_youtube_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ"), "dQw4w9WgXcQ")
        self.assertEqual(
            normalize_url("https://www.threads.net/@user/post/C12345/?igshid=xyz&utm_medium=copy"),
            "https://www.threads.com/@user/post/C12345",
        )

    def test_split_batch_lines(self) -> None:
        raw = "1. Гиперион\n2) Падение Гипериона\n- Дюна\n"
        self.assertEqual(split_batch_lines(raw), ["Гиперион", "Падение Гипериона", "Дюна"])

    def test_parse_html_metadata(self) -> None:
        sample_html = """
        <html>
          <head>
            <meta property="og:title" content="Топ 5 лучших книг по фантастике" />
            <meta content="Подробный разбор классики научной фантастики." property="og:description" />
            <meta property="og:image" content="https://example.com/cover.jpg" />
          </head>
          <body>
            <p>В этой статье мы подробно разберем лучшие научно-фантастические романы двадцатого века.</p>
          </body>
        </html>
        """
        parsed = parse_html_metadata(sample_html)
        self.assertEqual(parsed["title"], "Топ 5 лучших книг по фантастике")
        self.assertEqual(parsed["description"], "Подробный разбор классики научной фантастики.")
        self.assertEqual(parsed["image"], "https://example.com/cover.jpg")
        self.assertIn("научно-фантастические романы", parsed["body_text"] or "")

    def test_llm_tag_normalization_and_short_idea_tagging(self) -> None:
        from unittest.mock import patch
        from app.bot.handlers import handle_update
        from app.clients.groq_llm import GroqLLMClient, extract_hashtags, normalize_llm_tags
        from app.config import settings
        from app.db.client import get_connection
        from app.db.migrate import apply_migrations
        from app.db.repo import get_item

        self.assertEqual(normalize_llm_tags(["#Мода", "одежда", "мода"]), ["мода", "одежда"])
        self.assertEqual(normalize_llm_tags("свитер, #зима, одежда"), ["свитер", "зима", "одежда"])
        self.assertEqual(extract_hashtags("Свитер #Одежда #123 #uniqlo"), ["одежда", "uniqlo"])

        # Проверка, что summarize_and_tag передаёт accept и принимает теги при наличии
        llm = GroqLLMClient(api_key="test-key")
        with patch.object(llm, "_call_json", return_value={"title_ru": "Свитер", "summary": "Описание", "tags": "#мода, #одежда"}) as m_call:
            res = llm.summarize_and_tag(title="Jumper", text="Lambswool jumper")
            self.assertEqual(res["tags"], ["мода", "одежда"])
            _, kwargs = m_call.call_args
            self.assertIsNotNone(kwargs.get("accept"))
            self.assertFalse(kwargs["accept"]({"title_ru": "X", "tags": []}))
            self.assertTrue(kwargs["accept"]({"title_ru": "X", "tags": ["мода"]}))

        # Короткая идея (<= 80 символов) всё равно получает теги от LLM и хештеги
        conn = get_connection(":memory:")
        apply_migrations(conn)

        class DummyTG:
            def set_message_reaction(self, *args, **kwargs):
                return {"ok": True}

        upd = {
            "update_id": 4001,
            "message": {
                "message_id": 100,
                "message_thread_id": 5,
                "chat": {"id": -1003531389022},
                "from": {"id": 349407845},
                "text": "Купить свитер из мериноса #зима",
            },
        }
        with (
            patch.object(settings, "allowed_tg_user_id", 349407845),
            patch.object(settings, "topic_ideas_id", 5),
            patch.object(settings, "llm_for_ideas", True),
            patch.object(settings, "groq_api_key", "test-key"),
            patch.object(
                GroqLLMClient,
                "summarize_and_tag",
                return_value={"title_ru": "Покупка свитера", "summary": "Купить тёплый свитер.", "tags": ["одежда", "покупки"]},
            ),
        ):
            res = handle_update(conn, upd, tg=DummyTG())  # type: ignore[arg-type]

        item = get_item(conn, res["item_id"])
        assert item is not None
        # Короткий заголовок не раздувается в длинную сводку, а теги проставляются
        self.assertEqual(item["title_ru"], "Купить свитер из мериноса #зима")
        self.assertIn("зима", item["tags"])
        self.assertIn("одежда", item["tags"])
        self.assertIn("покупки", item["tags"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
