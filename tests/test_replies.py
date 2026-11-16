from backend.replies import keyword_reply


def test_greeting_rule():
    reply = keyword_reply("Assalam o alaikum")
    assert reply is not None
    assert "Wa alaikum" in reply.text


def test_no_keyword_returns_none():
    assert keyword_reply("random unrelated message") is None

from backend.automation import match_trigger, Trigger


def test_keyword_trigger_is_case_insensitive():
    assert match_trigger("I need the LINK please", "dm") is not None


def test_comment_trigger():
    assert match_trigger("price please", "comment") is not None


def test_trigger_exact_match():
    trigger = Trigger(("hello",), "Hi", match="exact")
    assert match_trigger("hello", "dm", (trigger,)) == "Hi"
    assert match_trigger("hello there", "dm", (trigger,)) is None
