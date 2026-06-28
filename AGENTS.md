# Agent Instructions

## Security: Bot Token Leak Prevention

- `telegram_config.py` contains `BOT_TOKEN` and `CHAT_ID` — these files are now in `.gitignore` and removed from git tracking.
- NEVER commit real bot tokens or secrets. Before any `git push`, verify no `telegram_config.py` with real tokens is staged.
- If you need to add a new `telegram_config.py` in a subdirectory, make sure `.gitignore` covers it.
