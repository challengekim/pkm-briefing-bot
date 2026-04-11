"""Vault search — keyword matching against vault notes for Q&A."""
import logging
from .knowledge_scanner import scan_recent_notes

logger = logging.getLogger(__name__)


def search_vault(config, query: str, max_results: int = 10, days: int = 30) -> list[dict]:
    """Search vault notes by keyword matching against title, description, and category.

    Returns list of matching note dicts sorted by relevance (number of keyword hits).
    """
    notes = scan_recent_notes(config, days=days)
    keywords = [w.lower() for w in query.split() if len(w) >= 2]
    if not keywords:
        return notes[:max_results]

    scored = []
    for note in notes:
        searchable = f"{note.get('title', '')} {note.get('description', '')} {note.get('category', '')}".lower()
        hits = sum(1 for kw in keywords if kw in searchable)
        if hits > 0:
            scored.append((hits, note))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [note for _, note in scored[:max_results]]


def synthesize_answer(summarizer, query: str, notes: list[dict]) -> str:
    """Use LLM to synthesize an answer from matching vault notes."""
    if not notes:
        return "관련 노트를 찾지 못했습니다."

    note_context = "\n".join(
        f"- {n.get('title', 'Untitled')}: {n.get('description', 'No description')}"
        for n in notes[:10]
    )

    prompt = (
        f"사용자 질문: {query}\n\n"
        f"관련 vault 노트:\n{note_context}\n\n"
        f"위 노트들을 바탕으로 사용자의 질문에 답변해주세요. "
        f"답변에 관련 노트 제목을 언급해주세요. 한국어로 답변하세요."
    )
    return summarizer._generate(prompt)
