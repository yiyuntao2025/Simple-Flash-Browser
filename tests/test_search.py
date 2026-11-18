from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flashbrowser.search import (  # noqa: E402
    DEFAULT_SEARCH_ENGINE,
    build_search_url,
    engine_label,
    is_windows_path,
    looks_like_url,
    normalize_engine,
)


class SearchEngineTests(unittest.TestCase):
    def test_default_engine(self):
        self.assertEqual(DEFAULT_SEARCH_ENGINE, "bing")
        self.assertEqual(normalize_engine(None), "bing")
        self.assertEqual(normalize_engine("unknown"), "bing")
        self.assertEqual(normalize_engine("baidu"), "baidu")

    def test_labels(self):
        self.assertEqual(engine_label("bing"), "Bing")
        self.assertEqual(engine_label("baidu"), "百度")
        self.assertEqual(engine_label("google"), "Google")

    def test_build_search_url(self):
        self.assertEqual(
            build_search_url("hello world", "bing"),
            "https://www.bing.com/search?q=hello+world",
        )
        self.assertEqual(
            build_search_url("a&b c", "baidu"),
            "https://www.baidu.com/s?wd=a%26b+c",
        )
        self.assertEqual(
            build_search_url("猫咪", "google"),
            "https://www.google.com/search?q=%E7%8C%AB%E5%92%AA",
        )


class UrlHeuristicTests(unittest.TestCase):
    def test_schemes(self):
        for value in (
            "https://example.com",
            "http://example.com/a b",
            "file:///C:/game.swf",
            "about:blank",
            "data:text/html,hi",
            "mailto:a@b.com",
            "ftp://example.com/file",
        ):
            self.assertTrue(looks_like_url(value), value)

    def test_domains_and_hosts(self):
        for value in (
            "example.com",
            "www.example.com/path?q=1",
            "example.com:8080",
            "localhost",
            "localhost:3000",
            "127.0.0.1",
            "127.0.0.1:8080",
            "192.168.0.1/path",
            "foo:8080",
            "中文.com",
            "example.com.",
        ):
            self.assertTrue(looks_like_url(value), value)

    def test_windows_paths(self):
        self.assertTrue(is_windows_path(r"C:\games\a.swf"))
        self.assertTrue(is_windows_path("D:/games/a.swf"))
        self.assertTrue(is_windows_path(r"\\server\share\a.swf"))
        self.assertFalse(is_windows_path("C:games"))
        self.assertTrue(looks_like_url(r"C:\games\a.swf"))

    def test_search_queries(self):
        for value in (
            "python",
            "python tutorial",
            "how to build a flash game",
            "3.14",
            "1.2.3.4.5",
            "999.999.999.999",
            "foo:bar",
            "flash player",
            "flash-player",
        ):
            self.assertFalse(looks_like_url(value), value)

    def test_empty(self):
        self.assertFalse(looks_like_url(""))
        self.assertFalse(looks_like_url("   "))


if __name__ == "__main__":
    unittest.main()
