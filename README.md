# Compound Brain

**For everyone who saves articles to "Read Later" and never reads them again.**

Compound Brain is a bot that reads your saved articles for you, finds patterns across them, and tells you what actually matters — every week, automatically.

> Built on Building a Second Brain, Zettelkasten, Compound Learning, GTD, and AI-native workflows.

---

## The Problem

You bookmark 10 articles a week. You read maybe 2. The rest sit in your "Read Later" folder forever. Sound familiar?

Even the ones you read — you forget them within days. The insights never connect. The patterns never emerge. You keep saving the same types of articles without realizing it.

**Compound Brain fixes this.** It reads everything you save, finds the patterns you missed, and builds on its own analysis week after week — so your knowledge actually compounds instead of collecting dust.

### How this was built

This isn't a tool built from a single idea. It came from months of researching dozens of open-source projects, AI skills, knowledge management frameworks, and workflow tools — then figuring out how to actually combine them into one system that produces real compound learning effects.

The key question was: **"How do I make all these separate tools work together so that knowledge actually accumulates and improves my work?"** Each piece (Karpathy's [autoresearch](https://github.com/karpathy/autoresearch) for self-improvement, his [LLM Wiki concept](https://x.com/karpathy/status/2039805659525644595) for persistent knowledge, [Last30Days](https://github.com/mvanhorn/last30days-skill) for trend research, [Simpson Sim's compound learning loop](https://retn.kr/blog/compound-learning-ai-system/), Tiago Forte's BASB, Luhmann's Zettelkasten) solves one problem well. But none of them connect to each other out of the box. This project is the result of figuring out those connections and building the glue that makes them compound.

---

## What This Does

1. **Save articles (3 ways)**:
   - **Telegram** — send a URL to your bot from your phone. Done. (mobile-friendly)
   - **CLI** — `python3 main.py --save <URL>`
   - **Auto** — top 3 trend articles saved daily without you doing anything
2. **Trend Digest** -- Curated top stories from Hacker News, Reddit AI, and GeekNews. **Top 3 are auto-saved to your vault** — your knowledge base grows even when you're not actively saving.
3. **LinkedIn Draft** -- AI-generated post from your recent notes and trends, ready to edit and publish.
4. **Weekly Knowledge Compounding** -- Cross-references everything you saved, discovers patterns using tag analysis, and feeds the last 4 weeks of reports into each new analysis. Your insights actually accumulate.
5. **Monthly Meta-Review** -- The system diagnoses itself: collection blind spots, idea-to-code conversion rates (AI-estimated), and improvement suggestions.

---

## What You Actually Do — and What You Get Back

### Your daily routine (30 seconds)

1. **See an interesting article on your phone?** Send the URL to your Telegram bot. That's it.
2. **Don't feel like saving anything?** The bot auto-saves top 3 trend articles daily.
3. **Check Telegram** — briefings arrive automatically.

Your vault grows whether you actively save or not.

### What the bot does for you (from a 10-week simulation with real vault data)

**Week 1** — You save 7 articles about AI agents and startup strategy.
```
→ Bot finds 3 themes: "agent architecture", "AI-native orgs", "token optimization"
→ Suggests: "Apply token optimization to your SaaS project's API costs"
```

**Week 3** — You save articles about marketing automation and knowledge management.
```
→ Bot receives Week 1-2 reports as input
→ Discovers: "Your interest in 'AI agents' has evolved from architecture → practical workflows"
→ Connects notes: "Marketing automation article" ↔ "Agent orchestration article" (shared tags: automation, ai-agents)
→ Suggests: "Combine agent orchestration with your marketing workflow for automated competitor analysis"
```

**Week 8** — You've accumulated 50+ notes across categories.
```
→ Bot traces 8-week evolution: "AI agents → practical workflows → business automation → 1-person company"
→ Cross-project insight: "The agent framework from Week 2 can power the recommendation engine in your side project"
→ Suggests specific actions for each of your registered projects
```

**Month-end** — Meta-review arrives.
```
→ "You saved 78 notes. 40% AI Engineering, 25% Business, 20% Marketing, 15% other"
→ "Top sources: Karpathy (5), GeekNews (8), Lenny Newsletter (4)"
→ "3 of 12 suggested ideas appeared in your git commits — 25% conversion rate"
→ "Blind spot: No Engineering/DevOps articles saved. Consider diversifying."
```

### The key difference from just reading articles

Without this system: You read → you forget → you read the same patterns again.

With this system: You save → AI analyzes → patterns emerge across weeks → ideas compound → you act on the best ones → the system tracks what worked.

---

## The Methodology: Why This Works

### Standing on the Shoulders of Giants

This system didn't emerge from scratch. It synthesizes proven knowledge management frameworks and evolves them with AI automation.

#### 1. Building a Second Brain (CODE Method)

Tiago Forte's framework for personal knowledge management follows four stages: Capture, Organize, Distill, Express. This bot automates every one of them:

- **Capture**: `/save` extracts and structures web content with AI-generated summaries
- **Organize**: Auto-categorization into vault folders by topic
- **Distill**: Gemini AI summarizes trends and accumulated knowledge
- **Express**: LinkedIn draft generation, weekly reports

#### 2. Zettelkasten (Luhmann's Slip-Box)

Niklas Luhmann wrote 70 books and 400 papers using a system of interconnected notes. The power wasn't in individual notes but in the connections between them.

The weekly knowledge report uses tag co-occurrence analysis to find real connections between notes -- notes sharing 2+ tags are surfaced as linked pairs. The AI then builds on these programmatic connections to discover deeper thematic patterns across your vault.

#### 3. Compound Learning (Farnam Street)

Shane Parrish's insight: knowledge compounds like interest, but only if you actively review and connect it. Most people save articles and never look at them again.

The weekly knowledge report doesn't just list what you saved. It receives the previous week's report as input, finds patterns, and tracks how themes evolve over time. Each week's analysis explicitly references and builds on the last -- cumulative learning trends emerge naturally across weeks.

#### 4. AI-Native Knowledge Work (Karpathy's LLM OS)

Andrej Karpathy's vision of LLMs as an operating system layer for human work. This bot treats AI not as a chatbot you query, but as infrastructure that works in the background -- it scans your vault, writes your LinkedIn posts, and diagnoses its own performance.

### The Full Ecosystem

This bot is one piece of a larger knowledge management system. Here's what each layer does:

| Layer | What It Is | Standalone? |
|-------|-----------|:-----------:|
| **Compound Brain** (this repo) | Automated briefings, trend curation, compound learning loop, meta-review | Yes |
| **Claude Code + OMC** | `/save` content capture, `/wiki` knowledge base, `/skill-eval` auto-improvement, `/learn` lesson tracking | Requires [Claude Code](https://claude.ai/claude-code) |
| **Markdown Vault** | Knowledge storage (Obsidian, Logseq, VS Code, or any folder) | Yes |

### Inspirations and Sources

This system combines ideas from open-source projects, articles, and frameworks we found online:

**Frameworks:**

| Framework | Author | How We Applied It |
|-----------|--------|-------------------|
| Building a Second Brain | Tiago Forte — CODE method (Capture→Organize→Distill→Express) | `/save` captures + auto-categorizes; bot distills and expresses via briefings |
| Zettelkasten | Niklas Luhmann — Interconnected note system | Tag co-occurrence analysis finds real connections between notes programmatically |

**Open-Source Projects:**

| Project | Repo | How We Applied It |
|---------|------|-------------------|
| **Karpathy's autoresearch** | [karpathy/autoresearch](https://github.com/karpathy/autoresearch) — Automated research via LLM mutation loops | The core idea: evaluate output → mutate → re-evaluate → repeat until quality threshold. Applied to skill improvement |
| **autoimprove-cc** | [VoidLight00/autoimprove-cc](https://github.com/VoidLight00/autoimprove-cc) — autoresearch for Claude Code SKILL.md | Binary assertion evals + git commit on improvement. Adapted for `/skill-eval` |
| **autoresearch-skill** | [olelehmann100kMRR/autoresearch-skill](https://github.com/olelehmann100kMRR/autoresearch-skill) — 857 stars | 3-6 binary evals, one mutation at a time, 95%+ target. Informed our eval design |
| **Last30Days** | [mvanhorn/last30days-skill](https://github.com/mvanhorn/last30days-skill) — 9-platform trend research | 30-day cross-platform convergence detection. Inspired our trend digest pipeline |
| **oh-my-claudecode** | [Yeachan-Heo/oh-my-claudecode](https://github.com/Yeachan-Heo/oh-my-claudecode) — Multi-agent orchestration | Provides `/wiki`, `/skill-eval`, `/save`, `/learn` skills used in the companion layer |
| **gstack** | [garrytan/gstack](https://github.com/garrytan/gstack) — AI development toolkit by Garry Tan | QA testing, deployment, code review workflows |

**Articles:**

| Article | Author | Key Idea |
|---------|--------|----------|
| [LLM Knowledge Bases](https://x.com/karpathy/status/2039805659525644595) | Andrej Karpathy | LLM compiles raw data into .md wiki (not RAG). Obsidian as frontend |
| [LLM Wiki 구축 가이드](https://gist.github.com/unclejobs-ai/7af4a9e3446751b8e2c3bc66d23fa0ac) | unclejobs-ai | Practical implementation guide for Karpathy's LLM wiki pattern |
| [복리 지식 시스템](https://retn.kr/blog/compound-learning-ai-system/) | Simpson Gyusup Sim | Episodic memory + 4-stage loop (collect→structure→contextualize→auto-apply) |

> **Note**: The bot itself (features 1-4) works independently. The Claude Code companion layer (LLM Wiki, Autoresearch, Learning System) requires [Claude Code](https://claude.ai/claude-code) with [oh-my-claudecode](https://github.com/Yeachan-Heo/oh-my-claudecode).

### What We Took From Each Tool — and What We Changed

| Tool / Method | What It Does Well | What's Missing | How This Bot Improves It |
|--------------|-------------------|----------------|--------------------------|
| **Readwise** ($8/mo) | Syncs highlights, spaced repetition review | Passive — you still review manually, no cross-note analysis | Weekly report auto-reviews everything, finds patterns you missed, suggests project applications |
| **Notion AI** ($10/mo) | Summarizes individual notes | No cross-note connections, no temporal tracking | Tag co-occurrence analysis links related notes; previous week's report feeds into this week |
| **Feedly / Inoreader** ($6/mo) | Aggregates RSS feeds | Raw firehose — no curation, no personal context | AI curates 5-7 key stories, filtered by your project context |
| **Obsidian + Dataview** (free) | PKM vault with queries | Manual tagging, manual review, no automation | Same vault format — but scanning, summarizing, and connecting are automated |
| **Zapier / Make** ($20+/mo) | Connects SaaS tools | Visual builder, limited AI, per-action pricing | Python scheduler — unlimited runs, full LLM integration, $0 infra cost |
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

### Two Ways to Run — With or Without API Key

| Mode | API Key? | Cost | Quality | Setup |
|------|:--------:|:----:|---------|-------|
| **Ollama (local)** | **No** | **$0** | Good (depends on model) | Install Ollama + pull a model |
| **Gemini (cloud)** | Free key | **$0** | Very good | Get key at aistudio.google.com |
| OpenRouter | Free key | $0-5 | Model-dependent | 100+ models, some free |
| OpenAI / Claude | Paid key | $0.5-15 | Best | For power users |

### Cost Comparison

| Tool | Monthly Cost | What You Get |
|------|-------------|-------------|
| Readwise | $8 | Highlight sync + review |
| Notion AI | $10 | Note summarization |
| Feedly Pro | $6 | RSS aggregation |
| **This bot (Ollama)** | **$0** | **All of the above + compound analysis** |
| **This bot (Gemini)** | **$0** | **Same, cloud-quality AI** |

---

## Quick Start

**Runs locally on your machine. No server or deployment needed.**

### One-line install

```bash
bash <(curl -s https://raw.githubusercontent.com/challengekim/compound-brain/main/install.sh)
```

Or manually:

```bash
git clone https://github.com/challengekim/compound-brain
cd compound-brain
pip install -r requirements.txt
python3 setup_wizard.py        # Interactive — guides you through everything
python3 main.py                # Start the bot
```

The setup wizard walks you through each step:
- Choose your LLM (Ollama = no API key, or Gemini = free key, or 3 others)
- Create a Telegram bot (step-by-step instructions inside the wizard)
- Auto-detects your Telegram chat ID
- Sets up your vault folder

### Optional: Run in background

```bash
# Keep running after closing terminal
nohup python3 main.py &

# Or use Docker (optional, not required)
docker-compose up -d
```

---

## Configuration

All configuration lives in two files:

| File | Contains | Example |
|------|----------|---------|
| `config.yaml` | Everything except secrets | Schedule times, projects, vault path |
| `.env` | Secrets only | API keys, bot tokens |

See [`config.example.yaml`](config.example.yaml) for all options with comments.

---

## Briefing Types

| Type | Schedule | What It Does |
|------|----------|-------------|
| Trend | Daily 10:00 | Top stories from HN, Reddit AI, GeekNews -- curated by AI |
| LinkedIn | Daily 11:30 | AI-drafted post from your vault notes + trends |
| Knowledge | Sat 10:00 | Compound learning: patterns across saved notes + project ideas |
| Meta Review | 1st of month | System self-diagnosis: collection patterns, idea-to-code tracking (AI-estimated) |

All schedules are configurable in `config.yaml`.

---

## Architecture

```
config.yaml + .env
       |
   config.py          <-- Configuration loader
       |
   +---+----------------------------+
   |  trend_fetcher   knowledge_scanner|  <-- Data Collection
   +---+----------------------------+
       |
   summarizer.py      <-- AI Processing (Gemini)
       |                  prompts/ko/*.txt
       |                  prompts/en/*.txt
       |
   briefing_composer.py   <-- Formatting (pure HTML)
       |
   telegram_sender.py    <-- Delivery
```

### Data Flow

1. **Collect**: Fetchers gather data from HN/Reddit and the vault
2. **Summarize**: Gemini processes raw data using prompt templates (language-specific)
3. **Compose**: Pure formatting module renders HTML -- no API calls, no side effects
4. **Deliver**: Telegram for real-time briefings

---

## Obsidian Not Required

This bot works with **any markdown folder**. Obsidian, Logseq, VS Code, or just plain files -- as long as your notes have YAML frontmatter, the scanner can read them.

See [`vault_template/`](vault_template/) for the expected folder structure.

---

## Requirements

- Python 3.9+
- Telegram bot ([free, 2 minutes to create](https://core.telegram.org/bots#botfather))
- **One of** (choose during setup):
  - [Ollama](https://ollama.com) installed locally — **no API key, $0**
  - [Gemini API key](https://aistudio.google.com/apikey) — **free tier, $0**
  - OpenRouter / OpenAI / Claude API key — paid

---

## Running

This runs **locally on your machine**. No server needed.

```bash
python3 main.py                # Runs scheduler (keeps running)
nohup python3 main.py &        # Run in background
```

**Optional** (for always-on without your laptop):

```bash
docker-compose up -d            # Docker
# or deploy to Railway / Render / any VPS
```

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

## Updating

```bash
cd compound-brain
git pull
pip install -r requirements.txt    # only if dependencies changed
```

Your `config.yaml`, `.env`, and vault are untouched — only code updates.

---

## Contributing

Contributions welcome! Areas where help is needed:

- Additional LLM provider support (OpenAI, Claude API)
- New briefing types
- Prompt improvements in `prompts/en/` and `prompts/ko/`
- Additional trend sources
- Alternative delivery channels (Slack, Discord)

---

## License

MIT
