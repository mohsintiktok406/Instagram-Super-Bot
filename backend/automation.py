"""Reusable trigger matcher inspired by InstaAuto's keyword/comment/story workflows."""
from dataclasses import dataclass
from typing import Literal

@dataclass(frozen=True)
class Trigger:
    keywords: tuple[str, ...]
    reply: str
    event_types: tuple[str, ...] = ("dm", "comment", "story_reply")
    match: Literal["contains", "exact"] = "contains"
    enabled: bool = True

# Starter defaults. Move these to a database-backed dashboard in the next phase.
DEFAULT_TRIGGERS = (
    Trigger(("price", " قیمت", "قیمت"), "Please share which product you are asking about."),
    Trigger(("link", "website"), "Thanks! Please tell me which link you need."),
    Trigger(("help", "support"), "I'm here to help. Please describe what you need."),
)

def match_trigger(text: str, event_type: str = "dm", triggers=DEFAULT_TRIGGERS) -> str | None:
    normalized = " ".join((text or "").casefold().split())
    if not normalized:
        return None
    for trigger in triggers:
        if not trigger.enabled or event_type not in trigger.event_types:
            continue
        for keyword in trigger.keywords:
            key = " ".join(keyword.casefold().split())
            matched = normalized == key if trigger.match == "exact" else key in normalized
            if matched:
                return trigger.reply
    return None
