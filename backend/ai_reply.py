"""Optional OpenAI-compatible AI fallback. Disabled unless configured explicitly."""
import httpx
from .config import settings

async def generate_reply(user_text: str, history: list[dict] | None = None) -> str | None:
    if settings.ai_provider != "openai_compatible" or not settings.ai_api_key or not settings.ai_model:
        return None
    base = settings.ai_base_url.rstrip("/")
    if not base:
        return None
    messages = [{"role": "system", "content": (
        "You are a concise, helpful Instagram page assistant. Reply in the user's language. "
        "Do not claim to have performed actions you cannot perform. Keep replies brief."
    )}]
    for item in (history or [])[-12:]:
        role = "user" if item.get("direction") == "inbound" else "assistant"
        messages.append({"role": role, "content": item.get("message_text", "")})
    if not history or not history or history[-1].get("message_text") != user_text:
        messages.append({"role": "user", "content": user_text})
    async with httpx.AsyncClient(timeout=25) as client:
        response = await client.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {settings.ai_api_key}"},
            json={"model": settings.ai_model, "messages": messages, "temperature": 0.4, "max_tokens": 180},
        )
    if response.is_error:
        return None
    data = response.json()
    return (data.get("choices", [{}])[0].get("message", {}).get("content") or "").strip() or None
