# Contributing

Thanks for your interest in Compound Brain!

## How to contribute

1. Fork the repo
2. Create a branch: `git checkout -b feat/your-feature`
3. Make your changes
4. Test: `python3 main.py --help` (should show all options)
5. Commit: `git commit -m "feat: description"`
6. Push and open a PR

## Areas where help is needed

- **Prompt improvements** — edit files in `prompts/en/` or `prompts/ko/`
- **New LLM providers** — add to `summarizer.py` and `config.py`
- **Additional trend sources** — extend `trend_fetcher.py`
- **Delivery channels** — Slack, Discord, email
- **Tests** — we have none yet. Any test coverage is welcome.
- **i18n** — `briefing_composer.py` UI strings are Korean-only

## Code style

- Python 3.9+ compatible
- No type annotations required (but welcome)
- Keep functions small
- Error handling: log and continue, don't crash

## Questions or feedback?

- **Bug reports / feature requests**: [Open an issue](https://github.com/challengekim/compound-brain/issues)
- **Code contributions**: Fork → branch → PR
- **General questions**: [Discussions](https://github.com/challengekim/compound-brain/discussions) or email kimtaewoo1201@gmail.com
