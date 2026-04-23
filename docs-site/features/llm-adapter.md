# Optional LLM adapter

The planner can keep its default local orchestrator path or use a user-supplied OpenAI or Anthropic key for live suggestions.

## Providers

- `Local` remains the default and does not call any third-party LLM API.
- `OpenAI` uses `gpt-4o-mini` through `POST /v1/chat/completions`.
- `Anthropic` uses `claude-haiku-4-5-20251001` through `POST /v1/messages`.

## Security model

- The API key is sent only in request headers: `X-AB-LLM-Provider` and `X-AB-LLM-Token`.
- The browser keeps the provider and key only in `sessionStorage` for the active tab lifecycle, and the UI clears them on unload so refresh or tab close resets back to `Local`.
- The backend uses the key for the current request only.
- The backend does not store, log, snapshot, or persist the key in SQLite.
- Logging sanitization masks sensitive headers such as `X-AB-LLM-Token`, `Authorization`, and `X-API-Key`.

## Getting API keys

- OpenAI API keys: [platform.openai.com/settings/organization/api-keys](https://platform.openai.com/settings/organization/api-keys)
- Anthropic API console: [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys)

## Cost notes

- Local suggestions are free.
- OpenAI lists `gpt-4o-mini` at low token rates, so a short demo-sized JSON suggestion is often around `$0.0002`, depending on prompt and response length.
- Anthropic lists Claude Haiku 4.5 at higher per-token rates than `gpt-4o-mini`, but still low enough for lightweight demo traffic.
- Always treat these as usage-based estimates, not fixed prices per click.

## UX behavior

- The settings panel exposes `Local`, `OpenAI`, and `Anthropic`.
- Remote providers use a password-style field labeled `API key (session only, never saved)`.
- If a remote provider is selected without a key, the UI warns that the request will fall back to local suggestions.
