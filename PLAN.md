# Compound Brain: Bot-to-Agent Upgrade Plan

> Goal: Transform Compound Brain from a schedule-driven bot into a fully autonomous agent
> that observes, decides, acts, and learns — without human intervention.

---

## Current Architecture (Bot)

```
config.yaml
    |
    v
main.py (APScheduler cron)
    |
    +---> process_trend_digest()     ── cron daily 10:00
    +---> process_linkedin_draft()   ── cron daily 11:30
    +---> process_weekly_knowledge() ── cron sat 10:00
    +---> process_meta_review()      ── cron 1st 11:00
    +---> process_telegram_saves()   ── interval 30s
    |
    v
core/
    scanner.py     ── vault scan, URL save, tag analysis
    summarizer.py  ── 5 LLM providers, prompt templates
    trends.py      ── HN / Reddit / GeekNews fetchers
    reviewer.py    ── monthly stats collector
    composer.py    ── HTML formatter (pure, no side effects)
    telegram.py    ── Telegram Bot API sender
```

**What makes this a bot, not an agent:**
- Fixed cron schedules — runs whether or not there's anything useful to report
- No memory of what the user engaged with or ignored
- No ability to skip, defer, or adjust its own behavior
- Each pipeline is independent — no cross-pipeline intelligence
- Config changes require human edits to config.yaml

---

## Target Architecture (Agent)

Applying Anthropic's Managed Agents "Brain/Hand" separation pattern:

```
brain.py (NEW — decision layer, the "brain")
    |
    +---> observe()  ── check vault state, recent saves, engagement history
    +---> decide()   ── what action to take, skip, or adjust
    +---> act()      ── call existing pipeline functions (the "hands")
    +---> learn()    ── record outcomes, update memory
    |
    v
memory.py (NEW — persistent state)
    |
    +---> engagement_log   ── what was read/ignored
    +---> action_log       ── what suggestions were acted on
    +---> preference_model ── learned patterns
    +---> source_scores    ── quality ratings per source
    |
    v
evolution.py (NEW — self-modification)
    |
    +---> evaluate_sources()  ── score by save rate
    +---> adjust_config()     ── modify config.yaml
    +---> evolve_prompts()    ── mutate/A/B test prompts
    +---> track_outcomes()    ── idea → implementation tracking
    |
    v
Existing "hands" (unchanged):
    core/scanner.py, summarizer.py, trends.py, reviewer.py, composer.py, telegram.py
```

**Key principle:** Each phase is independently shippable. Phase A works without B.
Users can choose their autonomy level via config.yaml:

```yaml
agent:
  mode: reactive    # reactive | proactive | self-improving
  autonomy: medium  # low (always ask) | medium (act + report) | high (full auto)
```

---

## Phase A: Reactive Agent

**Duration:** 2-3 days
**Core idea:** The agent REACTS to events instead of blindly following schedules.

### A1. Event-Driven Triggers (file: `brain.py`)

**What changes:**
- New `brain.py` module wraps existing pipeline functions with decision logic
- `main.py` scheduler calls `brain.tick()` instead of individual `process_*()` functions
- `brain.observe()` checks vault state before deciding what to run

**New file: `brain.py`**

```python
class Brain:
    """Decision layer — observes context, decides what action to take."""

    def __init__(self, config, memory):
        self.config = config
        self.memory = memory
        self.hands = Hands(config)  # wraps existing pipeline functions

    def tick(self):
        """Called by scheduler. Observes, decides, acts."""
        context = self.observe()
        actions = self.decide(context)
        for action in actions:
            result = self.act(action)
            self.memory.log_action(action, result)

    def observe(self):
        """Gather current state without side effects."""
        return {
            "recent_saves": self._count_recent_saves(hours=24),
            "saves_by_topic": self._cluster_recent_saves(days=1),
            "days_since_last_knowledge": self._days_since("knowledge"),
            "days_since_last_trend": self._days_since("trend"),
            "unread_briefings": self.memory.get_unread_count(),
            "vault_note_count": self._total_notes(),
        }

    def decide(self, context):
        """Return list of actions to take (or empty list to skip)."""
        actions = []

        # Rule: if 3+ saves on same topic today → trigger focused analysis
        for topic, count in context["saves_by_topic"].items():
            if count >= 3:
                actions.append({"type": "focused_analysis", "topic": topic})

        # Rule: if no new notes this week → skip knowledge report, suggest articles instead
        if context["recent_saves"] == 0 and self._is_knowledge_day():
            actions.append({"type": "suggest_articles"})
            # Skip the normal knowledge report
        elif self._is_knowledge_day():
            actions.append({"type": "knowledge_report"})

        # ... more rules
        return actions

    def act(self, action):
        """Execute an action using existing pipeline functions."""
        if action["type"] == "knowledge_report":
            return self.hands.run_weekly_knowledge()
        elif action["type"] == "focused_analysis":
            return self.hands.run_focused_analysis(action["topic"])
        elif action["type"] == "suggest_articles":
            return self.hands.run_article_suggestions()
        # ...
```

**New file: `hands.py`**

