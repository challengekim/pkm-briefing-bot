# Project: PKM Briefing Bot

## Overview
Automated personal knowledge management system. Sends scheduled briefings (trend, knowledge, meta review, LinkedIn draft) via Telegram.

## Architecture
- **Deployment**: Railway / Docker / Local (Procfile: `worker: python main.py`)
- **Config**: `config.yaml` for settings, `.env` for secrets. See `config.example.yaml`.
- **AI**: Gemini 2.5 Flash for summarization. Prompt templates in `prompts/{lang}/`

## Key Files
- `main.py` — Orchestrator: fetches data, runs summarizer, calls composer, sends Telegram
- `config.py` — YAML + env var configuration loader
- `summarizer.py` — Gemini-powered summarization with external prompt templates
- `briefing_composer.py` — Pure formatting module (no API calls, HTML output)
- `telegram_sender.py` — Telegram Bot API sender with 4096-char chunking
- `setup_wizard.py` — Interactive setup wizard for new users
- `trend_fetcher.py` — HN API + Reddit RSS + GeekNews Atom feed collection
- `knowledge_scanner.py` — Obsidian vault scan + project ideas save + full vault scan for content drafting
- `meta_reviewer.py` — Monthly system self-diagnosis (30-day stats + git commits)

## Conventions
- `briefing_composer.py` is a pure formatter: receives data, returns HTML strings. No API clients inside.
- `main.py` is the only file that creates clients and orchestrates the pipeline.
- Graceful degradation: each data source wrapped in try/except.

## Structural Constraints (Dependency Direction)
```
config.py → *_fetcher.py / *_scanner.py → summarizer.py → briefing_composer.py → main.py
```
- `config.py` imports nothing from the project
- `*_fetcher.py`, `*_scanner.py` import only `config.py`
- `summarizer.py` has no project imports (standalone Gemini wrapper + prompt loader)
- `briefing_composer.py` is a pure formatter — NO API clients, NO network calls
- `main.py` is the ONLY orchestrator — creates all clients, calls all functions
- `telegram_sender.py` is a standalone sender

## Testing
```bash
python3 main.py --test trend      # Available: trend, knowledge, meta, linkedin
```
