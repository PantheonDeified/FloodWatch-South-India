from __future__ import annotations

import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "download_nwdp_history.py"


def load_script():
    # This unit test only covers the pure filename helper, so stub the optional
    # network/parser imports and keep the lightweight CI environment independent.
    requests_stub = types.ModuleType("requests")
    requests_stub.Session = object
    bs4_stub = types.ModuleType("bs4")
    bs4_stub.BeautifulSoup = object
    with patch.dict(sys.modules, {"requests": requests_stub, "bs4": bs4_stub}):
        spec = importlib.util.spec_from_file_location("nwdp_downloader_under_test", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        assert spec is not None and spec.loader is not None
        spec.loader.exec_module(module)
    return module


class NwdpResourceFilenameTests(unittest.TestCase):
    def test_same_title_different_resource_urls_get_different_filenames(self):
        downloader = load_script()
        first = downloader.slugify("Kerala discharge 2001-2025.csv", "https://example.gov/resource/a")
        second = downloader.slugify("Kerala discharge 2001-2025.csv", "https://example.gov/resource/b")
        self.assertNotEqual(first, second)
        self.assertTrue(first.endswith(".csv"))
        self.assertTrue(second.endswith(".csv"))
        self.assertLessEqual(len(first), 150)
        self.assertLessEqual(len(second), 150)

    def test_same_resource_url_gets_stable_filename(self):
        downloader = load_script()
        first = downloader.slugify("Andhra Pradesh discharge 2001-2025.csv", "https://example.gov/resource/a")
        second = downloader.slugify("Andhra Pradesh discharge 2001-2025.csv", "https://example.gov/resource/a")
        self.assertEqual(first, second)

    def test_filename_uses_safe_characters(self):
        downloader = load_script()
        filename = downloader.slugify("../../ Kerala / discharge & levels.csv", "https://example.gov/resource/a")
        self.assertTrue(filename.endswith(".csv"))
        self.assertNotIn("/", filename)
        self.assertNotIn("\\", filename)


if __name__ == "__main__":
    unittest.main()