```python
class Hands:
    """Wraps existing pipeline functions as callable tools.
    Follows Anthropic pattern: execute(name, input) → string"""

    def __init__(self, config):
        self.config = config

    def run_trend_digest(self):
        """Delegate to existing process_trend_digest logic."""
        # Extract core logic from main.py's process_trend_digest()
        # Return result dict instead of sending directly

    def run_weekly_knowledge(self):
        """Delegate to existing process_weekly_knowledge logic."""
        # ...

    def run_focused_analysis(self, topic):
        """NEW — mini-analysis on a specific topic cluster."""
        # Filter vault notes by topic, summarize, send

    def run_article_suggestions(self):
        """NEW — suggest articles based on weak categories."""
        # Use meta-review data to find gaps, fetch trends on those topics
```

**What changes in existing files:**

| File | Change |
|------|--------|
| `main.py` | Scheduler calls `brain.tick()` instead of `process_*()` directly. Old direct calls remain as fallback when `agent.mode` is disabled. |
| `config.py` | New `agent` section in config.yaml parsed here. |
| No changes to | `core/scanner.py`, `summarizer.py`, `trends.py`, `reviewer.py`, `composer.py`, `telegram.py` |

### A2. Skip/Adjust Decisions

**Decision rules (implemented in `brain.decide()`):**

| Condition | Bot behavior | Agent behavior |
|-----------|-------------|----------------|
| No new notes this week | Send empty report | Skip report, suggest articles instead |
| User hasn't engaged with LinkedIn drafts for 2 weeks | Keep sending | Stop generating, send "Should I resume?" |
| No trend items collected (API down) | Send error or empty | Skip, retry next tick, notify only if 3 consecutive failures |
| Same article saved twice | Save duplicate | Detect duplicate, reply "Already saved on {date}" |
| Weekend morning | Send at scheduled time | Defer to user's actual reading time (learned from engagement) |

### A3. Context-Aware Telegram Responses

**Current behavior:** When user sends a URL, bot replies with a fixed format:
```
✓ Title
→ category
filename.md
```

**Agent behavior:** Reply includes contextual intelligence:
```
✓ "Building AI Agents with Claude"
→ AI Engineering (you have 7 articles here this week)

🔗 Related in your vault:
- "12 Agentic Harness Patterns" (saved 2d ago)
- "Managed Agents — Brain/Hand Separation" (saved today)

💡 This is your 3rd AI agents article today — want a focused analysis now?
[Reply /yes or /skip]
```

**Implementation:** Extend `process_telegram_saves()` to call `brain.contextualize_save(url, result)` after saving.

### A4. Verification

| Test | How to verify |
|------|---------------|
| Event-driven triggers work | Save 3 articles on same topic via Telegram → receive focused analysis within 30s |
| Skip logic works | Run with empty vault → no knowledge report sent, suggestion sent instead |
| Duplicate detection | Save same URL twice → second attempt replies "Already saved" |
| Fallback works | Set `agent.mode: disabled` in config → bot behavior unchanged |
| Context-aware replies | Save a URL → reply includes related vault articles |

### A5. New Files

```
brain.py      ── decision layer (observe/decide/act/learn)
hands.py      ── wraps existing pipelines as callable tools
```

### A6. What Makes It "Agent"

The specific autonomous decision: **the system decides whether to act or not, and what to act on, based on observed context.** A bot runs `process_weekly_knowledge()` every Saturday at 10:00 regardless. An agent checks "are there new notes? how many? what topics?" and decides the appropriate response.

---

## Phase B: Proactive Agent

**Duration:** 1 week
**Core idea:** The agent INITIATES actions without being asked.
**Prerequisite:** Phase A (brain.py, hands.py exist)

### B1. Agent Memory (file: `memory.py`)

**New file: `memory.py`**

The agent needs persistent state that survives restarts to learn from its own history.

```python
class AgentMemory:
    """Persistent agent state — tracks engagement, preferences, outcomes."""

    def __init__(self, memory_path="~/.compound-brain/memory.json"):
        self.path = os.path.expanduser(memory_path)
        self.data = self._load()

    # --- Engagement tracking ---
    def log_briefing_sent(self, briefing_type, timestamp, content_hash):
        """Record that a briefing was sent."""

    def log_briefing_read(self, briefing_type, timestamp):
        """Record that user interacted with a briefing (clicked link, replied, etc.)"""

    def get_engagement_rate(self, briefing_type, days=30):
        """What % of sent briefings got engagement?"""

    # --- Action tracking ---
    def log_suggestion(self, suggestion_id, content):
        """Record a suggestion we made."""

    def log_suggestion_acted(self, suggestion_id):
        """Record that user acted on a suggestion (saved article, used draft, etc.)"""

    def get_suggestion_hit_rate(self, category=None):
        """What % of suggestions led to action?"""

    # --- Preference learning ---
    def record_reading_time(self, briefing_type, timestamp):
        """Track when user reads briefings to learn optimal send times."""

    def get_preferred_time(self, briefing_type):
        """Return learned optimal send time for a briefing type."""

    # --- Source quality ---
    def log_source_article(self, source, url, title):
        """Record an article from a trend source."""

    def log_source_saved(self, source, url):
        """Record that user saved an article from this source."""

    def get_source_scores(self):
        """Return save_rate per source: {source: {shown: N, saved: M, rate: M/N}}"""

    # --- Persistence ---
    def save(self):
        """Write to JSON."""

    def _load(self):
        """Read from JSON, return empty structure if missing."""
```

