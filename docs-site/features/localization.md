# Localization

The product ships with seven UI and export locales: English, Russian, German, Spanish, French, Simplified Chinese, and Arabic. Frontend leaf-key parity is enforced at 925 keys per locale (matching `en`); backend export strings are 235 keys per locale.

## Shipped locales

| Locale | Coverage | Notes |
| --- | --- | --- |
| `en` | full | Default UI and export language. |
| `ru` | full | Full UI and deterministic report support. |
| `de` | full | Full UI and export locale with regional fallback support. |
| `es` | full | Full UI and export locale with regional fallback support. |
| `fr` | full | Full UI and export locale with regional fallback support. |
| `zh` | full | Simplified Chinese UI and export locale. |
| `ar` | full + RTL | Arabic UI and export locale; switching to `ar` flips `document.documentElement.dir` to `rtl` and the layout uses `inset-inline-*` / `margin-inline-*` / `border-inline-*` logical CSS properties. |

## Runtime behavior

- The header language switcher (7 buttons, `aria-pressed`) persists the selected locale in `localStorage`.
- Query-string overrides such as `?lang=de` take precedence over browser defaults.
- Backend export endpoints honor `Accept-Language`.
- Regional tags fall back to the primary locale: `de-AT` → `de`, `es-MX` → `es`, `en-GB` → `en`, `zh-TW` → `zh`, `ar-EG` → `ar`.
- Unsupported locales fall back to English.
- Locale JSONs are lazy-loaded from `app/frontend/public/locales/` via `i18next-http-backend`; only the active locale is fetched at startup, the rest on-demand at switch.

## Example

```bash
curl -X POST http://127.0.0.1:8008/api/v1/export/markdown \
  -H "Accept-Language: de" \
  -H "Content-Type: application/json" \
  -d @docs/demo/sample-report.json
```
