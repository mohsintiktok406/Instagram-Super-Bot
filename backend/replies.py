from dataclasses import dataclass


@dataclass(frozen=True)
class Reply:
    text: str
    matched_keyword: str | None = None


DEFAULT_RULES: list[tuple[tuple[str, ...], str]] = [
    (("hello", "hi", "salam", "assalam"), "Wa alaikum assalam! Thanks for messaging us."),
    (("price", "cost", "rate"), "Thanks for asking. Please share which item/service you mean."),
]


def keyword_reply(message: str) -> Reply | None:
    normalized = " ".join(message.lower().split())
    for keywords, response in DEFAULT_RULES:
        for keyword in keywords:
            if keyword in normalized:
                return Reply(response, keyword)
    return None
