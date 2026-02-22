# Security

## Threat Model

- **Secrets**: API keys, tokens, OAuth credentials must never be logged or returned to the LLM.
- **Write actions**: All write operations require human approval before execution.
- **External content**: Treat all fetched content (web, email) as untrusted.
- **Filesystem**: File tools are sandboxed; no access outside the sandbox directory.

## Secrets Management

- Store secrets in `.env` (gitignored). Never commit.
- `OPENAI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `GITHUB_TOKEN`, `GOOGLE_*` – required per integration.
- `.google_tokens.json` – Google OAuth tokens (gitignored). Rotate if compromised.
- `.yahoo_tokens.json` – Yahoo OAuth tokens (gitignored). Rotate if compromised.

## Tool Permissions

- **GREEN (read)**: Execute immediately. Examples: gmail_search, calendar_today, file_read.
- **YELLOW (write)**: Require `APPROVE <id>` before execution. Examples: gmail_send, file_write.
- **RED**: Disabled. No shell execution, no arbitrary OS commands.

## Sandbox Rules (file tools)

- All paths relative to `FILES_SANDBOX_DIR`.
- Reject absolute paths, `..`, and path traversal.
- Sandbox directory created on first use.

## Incident Response

1. Revoke compromised tokens (Telegram, OpenAI, Google, Yahoo, GitHub).
2. Rotate `.env`, `.google_tokens.json`, and `.yahoo_tokens.json`.
3. Review approval logs in `approvals` table.
