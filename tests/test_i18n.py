from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ndex_common import i18n

REPO = Path(__file__).resolve().parent.parent


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


class I18nTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.bundled = root / "bundled"
        self.appdata = root / "appdata"
        self.bundled.mkdir()
        patches = [
            mock.patch.dict(os.environ, {"LOCALAPPDATA": str(self.appdata)}),
            mock.patch.object(i18n, "bundled_locales_dir", lambda: self.bundled),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(i18n.init, "test", "en")
        _write(self.bundled / "en.json", {"__meta__": {"name": "English", "code": "en"}})
        _write(
            self.bundled / "ko.json",
            {
                "__meta__": {"name": "한국어", "code": "ko"},
                "Open": "열기",
                "Close": "",
                "Copied {count} files": "{count}개 파일 복사됨",
                "__plural__": {"{count} file": ["{count}개 파일"]},
            },
        )

    def test_lookup_and_fallback(self) -> None:
        i18n.init("test", "ko")
        self.assertEqual(i18n._("Open"), "열기")
        self.assertEqual(i18n._("Close"), "Close")  # empty = untranslated
        self.assertEqual(i18n._("Never seen"), "Never seen")
        i18n.init("test", "xx")  # unknown language
        self.assertEqual(i18n.current_language(), "en")
        self.assertEqual(i18n._("Open"), "Open")

    def test_placeholders_survive_formatting(self) -> None:
        i18n.init("test", "ko")
        self.assertEqual(i18n._("Copied {count} files").format(count=3), "3개 파일 복사됨")

    def test_plural(self) -> None:
        self.assertEqual(i18n.ngettext("{count} file", "{count} files", 1), "{count} file")
        self.assertEqual(i18n.ngettext("{count} file", "{count} files", 2), "{count} files")
        i18n.init("test", "ko")
        self.assertEqual(i18n.ngettext("{count} file", "{count} files", 1).format(count=1), "1개 파일")
        self.assertEqual(i18n.ngettext("{count} file", "{count} files", 5).format(count=5), "5개 파일")
        self.assertEqual(i18n.ngettext("{count} dir", "{count} dirs", 2), "{count} dirs")

    def test_override_folder_wins_per_key(self) -> None:
        _write(
            self.appdata / "NDEX" / "locales" / "ko.json",
            {"Open": "오픈", "Close": "닫기", "Other": ""},
        )
        i18n.init("test", "ko")
        self.assertEqual(i18n._("Open"), "오픈")
        self.assertEqual(i18n._("Close"), "닫기")
        self.assertEqual(i18n._("Copied {count} files"), "{count}개 파일 복사됨")

    def test_available_languages_discovery(self) -> None:
        self.assertEqual(i18n.available_languages(), [("en", "English"), ("ko", "한국어")])
        _write(self.appdata / "NDEX" / "locales" / "ja.json", {"__meta__": {"name": "日本語"}})
        (self.bundled / "broken.json").write_text("{not json", encoding="utf-8")
        codes = dict(i18n.available_languages())
        self.assertEqual(codes["ja"], "日本語")
        self.assertEqual(codes["broken"], "broken")
        self.assertEqual(list(codes)[0], "en")

    def test_system_language_mapping(self) -> None:
        kernel = mock.Mock()
        windll = mock.Mock(kernel32=kernel)
        with mock.patch("ctypes.windll", windll, create=True):
            kernel.GetUserDefaultUILanguage.return_value = 0x0412
            self.assertEqual(i18n.system_language(), "ko")
            kernel.GetUserDefaultUILanguage.return_value = 0x0409
            self.assertEqual(i18n.system_language(), "en")
        with mock.patch("ctypes.windll", mock.Mock(side_effect=OSError), create=True), mock.patch.object(
            i18n.locale, "getlocale", return_value=("Korean_Korea", "cp949")
        ):
            windll_fail = mock.Mock()
            windll_fail.kernel32.GetUserDefaultUILanguage.side_effect = OSError
            with mock.patch("ctypes.windll", windll_fail, create=True):
                self.assertEqual(i18n.system_language(), "ko")

    def test_system_choice_resolves_to_available_only(self) -> None:
        with mock.patch.object(i18n, "system_language", return_value="ko"):
            self.assertEqual(i18n.resolve_language("system"), "ko")
        with mock.patch.object(i18n, "system_language", return_value="fr"):
            self.assertEqual(i18n.resolve_language("system"), "en")

    def test_setting_persistence(self) -> None:
        self.assertEqual(i18n.configured_language(), "system")
        i18n.set_language("KO")
        self.assertEqual(i18n.configured_language(), "ko")
        self.assertEqual(i18n.init("test"), "ko")
        self.assertEqual(i18n._("Open"), "열기")
        i18n.set_language("system")
        self.assertEqual(i18n.configured_language(), "system")

    def test_lookup_before_init_is_english(self) -> None:
        i18n._messages, i18n._plurals = {}, {}
        self.assertEqual(i18n._("Open"), "Open")


class ExtractorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        spec = importlib.util.spec_from_file_location("i18n_extract", REPO / "tools" / "i18n_extract.py")
        cls.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.tool)

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.src = root / "src"
        self.locales = root / "locales"
        self.src.mkdir()
        (self.src / "a.py").write_text(
            "from ndex_common.i18n import _, ngettext\r\n"
            'x = _("Open")\r\n'
            'y = _("Copied {count}").format(count=1)\r\n'
            'z = ngettext("{count} file", "{count} files", 2)\r\n'
            "w = _(variable)\r\n"
            'v = f(_("Nested"))\r\n',
            encoding="utf-8",
        )
        _write(
            self.locales / "ko.json",
            {"__meta__": {"name": "한국어"}, "Open": "열기", "Old": "옛"},
        )
        _write(self.locales / "en.json", {"__meta__": {"name": "English"}})

    def run_tool(self, *extra: str) -> int:
        return self.tool.main([str(self.src), "--locales", str(self.locales), *extra])

    def test_extract_finds_literals_only(self) -> None:
        messages, plurals = self.tool.extract_tree([self.src])
        self.assertEqual(messages, {"Open", "Copied {count}", "Nested"})
        self.assertEqual(plurals, {"{count} file"})

    def test_check_flags_missing_without_writing(self) -> None:
        before = (self.locales / "ko.json").read_bytes()
        self.assertEqual(self.run_tool("--check"), 1)
        self.assertEqual((self.locales / "ko.json").read_bytes(), before)

    def test_update_adds_empty_keys_sorted_and_keeps_unused(self) -> None:
        self.assertEqual(self.run_tool(), 0)
        data = json.loads((self.locales / "ko.json").read_text(encoding="utf-8"))
        self.assertEqual(data["Open"], "열기")
        self.assertEqual(data["Copied {count}"], "")
        self.assertEqual(data["Old"], "옛")
        self.assertEqual(data["__plural__"], {"{count} file": ["", ""]})
        keys = [k for k in data if k not in ("__meta__", "__plural__")]
        self.assertEqual(keys, sorted(keys))
        self.assertEqual(json.loads((self.locales / "en.json").read_text(encoding="utf-8")), {"__meta__": {"name": "English"}})
        self.assertEqual(self.run_tool("--check"), 0)

    def test_prune_removes_unused_with_force(self) -> None:
        self.assertEqual(self.run_tool("--prune", "--force"), 0)
        data = json.loads((self.locales / "ko.json").read_text(encoding="utf-8"))
        self.assertNotIn("Old", data)
        self.assertIn("Open", data)

    def test_prune_refused_for_narrower_paths_without_force(self) -> None:
        before = (self.locales / "ko.json").read_bytes()
        self.assertEqual(self.run_tool("--prune"), 2)
        self.assertEqual((self.locales / "ko.json").read_bytes(), before)

    def test_prune_never_removes_keys_used_in_default_set(self) -> None:
        used_messages, used_plurals = self.tool.extract_tree(self.tool.default_roots())
        message = sorted(used_messages)[0]
        plural = sorted(used_plurals)[0]
        _write(
            self.locales / "ko.json",
            {"__meta__": {"name": "x"}, message: "t", "Old": "o", "__plural__": {plural: ["a"], "Gone": ["b"]}},
        )
        self.assertEqual(self.run_tool("--prune", "--force"), 0)
        data = json.loads((self.locales / "ko.json").read_text(encoding="utf-8"))
        self.assertEqual(data[message], "t")
        self.assertNotIn("Old", data)
        self.assertEqual(data["__plural__"][plural], ["a"])
        self.assertNotIn("Gone", data["__plural__"])

    def test_default_sources_cover_every_app_root(self) -> None:
        names = {path.name for path in self.tool.default_roots()}
        for expected in ("main.py", "src", "dsb_image_manager", "ndex_auto_selector", "ndex_frame",
                         "ndex_launcher", "ndex_common"):
            self.assertIn(expected, names)
        self.assertTrue(self.tool.covers_default_set(self.tool.default_roots()))
        self.assertTrue(self.tool.covers_default_set([REPO]))
        self.assertFalse(self.tool.covers_default_set([REPO / "ndex_frame"]))

    def test_printing_on_cp949_console_does_not_raise(self) -> None:
        import io
        import sys

        _write(self.locales / "ko.json", {"__meta__": {"name": "x"}, "Unused \u2192 \u00e9\u2603": ""})
        stream = io.TextIOWrapper(io.BytesIO(), encoding="cp949", errors="strict")
        with mock.patch.object(sys, "stdout", stream):
            self.assertEqual(self.run_tool(), 0)
            stream.flush()

if __name__ == "__main__":
    unittest.main()
