# Compound Brain

**For everyone who saves articles to "Read Later" and never reads them again.**

A bot that reads your saved articles, finds patterns, and compounds analysis week after week — automatically.

---

## Quick Start

**Runs on your machine. macOS, Linux, Windows. No server needed.**

### macOS / Linux

```bash
bash <(curl -s https://raw.githubusercontent.com/challengekim/compound-brain/main/install.sh)
```

### Windows

```powershell
git clone https://github.com/challengekim/compound-brain
cd compound-brain
pip install -r requirements.txt
python setup_wizard.py
python main.py
```

### What the wizard sets up

- **LLM** — Ollama (no API key, $0) / Gemini (free key) / OpenRouter / OpenAI / Claude
- **Telegram bot** — step-by-step guide + auto chat ID detection
- **Vault folder** — where your saved articles live

---

## Save Articles (5 ways)

| Method | Where | How |
|--------|-------|-----|
| **Telegram** | Phone / desktop | Send a URL to your bot |
| **Claude Code** | Terminal | `/save <URL>` — AI extracts + summarizes + categorizes + tags |
| **CLI** | Terminal | `python3 main.py --save <URL>` |
| **Auto** | Runs daily | Top 3 trend articles saved to vault automatically |
| **Manual** | Any editor | Create a `.md` file with YAML frontmatter |

---

## What the Bot Does With Your Saves

| Briefing | Schedule | What It Does |
|----------|----------|-------------|
| **Trend Digest** | Daily 10:00 | AI curates 5-7 top stories from HN, Reddit AI, GeekNews |
| **LinkedIn Draft** | Daily 11:30 | Auto-generated post from your notes + trends |
| **Weekly Compound** | Sat 10:00 | Last 4 weeks of reports feed into this week's analysis. Tag connections. Project ideas. |
| **Monthly Meta** | 1st of month | System self-diagnosis: collection bias, idea-to-code tracking (AI-estimated) |

All schedules configurable in `config.yaml`.

---

## How Compound Learning Works (real example)

**Week 1** — Save 7 articles.
```
→ 3 themes found: "agent architecture", "AI-native orgs", "token optimization"
→ Suggests: "Apply token optimization to your project's API costs"
```

**Week 3** — Previous reports feed into analysis.
```
→ "Interest evolved from architecture → practical workflows"
→ Notes auto-linked: "Marketing automation" ↔ "Agent orchestration" (shared tags)
→ Cross-project suggestion generated
```

**Week 8** — 50+ notes accumulated.
```
→ 8-week learning trajectory visible
→ Cross-project insights: "Week 2's framework can power your side project's recommendation engine"
```

**Month-end** — Meta-review.
```
→ "78 notes. 40% AI Engineering, 25% Business, 20% Marketing"
→ "3 of 12 ideas became actual code — 25% conversion"
→ "Blind spot: no DevOps articles. Consider diversifying."
```

**Without this**: Read → forget → read the same thing again.
**With this**: Save → analyze → patterns compound → track what got done.

*(Results from a 10-week simulation with real vault data)*

---

## How This Was Built

This isn't from a single idea. It came from researching dozens of open-source projects and frameworks — then figuring out how to combine them so knowledge actually compounds.

**The key question**: "How do I connect these separate tools so insights accumulate and improve my work?"

### Inspirations

**Projects:**

| Project | How It Influenced This |
|---------|----------------------|
| [karpathy/autoresearch](https://github.com/karpathy/autoresearch) | Self-improvement via LLM mutation loops |
| [VoidLight00/autoimprove-cc](https://github.com/VoidLight00/autoimprove-cc) | Binary eval + auto-fix for skills |
| [olelehmann100kMRR/autoresearch-skill](https://github.com/olelehmann100kMRR/autoresearch-skill) | 95%+ target via mutation |
| [mvanhorn/last30days-skill](https://github.com/mvanhorn/last30days-skill) | Multi-platform trend research |
| [Yeachan-Heo/oh-my-claudecode](https://github.com/Yeachan-Heo/oh-my-claudecode) | `/wiki`, `/skill-eval`, `/save` skills |

**Articles:**

| Article | Key Idea |
|---------|----------|
| [Karpathy — LLM Knowledge Bases](https://x.com/karpathy/status/2039805659525644595) | LLM compiles .md wiki (not RAG) |
| [unclejobs-ai — LLM Wiki Guide](https://gist.github.com/unclejobs-ai/7af4a9e3446751b8e2c3bc66d23fa0ac) | Practical wiki implementation |
| [Simpson Sim — Compound Knowledge](https://retn.kr/blog/compound-learning-ai-system/) | 4-stage loop: collect → structure → contextualize → apply |

**Frameworks:**
- **BASB** (Tiago Forte) — Capture → Organize → Distill → Express, all 4 automated
- **Zettelkasten** (Luhmann) — Note interconnection via tag co-occurrence analysis
- **GTD** (David Allen) — Action items auto-extracted from content

### Ecosystem

| Layer | Role | Standalone? |
|-------|------|:-----------:|
| **Compound Brain** (this repo) | Briefings, trends, compound analysis, meta-review | Yes |
| **Claude Code + OMC** | `/save`, `/wiki`, `/skill-eval`, `/learn` | Requires [Claude Code](https://claude.ai/claude-code) |
| **Markdown Vault** | Storage (Obsidian, Logseq, VS Code, any folder) | Yes |

> The bot works independently. Claude Code companion layer is optional.

### vs. Existing Tools

| Tool | Monthly | What's Missing | Compound Brain |
|------|---------|----------------|----------------|
| Readwise | $8 | No cross-note analysis | Finds patterns across notes |
| Notion AI | $10 | Notes stay isolated | Tag connections + weekly continuity |
| Feedly | $6 | Raw firehose | AI curates for your project context |
| **This bot** | **$0** | | **All of the above + compound analysis** |

---

## Configuration

| File | Contains |
|------|----------|
| `config.yaml` | Schedule, projects, vault path, LLM settings |
| `.env` | API keys, bot tokens |

See [`config.example.yaml`](config.example.yaml) for all options.

---

## Requirements

- Python 3.9+ (macOS, Linux, Windows)
- Telegram bot ([free, 2 min](https://core.telegram.org/bots#botfather))
- **One of**: [Ollama](https://ollama.com) ($0, local) / [Gemini](https://aistudio.google.com/apikey) ($0, free key) / OpenRouter / OpenAI / Claude

---

## Background / Docker

```bash
nohup python3 main.py &                              # macOS/Linux
Start-Process python main.py -WindowStyle Hidden      # Windows
docker-compose up -d                                   # Docker (any OS)
```

---

## Updating

```bash
cd compound-brain && git pull
pip install -r requirements.txt    # only if deps changed
```

Your `config.yaml`, `.env`, and vault stay untouched.

---

## Changelog

### v0.2.1 (2026-04-11)

- **Fix**: Schedules now work without `config.yaml`. Previously, if `config.yaml` was missing or had no `schedule:` section, no briefings would run. Now falls back to built-in defaults (trend 10:00, linkedin 11:30, knowledge sat 10:00, meta 1st 11:00).
- **Fix**: Partial `schedule:` sections now merge with defaults. Setting only `trend: "14:00"` keeps the other 3 briefings on their default times instead of silently dropping them.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Questions? [Open an issue](https://github.com/challengekim/compound-brain/issues) or email kimtaewoo1201@gmail.com.

## License

MIT
