# PKM Briefing Bot

**A self-improving personal knowledge management system that reads, collects, summarizes, connects, suggests, and evolves -- automatically.**

> Combines the best ideas from Building a Second Brain (Tiago Forte), Zettelkasten (Luhmann), Compound Learning, and AI-native workflows into a single automated pipeline.

---

## What This Does

1. **Content Capture** -- Save any web link with `/save <URL>`. AI extracts, categorizes, tags, and summarizes it into your vault.
2. **Morning Briefing** -- Daily digest of today's calendar, newsletter summaries, important emails, and auto-extracted action items.
3. **Trend Digest** -- Curated top stories from Hacker News, Reddit AI, and GeekNews, filtered by relevance to your projects.
4. **LinkedIn Draft** -- AI-generated post from your recent notes and trends, ready to edit and publish.
5. **Evening Review** -- Afternoon email catch-up and tomorrow's schedule preview.
6. **Weekly Knowledge Compounding** -- Cross-references everything you saved this week, discovers patterns, and generates project ideas.
7. **Monthly Meta-Review** -- The system diagnoses itself: collection blind spots, idea-to-code conversion rates, and improvement suggestions.

---

## The Methodology: Why This Works

### Standing on the Shoulders of Giants

This system didn't emerge from scratch. It synthesizes proven knowledge management frameworks and evolves them with AI automation.

#### 1. Building a Second Brain (CODE Method)

Tiago Forte's framework for personal knowledge management follows four stages: Capture, Organize, Distill, Express. This bot automates every one of them:

- **Capture**: `/save` extracts and structures web content with AI-generated summaries
- **Organize**: Auto-categorization into vault folders by topic
- **Distill**: Gemini AI summarizes newsletters, trends, and accumulated knowledge
- **Express**: LinkedIn draft generation, weekly reports, email digests

#### 2. Zettelkasten (Luhmann's Slip-Box)

Niklas Luhmann wrote 70 books and 400 papers using a system of interconnected notes. The power wasn't in individual notes but in the connections between them.

The weekly knowledge report uses tag co-occurrence analysis to find real connections between notes -- notes sharing 2+ tags are surfaced as linked pairs. The AI then builds on these programmatic connections to discover deeper thematic patterns across your vault.

#### 3. Compound Learning (Farnam Street)

Shane Parrish's insight: knowledge compounds like interest, but only if you actively review and connect it. Most people save articles and never look at them again.

The weekly knowledge report doesn't just list what you saved. It receives the previous week's report as input, finds patterns, and tracks how themes evolve over time. Each week's analysis explicitly references and builds on the last -- cumulative learning trends emerge naturally across weeks.

#### 4. Getting Things Done (GTD)

David Allen's core principle: your brain is for having ideas, not holding them. Action items are automatically extracted from every email summary and meeting prep note. The morning briefing surfaces "what needs doing today" without you having to process your inbox manually.

#### 5. AI-Native Knowledge Work (Karpathy's LLM OS)

Andrej Karpathy's vision of LLMs as an operating system layer for human work. This bot treats AI not as a chatbot you query, but as infrastructure that works in the background -- it reads your emails, scans your vault, writes your LinkedIn posts, and diagnoses its own performance.

### What We Took From Each Tool — and What We Changed

| Tool / Method | What It Does Well | What's Missing | How This Bot Improves It |
|--------------|-------------------|----------------|--------------------------|
| **Readwise** ($8/mo) | Syncs highlights, spaced repetition review | Passive — you still review manually, no cross-note analysis | Weekly report auto-reviews everything, finds patterns you missed, suggests project applications |
| **Notion AI** ($10/mo) | Summarizes individual notes | No cross-note connections, no temporal tracking | Tag co-occurrence analysis links related notes; previous week's report feeds into this week |
| **Feedly / Inoreader** ($6/mo) | Aggregates RSS feeds | Raw firehose — no curation, no personal context | AI curates 5-7 key stories, filtered by your project context |
| **Obsidian + Dataview** (free) | PKM vault with queries | Manual tagging, manual review, no automation | Same vault format — but scanning, summarizing, and connecting are automated |
| **Zapier / Make** ($20+/mo) | Connects SaaS tools | Visual builder, limited AI, per-action pricing | Python scheduler — unlimited runs, full LLM integration, $0 infra cost |
| **Morning Brew / TLDR** (free) | Curated newsletters | Generic — same content for everyone | Your subscriptions only, summarized with your project context |
| **ChatGPT / Claude chat** (free-$20) | Answers questions on demand | Pull-based — you have to ask; no memory across sessions | Push-based — briefings arrive automatically; weekly reports remember last week |

### The Compound Learning Loop

Existing tools are **one-way pipes**: content goes in, summary comes out, done. This system connects them into a **feedback loop where each week builds on the last**:

```
Save content --> AI summarizes --> Weekly patterns emerge --> Project ideas generated
     ^                                                              |
     |                                                              v
     +-------- Monthly meta-review diagnoses the system itself <----+
```

The meta-review diagnoses the system: what categories you're neglecting, which sources produce noise vs. insight, and whether AI-suggested ideas actually turned into code commits (tracked via structured idea status: proposed → implemented | abandoned).