**Storage format:** Single JSON file at `~/.compound-brain/memory.json`

```json
{
  "version": 1,
  "briefings": [
    {"type": "trend", "sent_at": "2026-04-08T10:00:00+09:00", "read_at": "2026-04-08T10:15:00+09:00"},
    {"type": "knowledge", "sent_at": "2026-04-05T10:00:00+09:00", "read_at": null}
  ],
  "suggestions": [
    {"id": "sug_001", "content": "Save 3 AI agent articles", "suggested_at": "...", "acted_at": "..."}
  ],
  "source_scores": {
    "Hacker News": {"shown": 150, "saved": 12, "rate": 0.08},
    "r/MachineLearning": {"shown": 80, "saved": 2, "rate": 0.025}
  },
  "reading_times": {
    "trend": ["09:12", "09:05", "08:58", "09:20"],
    "knowledge": ["10:30", "11:00", "10:45"]
  }
}
```

### B2. Auto-Research

**How it works:**
1. Monthly meta-review identifies weak categories (e.g., "Marketing has only 2 notes in 30 days")
2. Agent proactively searches trends for articles in weak categories
3. If quality articles found, auto-saves top 3 to vault
4. Sends Telegram notification: "Filled a gap: saved 3 marketing articles based on your meta-review"

**Implementation in `brain.py`:**

```python
def _proactive_research(self, context):
    """Auto-fill knowledge gaps identified by meta-review."""
    weak_categories = self.memory.get_weak_categories(threshold=3)  # <3 notes in 30d
    if not weak_categories:
        return None

    # Fetch trends, filter by weak categories
    items = self.hands.fetch_trends()
    relevant = [i for i in items if self._matches_category(i, weak_categories)]

    if relevant:
        saved = self.hands.save_articles(relevant[:3])
        return {"type": "auto_research", "saved": saved, "categories": weak_categories}
```

### B3. Smart Scheduling

**Current:** Fixed cron times in config.yaml.
**Agent:** Learns when user actually reads briefings and adjusts.

```python
def _get_optimal_send_time(self, briefing_type):
    """Learn from engagement data when user actually reads this briefing type."""
    times = self.memory.data["reading_times"].get(briefing_type, [])
    if len(times) < 5:
        return None  # not enough data, use config default

    # Median reading time minus 15 minutes
    from statistics import median
    minutes = [int(t.split(":")[0]) * 60 + int(t.split(":")[1]) for t in times[-20:]]
    optimal_minute = median(minutes) - 15
    return f"{optimal_minute // 60:02d}:{optimal_minute % 60:02d}"
```

**How to detect "reading time":**
- When user clicks a link in a Telegram message (Telegram Bot API tracks this via `callback_query`)
- When user replies to a briefing
- When user forwards a briefing

### B4. Proactive Suggestions

**Examples of proactive behavior:**

| Trigger | Agent action |
|---------|-------------|
| 5 unsaved trend items about "AI agents" this week | "You might want to save these 5 AI agent articles — want me to auto-save?" |
| User saved 3 articles but no LinkedIn draft this week | "I have enough material for a LinkedIn draft. Generate now?" |
| Project idea proposed 2 weeks ago, no git commits related | "Your 'RAG pipeline' idea from 2 weeks ago — still interested? Want me to research implementation approaches?" |
| Source quality score drops below threshold | "GeekNews articles haven't been useful lately (2% save rate vs 8% for HN). Want me to deprioritize it?" |

### B5. Engagement Detection via Telegram

**Add Telegram inline keyboard buttons to every briefing:**

```python
def send_briefing_with_tracking(self, text, briefing_type):
    """Send briefing with invisible engagement tracking."""
    # Add reaction buttons
    keyboard = {
        "inline_keyboard": [[
            {"text": "👍", "callback_data": f"useful_{briefing_type}_{timestamp}"},
            {"text": "👎", "callback_data": f"skip_{briefing_type}_{timestamp}"},
        ]]
    }
    # Send with keyboard
    self.telegram.send_message_with_keyboard(text, keyboard)
```

**New in `process_telegram_saves()`:** Handle `callback_query` updates to log engagement.

### B6. Verification

| Test | How to verify |
|------|---------------|
| Memory persists across restarts | Send briefing → restart bot → check memory.json has the record |
| Auto-research triggers | Set up vault with 0 marketing notes → agent fetches and saves marketing articles |
| Smart scheduling adjusts | Simulate 10 reads at 09:00 → agent shifts send time earlier |
| Proactive suggestions appear | Have 5 unsaved trend items on same topic → receive suggestion |
| Engagement tracking works | Click 👍 on a briefing → memory.json records it |

### B7. New Files

```
memory.py   ── persistent agent state (engagement, preferences, scores)
```

### B8. What Makes It "Agent"

