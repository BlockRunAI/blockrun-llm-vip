"""Unit tests for Search + Exa pure body builders (no network)."""

import pytest

from blockrun_llm_vip._search_client import build_search_body
from blockrun_llm_vip._exa_client import (
    build_exa_answer_body,
    build_exa_contents_body,
    build_exa_find_similar_body,
    build_exa_search_body,
)


# ---- Search -----------------------------------------------------------------

def test_search_body_minimal():
    assert build_search_body("hi") == {"query": "hi"}


def test_search_body_full():
    body = build_search_body(
        "x402", sources=["x", "news"], max_results=20, from_date="2026-01-01"
    )
    assert body == {
        "query": "x402",
        "sources": ["x", "news"],
        "max_results": 20,
        "from_date": "2026-01-01",
    }


def test_search_body_empty_query_rejected():
    with pytest.raises(ValueError, match="query"):
        build_search_body("  ")


def test_search_body_bad_source_rejected():
    with pytest.raises(ValueError, match="unknown sources"):
        build_search_body("x", sources=["x", "reddit"])


def test_search_body_max_results_bounds():
    with pytest.raises(ValueError, match="between 1 and 50"):
        build_search_body("x", max_results=51)


# ---- Exa --------------------------------------------------------------------

def test_exa_search_body_camelcases_fields():
    body = build_exa_search_body(
        "q", num_results=5, category="github", include_domains=["a.com"]
    )
    assert body == {
        "query": "q",
        "numResults": 5,
        "category": "github",
        "includeDomains": ["a.com"],
    }


def test_exa_find_similar_body():
    assert build_exa_find_similar_body("https://x", num_results=3) == {
        "url": "https://x",
        "numResults": 3,
    }


def test_exa_contents_body_requires_urls():
    with pytest.raises(ValueError, match="urls is required"):
        build_exa_contents_body([])
    assert build_exa_contents_body(["a", "b"]) == {"urls": ["a", "b"]}


def test_exa_contents_body_caps_at_100():
    with pytest.raises(ValueError, match="at most 100"):
        build_exa_contents_body([f"u{i}" for i in range(101)])


def test_exa_answer_body():
    assert build_exa_answer_body("why?") == {"query": "why?"}
    with pytest.raises(ValueError):
        build_exa_answer_body(" ")
