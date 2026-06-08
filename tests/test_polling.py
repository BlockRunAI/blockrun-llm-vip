"""Unit tests for the shared submit→poll plumbing (no network)."""

import pytest

from blockrun_llm_vip._polling import poll_until, resolve_poll_url


class _Boom(RuntimeError):
    pass


def test_resolve_poll_url_preserves_signed_query():
    out = resolve_poll_url(
        "https://blockrun.ai/api", "/api/v1/images/generations/abc?sig=zzz", error_cls=_Boom
    )
    assert out == "https://blockrun.ai/api/v1/images/generations/abc?sig=zzz"


def test_resolve_poll_url_absolute_passthrough():
    abs_url = "https://x/y?z=1"
    assert resolve_poll_url("https://blockrun.ai/api", abs_url, error_cls=_Boom) == abs_url


def test_resolve_poll_url_missing_uses_error_cls():
    with pytest.raises(_Boom):
        resolve_poll_url("https://blockrun.ai/api", "", error_cls=_Boom)


def test_poll_until_returns_first_terminal_result():
    seq = iter([None, None, {"status": "done"}])
    out = poll_until(
        lambda: next(seq),
        lambda r: r,  # interpret: pass the (already-terminal-or-None) value through
        timeout=10,
        interval=0,
        on_timeout=lambda: _Boom("timeout"),
    )
    assert out == {"status": "done"}


def test_poll_until_raises_on_timeout():
    with pytest.raises(_Boom, match="timeout"):
        poll_until(
            lambda: None,            # never terminal
            lambda r: r,
            timeout=-1,              # already past deadline → one check then raise
            interval=0,
            on_timeout=lambda: _Boom("timeout"),
        )