The specific autonomous decision: **the agent initiates actions based on learned patterns, not just responding to scheduled triggers.** It fills knowledge gaps without being asked. It adjusts its own schedule. It suggests actions based on observed patterns.

---

## Phase C: Self-Improving Agent

**Duration:** 1-2 weeks
**Core idea:** The agent MODIFIES its own behavior based on measured outcomes.
**Prerequisite:** Phase B (memory.py exists with engagement data)

### C1. Auto-Config Adjustment (file: `evolution.py`)

**New file: `evolution.py`**

```python
class Evolution:
    """Self-modification engine. Adjusts config and prompts based on outcomes."""

    def __init__(self, config, memory):
        self.config = config
        self.memory = memory

    def evaluate_and_adjust(self):
        """Run all self-improvement checks. Called monthly after meta-review."""
        changes = []
        changes.extend(self._adjust_trend_sources())
        changes.extend(self._adjust_subreddits())
        changes.extend(self._adjust_schedule())
        if changes:
            self._apply_config_changes(changes)
            self._log_evolution(changes)
        return changes

    def _adjust_trend_sources(self):
        """Deprioritize low-quality trend sources, boost high-quality ones."""
        scores = self.memory.get_source_scores()
        changes = []
        for source, data in scores.items():
            if data["rate"] < 0.02 and data["shown"] > 50:
                # Source produces noise — reduce limit
                changes.append({
                    "type": "reduce_source",
                    "source": source,
                    "reason": f"Save rate {data['rate']:.1%} ({data['saved']}/{data['shown']})",
                    "action": f"Reduce {source} limit from {self._get_limit(source)} to {max(3, self._get_limit(source) // 2)}",
                })
        return changes

    def _adjust_subreddits(self):
        """Add subreddits for weak categories, remove low-value ones."""
        weak = self.memory.get_weak_categories(threshold=3)
        changes = []
        # Map categories to suggested subreddits
        category_subreddits = {
            "marketing": ["marketing", "growthacking", "SEO"],
            "business": ["startups", "Entrepreneur", "smallbusiness"],
            "engineering": ["devops", "programming", "webdev"],
        }
        for cat in weak:
            if cat in category_subreddits:
                for sub in category_subreddits[cat]:
                    if sub not in self.config.trend_subreddits:
                        changes.append({
                            "type": "add_subreddit",
                            "subreddit": sub,
                            "reason": f"Category '{cat}' is weak — adding r/{sub}",
                        })
        return changes
```

### C2. Prompt Evolution

**Karpathy "autoresearch" pattern applied to prompts:**

1. Each prompt template gets a version number
2. Agent generates a mutated variant (slightly different instructions, different emphasis)
3. Both versions run for 1 week (A/B test)
4. Version with higher engagement rate wins
5. Winner becomes the new baseline; generate another mutation

**Implementation:**

```python
def evolve_prompts(self):
    """A/B test prompt variants based on engagement."""
    for prompt_name in ["trend_digest", "weekly_knowledge", "linkedin_draft"]:
        current_version = self._get_current_prompt(prompt_name)
        variant = self._generate_mutation(current_version)

        # Store both versions
        self.prompt_variants[prompt_name] = {
            "A": current_version,
            "B": variant,
            "started": datetime.now().isoformat(),
            "engagement_A": 0,
            "engagement_B": 0,
        }

def _generate_mutation(self, prompt_text):
    """Use LLM to create a slightly different version of the prompt."""
    mutation_prompt = f"""
    Here is a prompt template used to generate a briefing:

    {prompt_text}

    Create a slightly different version that might produce more engaging output.
    Change ONE thing: tone, structure, emphasis, or level of detail.
    Keep the same input variables ({{items_text}}, etc).
    """
    return self.summarizer._generate(mutation_prompt)
```

**Storage:** `~/.compound-brain/prompts/variants/` directory with versioned files.

### C3. Source Quality Scoring

**Automatic quality measurement:**

```
Source Score = (articles_saved_by_user / articles_shown) * 100

Hacker News:     shown=150, saved=12 → score=8.0%
r/MachineLearning: shown=80, saved=2  → score=2.5%
GeekNews:        shown=100, saved=8  → score=8.0%
r/ChatGPT:       shown=60, saved=0  → score=0.0%  ← candidate for removal
```

**Actions based on scores:**
- Score < 2% after 50+ items shown: reduce fetch limit by 50%
- Score < 1% after 100+ items shown: remove source entirely
- Score > 10%: increase fetch limit by 50%
- New source suggested by user: start with default limit, measure for 2 weeks

### C4. Idea-to-Implementation Tracking

**How it works:**
1. Weekly knowledge report suggests project ideas (already exists via `save_project_ideas()`)
2. Agent tracks each idea with an ID
3. Monthly, agent scans git commits across tracked repos (already exists via `_git_commits_since()`)
4. If commit messages match an idea's keywords → mark as "implemented"
5. Adjust future suggestions based on what types of ideas actually get implemented

