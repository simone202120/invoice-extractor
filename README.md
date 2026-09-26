# invoice-extractor

LangChain pipeline that turns invoices and receipts (PDF or text) into validated, structured JSON, with consistency checks and self-correcting retries.

> Status: work in progress. See [`docs/design.md`](docs/design.md) for scope and design.

## Development

This project is developed with an AI-assisted workflow using [Claude Code](https://claude.com/claude-code):
project context in [`CLAUDE.md`](CLAUDE.md), specialized agents, slash commands and hooks in
[`.claude/`](.claude/) (auto-formatting, secret protection, session context).

```bash
uv sync
uv run pytest
```

## License

MIT
