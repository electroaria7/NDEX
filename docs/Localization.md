# Localization

NDEX apps use English source text as the translation key. Translations are plain JSON files, so a language can be added without changing code.

## Add a language

1. Copy `ndex_common/locales/ko.json` to `ndex_common/locales/<code>.json` (for example `ja.json`).
2. Set `__meta__.name` to the language's own name (shown in the Launcher's Language selector) and `__meta__.code` to the code.
3. Run `python tools/i18n_extract.py` to add every translatable string with an empty value.
4. Fill in the values. The language then appears in the selector automatically.

To try a translation without rebuilding, put the file in `%LOCALAPPDATA%\NDEX\locales\<code>.json`. Entries there override the bundled file key by key, and a file that exists only there still adds a language.

## File format

```json
{
  "__meta__": {"name": "한국어", "code": "ko"},
  "Open": "열기",
  "Copied {count} files": "{count}개 파일을 복사했습니다",
  "__plural__": {"{count} file": ["{count}개 파일"]}
}
```

- Keys are the exact English strings used in the code.
- `__plural__` maps an English singular to a list of forms: index 0 is used when the count is 1, index 1 otherwise. A single form is used for every count (right for Korean and Japanese).
- Files are UTF-8.

## Rules

- Keep placeholders such as `{count}` and `{name}` exactly as written, but you may move them within the sentence. Keep `\n` line breaks.
- An empty string means "not translated yet": the app shows the English text. A missing key does the same, so a partial translation is always safe.
- Do not translate the `__meta__` code.

## Language setting

Settings > `shared.language` in the shared settings file holds `system` (default, follows the Windows display language) or a code such as `ko`. The Launcher's footer has a Language selector. A change applies the next time an app starts.

## For developers

```python
from ndex_common.i18n import _, ngettext

_("Open")
_("Copied {count} files").format(count=n)
ngettext("{count} file", "{count} files", n).format(count=n)
```

- Call `i18n.init("<app>")` once at start-up, before building any UI.
- Use string literals inside `_()` and `ngettext()`; the extractor reads them statically. Do not build the English text with f-strings; use named `{placeholders}` and `.format()`.
- `python tools/i18n_extract.py [--prune]` syncs every locale file with the source. `--check` writes nothing and exits non-zero if any locale lacks a key.
- Frozen builds bundle `ndex_common/locales` as data.