```python
def track_outcomes(self):
    """Check which suggested ideas appeared in git commits."""
    ideas = self.memory.get_pending_ideas()
    for project_name, repo_path in self.config.project_repos.items():
        commits = _git_commits_since(repo_path, days=30)
        commit_text = " ".join(commits).lower()
        for idea in ideas:
            keywords = idea["keywords"]
            if any(kw.lower() in commit_text for kw in keywords):
                self.memory.mark_idea_implemented(idea["id"], project_name)
                # Learn: this type of idea gets implemented
```

### C5. Safety Rails

**Critical:** Self-modification needs guardrails.

| Guard | Implementation |
|-------|---------------|
| Config backup | Before any config change, copy config.yaml to config.yaml.bak.{timestamp} |
| Change log | All config changes written to `~/.compound-brain/evolution-log.json` |
| Rollback | If engagement drops >50% after a change, auto-rollback within 1 week |
| Human override | `agent.autonomy: low` forces all changes to go through Telegram confirmation first |
| Prompt safety | Mutated prompts validated: must contain all required variables, must be <2x original length |
| Rate limit | Max 3 config changes per month; max 1 prompt mutation per week |

### C6. Verification

| Test | How to verify |
|------|---------------|
| Source scoring works | Run for 2 weeks → memory.json has accurate source scores |
| Config auto-adjustment | Create low-scoring source → agent reduces its limit in config.yaml |
| Prompt evolution | Check prompts/variants/ for A/B test files after 1 week |
| Idea tracking | Add a git commit matching an idea keyword → idea marked "implemented" |
| Safety rails | Trigger a config change → config.yaml.bak.{timestamp} exists |
| Rollback works | Simulate engagement drop → config reverts to backup |

### C7. New Files

```
evolution.py                          ── self-modification engine
~/.compound-brain/evolution-log.json  ── audit trail of all self-modifications
~/.compound-brain/prompts/variants/   ── A/B test prompt versions
```

### C8. What Makes It "Agent"

The specific autonomous decision: **the agent modifies its own configuration and prompts based on measured outcomes.** It doesn't just report that "GeekNews has low engagement" — it acts on that data by adjusting its own parameters. This is closed-loop learning.

---

## Phase D: Multi-Agent System

**Duration:** 2-3 weeks
**Core idea:** Specialized sub-agents that coordinate, following Anthropic's Managed Agents pattern.
**Prerequisite:** Phases A-C (brain, memory, evolution all working)

### D1. Architecture: Brain/Hand Separation at Scale

```
agents/
    orchestrator.py    ── the "brain" — decides what to do next
    researcher.py      ── finds and evaluates articles
    curator.py         ── manages vault quality
    analyst.py         ── compound analysis, pattern detection
    writer.py          ── content generation (LinkedIn, summaries)
session/
    event_log.py       ── append-only log of all decisions and outcomes
    state.py           ── current agent state machine
```

**Applying Anthropic's pattern:**

| Anthropic Concept | Compound Brain Implementation |
|-------------------|-------------------------------|
| Session = append-only log | `session/event_log.py` — every decision, action, and outcome logged |
| Harness = stateless brain | `agents/orchestrator.py` — reads event log, decides next action |
| Sandbox = execution env | Each agent function = a "sandbox" with defined inputs/outputs |
| `execute(name, input) → string` | Each agent exposes `run(input: dict) → AgentResult` |
| Container crash recovery | If agent fails mid-task, orchestrator reads event log and resumes |

### D2. Agent Definitions

#### Researcher Agent (`agents/researcher.py`)

**Inputs:** topic keywords, category gaps, user interest signals
**Outputs:** ranked list of articles with relevance scores

```python
class ResearcherAgent:
    """Finds and evaluates articles. Learns what the user cares about."""

    def run(self, task):
        if task["type"] == "fill_gap":
            return self._fill_category_gap(task["category"])
        elif task["type"] == "deep_dive":
            return self._deep_dive_topic(task["topic"])
        elif task["type"] == "trending_relevant":
            return self._find_relevant_trends(task["interests"])

    def _fill_category_gap(self, category):
        """Search multiple sources for articles in a weak category."""
        # 1. Fetch from HN, Reddit, GeekNews (existing trends.py)
        # 2. Score relevance to category
        # 3. Filter by user's historical preferences
        # 4. Return top 5 with confidence scores

    def _deep_dive_topic(self, topic):
        """When user shows strong interest in a topic, go deeper."""
        # 1. Search across all sources for this specific topic
        # 2. Include academic papers (arXiv RSS), blog posts, GitHub repos
        # 3. Cross-reference with user's vault to avoid duplicates
        # 4. Return structured research brief
```

#### Curator Agent (`agents/curator.py`)

**Inputs:** vault state, engagement data, quality metrics
**Outputs:** curation actions (archive, connect, tag, highlight)

