# Compound Brain — Roadmap

## Current State (v1.0 — Released)

**Repo**: https://github.com/challengekim/compound-brain

### What's shipped
- 4 briefing types: trend, knowledge, linkedin, meta-review
- Article saving: Telegram URL, CLI --save, auto-save top 3 trends
- Compound learning: append-only log, last 4 weeks feed into each analysis
- Tag co-occurrence analysis (Zettelkasten-style)
- 5 LLM providers: Gemini (free), OpenRouter, OpenAI, Anthropic, Ollama (local/$0)
- One-line install, interactive setup wizard, Docker support
- Claude Code skills bundle (/save, /learn, /recall)

---

## Phase 2: Network Effect — Shared Brain

### Vision
Users opt-in to share what they save (metadata only, not full content).
The system recommends articles that people with similar interests saved.
Like Spotify's "Discover Weekly" but for knowledge.

### Architecture

```
User A (local)              Backend (new)                User B (local)
┌──────────┐               ┌────────────────┐           ┌──────────┐
│ vault    │──opt-in sync──→│ Shared Index   │←─opt-in──│ vault    │
│ saves    │               │ (metadata only) │           │ saves    │
│ tags     │               │                │           │ tags     │
│ categories│              │ Recommendation │           │ categories│
└──────────┘←──recommend───│ Engine         │──recommend→└──────────┘
                           │                │
                           │ Analytics      │
                           │ Dashboard      │
                           └────────────────┘
```

### What gets shared (opt-in)
- Article URL
- Title
- Tags
- Category
- Save date
- Anonymous user ID (no personal info)

### What NEVER gets shared
- Full article content
- User's vault path or file contents
- Project names or descriptions
- Personal notes or annotations

### Features

#### 2a. Opt-in Metadata Sync
- User runs: `python3 main.py --share enable`
- Weekly: bot sends metadata of saved articles to backend
- Backend stores: `{url, title, tags, category, anonymous_user_id, date}`
- User can `--share disable` anytime, data deleted

#### 2b. Recommendation Engine
- "Users who saved articles about AI agents also saved..."
- Tag co-occurrence across users (global Zettelkasten)
- Trending topics: what's being saved most this week
- Delivered as a new briefing type: "Community Digest"

#### 2c. Web Dashboard
- Browse trending saves across all users
- Filter by category/tag
- See which articles have highest save rates
- Anonymous — no user profiles, just content

#### 2d. Analytics (for project owner)
- Active users (opted-in)
- Total saves per day/week
- Category distribution across all users
- Most saved URLs
- No personal data visible

### Tech Stack (tentative)
- Backend: Supabase or Railway Postgres + FastAPI
- Auth: Anonymous UUID (no login required)
- Sync: POST /api/sync (weekly, from bot scheduler)
- Recommend: GET /api/recommend?tags=ai,agents&limit=5
- Web: Next.js or simple HTML dashboard

### Implementation Order
1. Backend API (sync + recommend endpoints)
2. Bot: `--share` flag + weekly sync job
3. New briefing: "Community Digest" 
4. Web dashboard
5. Analytics dashboard (for project owner)

### Privacy Principles
- Opt-in only. Never default-on.
- Metadata only. Never full content.
- Anonymous. No accounts, no emails, no tracking.
- Deletable. `--share disable` removes all your data.
- Transparent. Open-source backend.

---

## Phase 3: Advanced Features

### 3a. Multi-language prompt optimization
- briefing_composer.py Korean UI → i18n string map
- Full English UI support

### 3b. Plugin system
- Custom briefing types as plugins
- Community-contributed prompts

### 3c. Webhook integrations
- Slack/Discord delivery (alongside Telegram)
- Notion/Obsidian direct sync

### 3d. Mobile app
- Lightweight app for saving URLs (instead of Telegram)
- Push notifications for briefings

---

## Source Repo vs Public Repo

| | Personal (`productivity/`) | Public (`compound-brain`) |
|--|:---:|:---:|
| Email/Calendar | Yes | No |
| 7 briefing types | Yes | 4 types |
| Google OAuth | Yes | No |
| Telegram save | Yes | Yes |
| Compound learning | Yes | Yes |
| Deploys to | Railway (private) | Docker/local (public) |
| Git remote | challengekim/productivity | challengekim/compound-brain |
