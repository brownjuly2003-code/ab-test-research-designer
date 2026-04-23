# Localization

The product ships with four UI and export locales: English, Russian, German, and Spanish.

## Shipped locales

| Locale | Coverage | Notes |
| --- | --- | --- |
| `en` | full | Default UI and export language. |
| `ru` | full | Full UI and deterministic report support. |
| `de` | full | Full UI and export locale with regional fallback support. |
| `es` | full | Full UI and export locale with regional fallback support. |

## Runtime behavior

- The header language switcher persists the selected locale in `localStorage`.
- Query-string overrides such as `?lang=de` take precedence over browser defaults.
- Backend export endpoints honor `Accept-Language`.
- Regional tags fall back to the primary locale: `de-AT` → `de`, `es-MX` → `es`, `en-GB` → `en`.
- Unsupported locales fall back to English.

## Example

```bash
curl -X POST http://127.0.0.1:8008/api/v1/export/markdown \
  -H "Accept-Language: de" \
  -H "Content-Type: application/json" \
  -d @docs/demo/sample-report.json
```