**How compound learning actually works in this system:**
1. Week 1: Save 10 articles → AI finds 3 themes → suggests 2 project ideas
2. Week 2: Save 8 articles → AI receives Week 1's report → notices "AI agents" theme persists from last week → deeper analysis on that thread → new ideas build on Week 1's suggestions
3. Week 3: Tag analysis connects Week 1 and Week 3 notes via shared tags → AI traces a 3-week evolution of your interests → cumulative trend section shows where your learning is heading
4. Month-end: Meta-review checks which of the 6 suggested ideas actually became git commits → reports 33% conversion rate → suggests focusing on the themes that led to action

### Cost Comparison

| Tool | Monthly Cost | What You Get |
|------|-------------|-------------|
| Readwise | $8 | Highlight sync + review |
| Notion AI | $10 | Note summarization |
| Feedly Pro | $6 | RSS aggregation |
| **This bot** | **~$1-3** | **All of the above + auto-analysis + self-improvement** |

*Costs: Gemini API (~$1-3/mo at typical usage) + free hosting tier or ~$5/mo for Railway/Docker.*

---

## Quick Start

### Option 1: Guided Setup (Recommended)

```bash
git clone https://github.com/challengekim/pkm-briefing-bot
cd pkm-briefing-bot
pip install -r requirements.txt
python3 setup_wizard.py
python3 main.py --test morning
```

### Option 2: Manual Setup

1. Copy `config.example.yaml` to `config.yaml` and fill in your values
2. Copy `.env.example` to `.env` and add your API keys
3. Run `python3 setup_oauth.py --account personal` for Gmail/Calendar access
4. Test: `python3 main.py --test morning`

### Option 3: Docker

```bash
# First, set up credentials locally:
python3 setup_wizard.py

# Then run with Docker:
docker-compose up -d
```

> **Note**: OAuth2 requires a browser for the initial login. Run `setup_wizard.py` locally first, then Docker uses the generated `.env` file.

---

## Configuration

All configuration lives in two files:

| File | Contains | Example |
|------|----------|---------|
| `config.yaml` | Everything except secrets | Schedule times, newsletter senders, projects, vault path |
| `.env` | Secrets only | API keys, OAuth tokens |

See [`config.example.yaml`](config.example.yaml) for all options with comments.

---

## Briefing Types

| Type | Schedule | What It Does |
|------|----------|-------------|
| Morning | Daily 08:00 | Today's calendar + email summaries + meeting prep + action items |
| Trend | Daily 10:00 | Top stories from HN, Reddit AI, GeekNews -- curated by AI |
| LinkedIn | Daily 11:30 | AI-drafted post from your vault notes + trends |
| Evening | Daily 17:00 | Afternoon email summaries + tomorrow's schedule |
| Weekly | Fri 18:00 | Week in review: meetings, emails, next week preview |
| Knowledge | Sat 10:00 | Compound learning: patterns across saved notes + project ideas |
| Meta Review | 1st of month | System self-diagnosis: collection patterns, idea-to-code tracking |

All schedules are configurable in `config.yaml`.

---

## Architecture

```
config.yaml + .env
       |
   config.py          <-- Configuration loader
       |
   +---+----------------------------+
   |  gmail_client    calendar_client|  <-- Data Collection
   |  trend_fetcher   knowledge_scanner|
   +---+----------------------------+
       |
   summarizer.py      <-- AI Processing (Gemini)
       |                  prompts/ko/*.txt
       |                  prompts/en/*.txt
       |
   briefing_composer.py   <-- Formatting (pure HTML)
       |
   +---+---+
   |       |
telegram  email       <-- Delivery
```

### Data Flow

1. **Collect**: Clients fetch data from Gmail, Calendar, HN/Reddit, and the vault
2. **Summarize**: Gemini processes raw data using prompt templates (language-specific)
3. **Compose**: Pure formatting module renders HTML -- no API calls, no side effects
4. **Deliver**: Telegram for real-time alerts, email for weekly/monthly reports

---

## Obsidian Not Required

This bot works with **any markdown folder**. Obsidian, Logseq, VS Code, or just plain files -- as long as your notes have YAML frontmatter, the scanner can read them.

See [`vault_template/`](vault_template/) for the expected folder structure.

---

## Requirements

- Python 3.9+
- Gemini API key ([free tier available](https://aistudio.google.com/apikey))
- Telegram bot ([free, 2 minutes to create](https://core.telegram.org/bots#botfather))
- Google OAuth2 credentials (optional, for email/calendar features)

---

## Deployment

### Local

```bash
python3 main.py
```

### Docker

```bash
docker-compose up -d
```

### Railway

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new)

Set environment variables in the Railway dashboard and add `config.yaml` as a mounted file.

---

## Prompt Templates

AI prompts live in `prompts/` with language subdirectories:

```
prompts/
  ko/   <-- Korean prompts
  en/   <-- English prompts
```

You can customize the tone, length, and style of every briefing by editing these text files. No code changes required.

---

## Claude Code Skills (Companion)

If you use [Claude Code](https://claude.ai/claude-code), there's a companion skills bundle that adds `/save`, `/learn`, and `/recall` commands for capturing knowledge directly from your terminal:

```bash
cd skills/
bash install.sh
```

See [`skills/README.md`](skills/README.md) for details.

---

## Contributing

Contributions welcome! Areas where help is needed:

- Additional LLM provider support (OpenAI, Claude API)
- New briefing types
- Prompt improvements in `prompts/en/` and `prompts/ko/`
- Additional trend sources
- Alternative delivery channels (Slack, Discord, email-only)

---

## License

MIT