```python
class CuratorAgent:
    """Maintains vault quality. Connects related notes. Archives stale content."""

    def run(self, task):
        if task["type"] == "connect_notes":
            return self._find_new_connections()
        elif task["type"] == "quality_audit":
            return self._audit_vault_quality()
        elif task["type"] == "archive_stale":
            return self._suggest_archives()

    def _find_new_connections(self):
        """Go beyond tag co-occurrence — use LLM to find semantic connections."""
        # 1. Scan recent notes
        # 2. For each note, ask LLM: "Which other notes in the vault relate to this?"
        # 3. Suggest new links (Obsidian [[wikilinks]])
        # 4. Optionally auto-add backlinks

    def _audit_vault_quality(self):
        """Check for notes missing tags, descriptions, or with broken links."""
        # 1. Scan all notes for missing frontmatter fields
        # 2. Check for orphan notes (no tags, no links)
        # 3. Find near-duplicate titles
        # 4. Return quality report
```

#### Analyst Agent (`agents/analyst.py`)

**Inputs:** vault notes, trend data, project context, compound log
**Outputs:** insights, patterns, cross-domain connections

```python
class AnalystAgent:
    """Runs compound analysis. Finds patterns across time and topics."""

    def run(self, task):
        if task["type"] == "compound_analysis":
            return self._compound_analysis(task["period_weeks"])
        elif task["type"] == "trend_intersection":
            return self._find_trend_intersections()
        elif task["type"] == "blind_spot_detection":
            return self._detect_blind_spots()

    def _compound_analysis(self, weeks):
        """Build on previous analyses — true compound learning."""
        # 1. Load last N weeks from compound-log.md
        # 2. Load current week's notes
        # 3. Ask LLM: "Given the evolving themes from previous weeks,
        #    what NEW patterns emerge when we add this week's data?"
        # 4. Specifically look for: convergent themes, contradictions,
        #    ideas that matured over time

    def _detect_blind_spots(self):
        """What topics is the user NOT reading about that they should be?"""
        # 1. Analyze user's project context
        # 2. Compare with industry trends
        # 3. Identify gaps between what user needs and what they're reading
```

#### Writer Agent (`agents/writer.py`)

**Inputs:** analysis results, user voice profile, content type
**Outputs:** draft content (LinkedIn posts, project proposals, action plans)

```python
class WriterAgent:
    """Generates content. Learns user's voice over time."""

    def run(self, task):
        if task["type"] == "linkedin_draft":
            return self._generate_linkedin(task["notes"], task["trends"])
        elif task["type"] == "action_plan":
            return self._generate_action_plan(task["idea"])
        elif task["type"] == "project_proposal":
            return self._generate_proposal(task["idea"], task["context"])

    def _generate_action_plan(self, idea):
        """Turn a vague idea into a concrete, actionable plan."""
        # 1. Research the idea (delegate to Researcher if needed)
        # 2. Break into phases
        # 3. Estimate effort
        # 4. Identify risks
        # 5. Generate implementation skeleton
```

#### Orchestrator (`agents/orchestrator.py`)

**The brain of the multi-agent system:**

```python
class Orchestrator:
    """Coordinates sub-agents. Decides priorities. Manages resources."""

    def __init__(self, config, memory, event_log):
        self.agents = {
            "researcher": ResearcherAgent(config, memory),
            "curator": CuratorAgent(config, memory),
            "analyst": AnalystAgent(config, memory),
            "writer": WriterAgent(config, memory),
        }
        self.event_log = event_log
        self.memory = memory

    def run_cycle(self):
        """One decision cycle. Called by scheduler or event trigger."""
        # 1. Read current state from event log
        context = self._build_context()

        # 2. Decide which agents to invoke
        plan = self._plan(context)

        # 3. Execute plan
        for step in plan:
            agent = self.agents[step["agent"]]
            self.event_log.append({"type": "agent_start", "agent": step["agent"], "task": step["task"]})

            result = agent.run(step["task"])

            self.event_log.append({"type": "agent_complete", "agent": step["agent"], "result": result})

            # Feed result into next step if needed
            if step.get("feed_into"):
                plan[step["feed_into"]]["task"]["input"] = result

    def _plan(self, context):
        """Use LLM to decide what agents to run and in what order."""
        plan_prompt = f"""
        You are the orchestrator of a knowledge management system.
        Current context:
        - Vault: {context['vault_stats']}
        - Recent engagement: {context['engagement']}
        - Pending tasks: {context['pending']}
        - Last actions: {context['recent_actions']}

        Available agents: researcher, curator, analyst, writer

        What should we do next? Return a JSON array of tasks.
        Each task: {{"agent": "name", "task": {{"type": "...", ...}}}}
        Order matters — earlier tasks can feed into later ones.
        If nothing useful to do, return empty array.
        """
        # Parse LLM response into execution plan
```

### D3. Event Log (Session as Context Object)

Following Anthropic's "session = append-only log" pattern:

```python
class EventLog:
    """Append-only log of all agent decisions and outcomes.
    Survives crashes. Enables replay and debugging."""

    def __init__(self, log_path="~/.compound-brain/session/events.jsonl"):
        self.path = os.path.expanduser(log_path)

    def append(self, event):
        """Append event to log. Never modify existing entries."""
        event["timestamp"] = datetime.now().isoformat()
        event["id"] = str(uuid4())
        with open(self.path, "a") as f:
            f.write(json.dumps(event) + "\n")

    def get_events(self, since=None, event_type=None, limit=100):
        """Read events with optional filtering. Supports the 'rewind' pattern."""

    def get_last_n(self, n=10):
        """Get most recent N events for context."""
```

