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


if __name__ == "__main__":
    unittest.main(verbosity=2)
