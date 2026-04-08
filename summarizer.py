import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"


class Summarizer:
    def __init__(self, config=None, api_key=None, lang="ko"):
        """Initialize with either a Config object or legacy api_key string."""
        self.lang = lang

        if config:
            self._provider = config.llm_provider
            self._model = config.llm_model
            self._api_key = config.llm_api_key
            self._base_url = config.llm_base_url
        else:
            # Legacy: api_key string = Gemini
            self._provider = "gemini"
            self._model = "gemini-2.5-flash"
            self._api_key = api_key or ""
            self._base_url = None

        self._client = None  # lazy init

    def _get_client(self):
        if self._client is not None:
            return self._client

        if self._provider == "gemini":
            from google import genai
            self._client = genai.Client(api_key=self._api_key)
        elif self._provider == "anthropic":
            from anthropic import Anthropic
            self._client = Anthropic(api_key=self._api_key)
        else:
            # OpenAI-compatible: openai, openrouter, ollama
            from openai import OpenAI
            kwargs = {"api_key": self._api_key or "ollama"}
            if self._base_url:
                kwargs["base_url"] = self._base_url
            self._client = OpenAI(**kwargs)

        return self._client

    def _load_prompt(self, name):
        """Load a prompt template file. Falls back to Korean if target language not found."""
        prompt_file = _PROMPTS_DIR / self.lang / f"{name}.txt"
        if not prompt_file.exists():
            prompt_file = _PROMPTS_DIR / "ko" / f"{name}.txt"
        if not prompt_file.exists():
            raise FileNotFoundError(
                f"Prompt template '{name}' not found. "
                f"Expected at: {_PROMPTS_DIR / self.lang / f'{name}.txt'} "
                f"or {_PROMPTS_DIR / 'ko' / f'{name}.txt'}. "
                "Re-clone the repo or check your prompts/ directory."
            )
        return prompt_file.read_text(encoding="utf-8")

    def _generate(self, prompt):
        """Call the configured LLM provider."""
        try:
            client = self._get_client()

            if self._provider == "gemini":
                response = client.models.generate_content(
                    model=self._model, contents=prompt
                )
                return response.text
            elif self._provider == "anthropic":
                response = client.messages.create(
                    model=self._model,
                    max_tokens=4096,
                    messages=[{"role": "user", "content": prompt}],
                )
                return response.content[0].text
            else:
                # OpenAI-compatible API
                response = client.chat.completions.create(
                    model=self._model,
                    messages=[{"role": "user", "content": prompt}],
                )
                return response.choices[0].message.content
        except Exception as e:
            logger.error(f"LLM call failed ({self._provider}/{self._model}): {e}")
            return f"(Generation failed: {e})"

    def summarize_newsletter(self, subject, body, sender):
        prompt = self._load_prompt("newsletter").format(
            sender=sender, subject=subject, body=body[:8000]
        )
        return self._generate(prompt)

    def summarize_business_email(self, subject, body, sender):
        prompt = self._load_prompt("business_email").format(
            sender=sender, subject=subject, body=body[:8000]
        )
        return self._generate(prompt)

    def summarize_newsletter_thread(self, subject, emails):
        thread_body = "\n\n---\n\n".join(
            f"[{e['from']}] ({e['date']})\n{e['body'][:4000]}"
            for e in emails
        )
        senders = ", ".join(dict.fromkeys(e["from"] for e in emails))
        prompt = self._load_prompt("newsletter_thread").format(
            email_count=len(emails),
            senders=senders,
            subject=subject,
            thread_body=thread_body[:12000],
        )
        return self._generate(prompt)

    def summarize_business_thread(self, subject, emails):
        thread_body = "\n\n---\n\n".join(
            f"[{e['from']}] ({e['date']})\n{e['body'][:4000]}"
            for e in emails
        )
        senders = ", ".join(dict.fromkeys(e["from"] for e in emails))
        prompt = self._load_prompt("business_thread").format(
            email_count=len(emails),
            senders=senders,
            subject=subject,
            thread_body=thread_body[:12000],
        )
        return self._generate(prompt)

    def summarize_meeting_prep(self, event):
        no_info = "No info" if self.lang == "en" else "정보 없음"
        attendees_str = ", ".join(event.get("attendees", [])[:10]) or no_info
        description = (event.get("description", "") or "")[:2000]
        prompt = self._load_prompt("meeting_prep").format(
            summary=event.get("summary", ""),
            attendees=attendees_str,
            description=description,
        )
        result = self._generate(prompt)
        return None if result.startswith("(Generation failed:") else result

    def summarize_trend_digest(self, items, project_context=""):
        """Summarize collected trend items into a concise daily digest."""
        items_text = "\n".join(
            f"- [{it['source']}] {it['title']} | {it['url']}"
            for it in items[:40]
        )
        context_section = ""
        if project_context:
            if self.lang == "en":
                context_section = (
                    f"\n\n[My Project Context]\n{project_context}\n\n"
                    "Considering the project context above, add this section at the end:\n"
                    "---\n"
                    "💡 Insights applicable to my projects:\n"
                    "- (Project name) How a specific trend can be applied, 1-3 items\n"
                )
            else:
                context_section = (
                    f"\n\n[내 프로젝트 컨텍스트]\n{project_context}\n\n"
                    "위 프로젝트 컨텍스트를 참고하여, 요약 마지막에 다음 섹션을 추가해주세요:\n"
                    "---\n"
                    "💡 내 프로젝트에 적용 가능한 인사이트:\n"
                    "- (프로젝트명) 어떤 트렌드가 어떻게 적용 가능한지 1-3개\n"
                )
        prompt = self._load_prompt("trend_digest").format(
            context_section=context_section,
            item_count=len(items),
            items_text=items_text,
        )
        return self._generate(prompt)

    def summarize_weekly_knowledge(self, notes, project_context=""):
        """Summarize this week's saved knowledge notes into a compound learning report."""
        notes_text = "\n".join(
            f"- [{n['category']}] {n['title']}: {n['description']}"
            for n in notes[:30]
        )
        prompt = self._load_prompt("weekly_knowledge").format(
            note_count=len(notes),
            notes_text=notes_text,
            project_context=project_context,
        )
        return self._generate(prompt)

    def generate_linkedin_draft(self, notes, trend_summary, project_context=""):
        """Generate a daily LinkedIn post draft from vault notes + trend digest."""
        notes_text = "\n".join(
            f"- [{n['category']}] {n['title']}: {n['description']}"
            + (f" (적용: {n['applicable_when']})" if n.get("applicable_when") else "")
            for n in notes[:50]
        )
        trend_section = ""
        if trend_summary:
            label = "Today's Trend Digest" if self.lang == "en" else "오늘의 트렌드 다이제스트"
            trend_section = f"\n\n[{label}]\n{trend_summary[:3000]}\n"
        prompt = self._load_prompt("linkedin_draft").format(
            notes_text=notes_text,
            trend_section=trend_section,
            project_context=project_context,
        )
        return self._generate(prompt)

    def summarize_meta_review(self, stats, project_context=""):
        """Generate a monthly meta review analyzing the knowledge system itself."""
        cat_str = "\n".join(
            f"  - {cat}: {cnt}건" for cat, cnt in stats["category_counts"].items()
        )
        author_str = "\n".join(
            f"  - {a}: {c}건" for a, c in stats["author_counts"].items()
        )
        tag_str = ", ".join(
            f"{t}({c})" for t, c in stats["tag_counts"].items()
        )
        commits_str = "\n".join(
            f"  - {name}: {d['count']}건 커밋"
            for name, d in stats["project_commits"].items()
        )
        prompt = self._load_prompt("meta_review").format(
            period_days=stats["period_days"],
            total_notes=stats["total_notes"],
            cat_str=cat_str,
            author_str=author_str,
            tag_str=tag_str,
            commits_str=commits_str,
            ideas_content=stats["ideas_content"][-1500:],
            project_context=project_context,
        )
        return self._generate(prompt)

    def translate_titles(self, items):
        """Translate English titles to Korean for display. Returns dict of original->translated."""
        english_items = [it for it in items if not self._is_korean(it["title"])]
        if not english_items:
            return {}

        titles_text = "\n".join(
            f"{i}. {it['title']}" for i, it in enumerate(english_items)
        )
        prompt = self._load_prompt("translate_titles").format(
            titles_text=titles_text
        )
        result = self._generate(prompt)
        if result.startswith("(Generation failed:"):
            return {}
        translations = {}
        for line in result.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            parts = line.split(". ", 1)
            if len(parts) == 2 and parts[0].strip().isdigit():
                idx = int(parts[0].strip())
                if 0 <= idx < len(english_items):
                    translations[english_items[idx]["title"]] = parts[1].strip()
        return translations

    @staticmethod
    def _is_korean(text):
        korean_count = sum(1 for c in text if '\uac00' <= c <= '\ud7a3')
        return korean_count >= len(text) * 0.3

    def summarize_weekly(self, email_stats, meeting_count, next_week_events):
        next_week_str = "\n".join(
            f"- {e.get('summary', '?')} ({e.get('start', '')})"
            for e in next_week_events[:10]
        ) or "없음"
        prompt = self._load_prompt("weekly_summary").format(
            meeting_count=meeting_count,
            personal_count=email_stats.get("personal", 0),
            work_count=email_stats.get("work", 0),
            next_week_str=next_week_str,
        )
        return self._generate(prompt)