### D4. State Machine

```
IDLE
  |
  v (timer tick or event trigger)
OBSERVING ── gather context from vault, memory, event log
  |
  v
PLANNING ── orchestrator decides what agents to run
  |
  v
EXECUTING ── agents run in sequence (or parallel if independent)
  |
  v
LEARNING ── record outcomes, update memory, check for self-improvement
  |
  v (back to)
IDLE
```

### D5. LLM Cost Considerations

| Agent | Calls per cycle | Estimated tokens | Cost (Gemini Flash) |
|-------|----------------|-----------------|---------------------|
| Orchestrator (planning) | 1 | ~1K in / ~500 out | ~$0.001 |
| Researcher | 0-2 | ~2K in / ~1K out | ~$0.003 |
| Curator | 0-1 | ~3K in / ~500 out | ~$0.002 |
| Analyst | 0-1 | ~5K in / ~2K out | ~$0.005 |
| Writer | 0-1 | ~3K in / ~2K out | ~$0.004 |
| **Total per cycle** | **1-6** | | **~$0.015** |
| **Daily (4 cycles)** | | | **~$0.06** |
| **Monthly** | | | **~$1.80** |

Still well within Gemini Flash free tier (1,500 req/day).

### D6. Verification

| Test | How to verify |
|------|---------------|
| Orchestrator plans correctly | Log shows sensible agent selection based on context |
| Researcher fills gaps | Weak category gets 3 new articles after one cycle |
| Curator finds connections | New Obsidian wikilinks suggested for related notes |
| Analyst produces compound insight | Week 4 analysis references themes from weeks 1-3 |
| Writer learns voice | LinkedIn drafts match user's historical tone (manual check) |
| Event log enables recovery | Kill process mid-cycle → restart → resumes from last event |
| Multi-agent coordination | Researcher output feeds into Writer (e.g., research brief → LinkedIn draft) |

### D7. New Files

```
agents/
    __init__.py
    orchestrator.py  ── coordinates sub-agents
    researcher.py    ── finds articles
    curator.py       ── manages vault quality
    analyst.py       ── compound analysis
    writer.py        ── content generation
session/
    __init__.py
    event_log.py     ── append-only decision log
    state.py         ── state machine (IDLE → OBSERVING → PLANNING → EXECUTING → LEARNING)
```

### D8. What Makes It "Agent"

The specific autonomous decision: **a meta-agent (orchestrator) uses an LLM to decide which specialized agents to invoke, in what order, with what inputs — and the plan adapts based on the full history of past decisions and outcomes.** This is not a pipeline. It's a system that reasons about what to do next.

---

## Implementation Summary

### Files Created per Phase

| Phase | New Files | Modified Files |
|-------|-----------|----------------|
| A: Reactive | `brain.py`, `hands.py` | `main.py`, `config.py` |
| B: Proactive | `memory.py` | `brain.py`, `core/telegram.py` |
| C: Self-Improving | `evolution.py` | `brain.py`, `config.py` |
| D: Multi-Agent | `agents/*.py` (5), `session/*.py` (2) | `brain.py` → becomes `agents/orchestrator.py` |

### Total Effort Estimate

| Phase | Effort | Running Total |
|-------|--------|--------------|
| A: Reactive Agent | 2-3 days | 2-3 days |
| B: Proactive Agent | 1 week | ~10 days |
| C: Self-Improving | 1-2 weeks | ~3 weeks |
| D: Multi-Agent | 2-3 weeks | ~6 weeks |

### Config.yaml Evolution

```yaml
# Phase A adds:
agent:
  mode: reactive        # disabled | reactive | proactive | self-improving | multi-agent
  autonomy: medium      # low (ask first) | medium (act + report) | high (full auto)

# Phase B adds:
agent:
  memory_path: ~/.compound-brain/memory.json
  engagement_tracking: true
  smart_scheduling: true

# Phase C adds:
agent:
  self_improve: true
  max_config_changes_per_month: 3
  max_prompt_mutations_per_week: 1
  rollback_threshold: 0.5   # engagement drop % that triggers rollback

# Phase D adds:
agent:
  agents:
    researcher: true
    curator: true
    analyst: true
    writer: true
  orchestrator:
    max_cycles_per_day: 8
    max_llm_calls_per_cycle: 6
```

### Migration Path for Existing Users

Each phase adds new config keys with sensible defaults. Existing `config.yaml` files work unchanged because:

1. `agent.mode` defaults to `disabled` — bot behavior preserved
2. All new features are opt-in via config
3. No existing files are renamed or deleted
4. Existing `process_*()` functions in `main.py` remain as direct-call fallbacks

To upgrade: `agent.mode: reactive` in config.yaml. That's it.

### Autonomy Level Matrix

| Feature | `low` | `medium` | `high` |
|---------|-------|----------|--------|
| Skip empty reports | Ask first via Telegram | Skip + notify | Skip silently |
| Auto-save trend articles | Never | Save + notify | Save silently |
| Fill category gaps | Suggest only | Save + notify | Save silently |
| Adjust schedule | Suggest new times | Apply + notify | Apply silently |
| Modify config | Never auto-modify | Suggest changes | Apply + log |
| Evolve prompts | Never | A/B test with notification | A/B test silently |
| Add/remove sources | Never | Suggest only | Apply + log |

