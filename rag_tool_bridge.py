import os
import sys
from typing import List, Dict, Optional
from dotenv import load_dotenv

load_dotenv()

# ───────────────── RAG PROJECT PATH SETUP ───────────────── #

_RAG_PROJECT_PATH = os.getenv("RAG_PROJECT_PATH", "").strip()

if _RAG_PROJECT_PATH and _RAG_PROJECT_PATH not in sys.path:
    sys.path.insert(0, _RAG_PROJECT_PATH)

# ───────────────── RAG IMPORT (graceful fallback) ───────────────── #

RAG_AVAILABLE = False
_hybrid_search = None
_semantic_search = None
_search_by_book = None
_search_by_section = None

try:
    if not _RAG_PROJECT_PATH:
        raise ImportError("RAG_PROJECT_PATH is not set in .env")

    from search_engine.search import hybrid_search as _hybrid_search
    from search_engine.search import semantic_search as _semantic_search
    from search_engine.search import search_by_book as _search_by_book
    from search_engine.search import search_by_section as _search_by_section

    RAG_AVAILABLE = True
except ImportError as _rag_import_error:
    _RAG_UNAVAILABLE_REASON = str(_rag_import_error)
except Exception as _rag_import_error:
    _RAG_UNAVAILABLE_REASON = str(_rag_import_error)

if not RAG_AVAILABLE:
    _RAG_UNAVAILABLE_REASON = locals().get(
        "_RAG_UNAVAILABLE_REASON",
        "Unknown import error"
    )


# ───────────────── RESULT FORMATTER ───────────────── #

def format_rag_results(results: list) -> str:
    """Format a list of RAG result dicts into a readable numbered string.

    Each dict is expected to have: text, book_title, section_title, score, parent_context.
    Uses parent_context["text"] when available, falls back to text.
    """
    if not results:
        return "No relevant information found in the knowledge base."

    parts = []
    for i, item in enumerate(results, 1):
        book = item.get("book_title", "Unknown Book")
        section = item.get("section_title", "Unknown Section")
        score = item.get("score", 0.0)

        parent_context = item.get("parent_context")
        if isinstance(parent_context, dict) and parent_context.get("text"):
            content = parent_context["text"]
        else:
            content = item.get("text", "")

        parts.append(
            f"[Source {i}: {book} \u2192 {section} | Score: {score:.3f}]\n"
            f"{content}\n"
            f"---"
        )

    return "\n".join(parts)


# ───────────────── RAG TOOL FUNCTIONS ───────────────── #

def rag_search(
    query: str,
    top_k: int = 5,
    search_type: str = "hybrid",
    book_filter: str = "",
) -> str:
    """Hybrid search across the RAG knowledge base."""
    if not RAG_AVAILABLE:
        return f"RAG system unavailable: {_RAG_UNAVAILABLE_REASON}"

    try:
        filters = {"book": book_filter} if book_filter else None

        results = _hybrid_search(
            query=query,
            top_k=top_k,
            filters=filters,
            weight_profile="auto",
            search_type=search_type,
            candidate_pool=200,
            enable_context_boost=True,
            use_hyde=False,
            use_rerank=False,
        )

        return format_rag_results(results)

    except Exception as e:
        return f"RAG search error: {str(e)}"


def rag_semantic_search(query: str, top_k: int = 5) -> str:
    """Semantic (embedding-based) search across the RAG knowledge base."""
    if not RAG_AVAILABLE:
        return f"RAG system unavailable: {_RAG_UNAVAILABLE_REASON}"

    try:
        results = _semantic_search(query=query, top_k=top_k)
        return format_rag_results(results)

    except Exception as e:
        return f"RAG semantic search error: {str(e)}"


def rag_search_by_book(book_name: str, topic: str = "", limit: int = 10) -> str:
    """Search within a specific book/document in the RAG knowledge base."""
    if not RAG_AVAILABLE:
        return f"RAG system unavailable: {_RAG_UNAVAILABLE_REASON}"

    try:
        results = _search_by_book(
            book_query=book_name,
            limit=limit,
            topic=topic if topic else None,
        )
        return format_rag_results(results)

    except Exception as e:
        return f"RAG search_by_book error: {str(e)}"


def rag_search_by_section(
    section_query: str,
    book_name: str = "",
    limit: int = 10,
) -> str:
    """Search for a specific chapter or section in the RAG knowledge base."""
    if not RAG_AVAILABLE:
        return f"RAG system unavailable: {_RAG_UNAVAILABLE_REASON}"

    try:
        results = _search_by_section(
            section_query=section_query,
            limit=limit,
            book_query=book_name if book_name else None,
        )
        return format_rag_results(results)

    except Exception as e:
        return f"RAG search_by_section error: {str(e)}"


def rag_health_check() -> str:
    """Check whether the RAG knowledge base system is reachable and functional."""
    if not RAG_AVAILABLE:
        return f"RAG OFFLINE — {_RAG_UNAVAILABLE_REASON}"

    try:
        results = _hybrid_search(
            query="test",
            top_k=1,
            candidate_pool=10,
        )

        if results is None:
            return "RAG ERROR — hybrid_search returned None"

        return f"RAG ONLINE — system responded successfully ({len(results)} result(s) returned)"

    except Exception as e:
        return f"RAG ERROR — {str(e)}"