---

## Open Questions

1. **Where does the agent run?** Railway (current) has no filesystem persistence for `memory.json`. Options: (a) Railway volume, (b) store memory in vault as markdown, (c) use Supabase/external DB, (d) S3-compatible object storage.

2. **Telegram engagement tracking accuracy.** Telegram's Bot API has limited callback tracking. Consider: (a) inline keyboard buttons (Phase B approach), (b) track `/feedback` command, (c) measure time between send and next user message as proxy.

3. **Multi-LLM for multi-agent.** Should different agents use different LLM providers? Researcher might benefit from a model with better web knowledge; Writer from a model with better creative output. Cost vs quality tradeoff.

4. **Vault as state store.** Instead of `~/.compound-brain/memory.json`, store agent state directly in the Obsidian vault (e.g., `20_Projects/Compound Brain/agent-state.md`). Pro: visible to user, backed up with vault. Con: mixing data with knowledge.

5. **Rate limiting for self-improvement.** Phase C's auto-config changes need careful bounds. The proposed 3 changes/month and 1 prompt mutation/week may need tuning based on real usage.

---

## Phase 3: Full Stack Dogfooding (Post-Core)

**Duration:** 1 week
**Core idea:** Make the agent usable daily — fix data pipeline, deploy, add conversation + dashboard.
**Prerequisite:** Phases A-D complete

**Strategy:** 1-month dogfooding period. Use the agent daily, measure what works, then decide on startup expansion.

### 3.1. Orchestrator Data Pipeline Fix (CRITICAL)

**Problem:** `_build_context()` had broken attribute access — `getattr(self.memory, "preferred_categories", [])` always returned `[]` because `AgentMemory` stores categories in `self.preferences["preferred_categories"]`.

**Fixed:**
- `_build_context()` now calls `self.memory.get_preferred_categories()` → returns `(category, score)` tuples
- `_build_planning_prompt()` includes engagement stats and formatted category scores
- `_rule_based_plan()` now includes curator (`quality_audit`, `connect_notes`) and alternates default plans between researcher+analyst and curator+analyst

### 3.2. Railway Deployment

**Fixed:**
- `railway.json`: builder changed from NIXPACKS to DOCKERFILE
- `Dockerfile`: build order fixed (COPY src/ before pip install)
- Volume: `/data/compound-brain` for persistent memory/event-log

**Env vars needed:**
- `COMPOUND_BRAIN_PATH=/data/compound-brain`
- `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- `DASHBOARD_PASSWORD` (optional)
- `DASHBOARD_PORT` (default 8080)

### 3.3. Telegram Natural Language Conversation

**New file: `vault_search.py`**

Keyword-based vault search + LLM synthesis:
- `search_vault(config, query)` — scores notes by keyword hit count
- `synthesize_answer(summarizer, query, notes)` — LLM generates answer from matched notes

**TelegramHandler changes:**
- Non-URL, non-command text → `_handle_question()` (vault search + LLM answer)
- `/status` — agent state + memory stats
- `/report` — trigger analysis now
- `/help` — command list

### 3.4. Web Dashboard MVP

**New file: `dashboard.py`**

Flask app running in daemon thread alongside APScheduler:
- `/health` — Railway health check
- `/api/status` — agent mode + state
- `/api/events` — event log (last 50)
- `/api/memory` — engagement stats, categories, source rankings
- Self-contained dark-theme SPA with 30s auto-refresh
- Optional basic auth via `DASHBOARD_PASSWORD`

### 3.5. Verification

| Test | How to verify |
|------|---------------|
| Orchestrator uses real data | preferred_categories returns actual tuples, engagement stats in prompt |
| Rule-based plan includes curator | curator quality_audit appears in fallback plans |
| Railway deploys | `git push` → Dockerfile builds, health check passes |
| Telegram Q&A works | Send text → get vault-based answer with source notes |
| Telegram commands work | `/status`, `/report`, `/help` return expected responses |
| Dashboard shows data | Browser at :8080 shows agent status, events, memory |

### 3.6. New/Modified Files

```
NEW:
  vault_search.py     — keyword vault search + LLM synthesis
  dashboard.py        — Flask web dashboard MVP
  tests/test_vault_search.py   — 22 tests
  tests/test_dashboard.py      — 20 tests

MODIFIED:
  agents/orchestrator.py  — data pipeline fix, curator fallback
  telegram_handler.py     — natural language + command routing
  main.py                 — dashboard integration
  pyproject.toml          — flask dependency
  railway.json            — DOCKERFILE builder
  Dockerfile              — build order fix, EXPOSE 8080
```

### 3.7. What's Next (Phase 4 — after dogfooding)

Deferred until demand signals from 1-month usage:
- Plugin system (agents/ auto-discovery)
- Multi-user support
- README.md for public release
- Evolution ↔ orchestrator integration
- Embedding-based vault search (if keyword matching proves insufficient)
