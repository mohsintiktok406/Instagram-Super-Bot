"""Minimal official Meta Graph API client. Never accepts Instagram passwords."""
import httpx
from .config import settings


class MetaAPIError(RuntimeError):
    pass


async def send_text_message(recipient_id: str, text: str) -> dict:
    if not settings.meta_access_token or not settings.instagram_account_id:
        raise MetaAPIError("Configure META_ACCESS_TOKEN and INSTAGRAM_ACCOUNT_ID first")
    url = (
        f"https://graph.facebook.com/{settings.graph_api_version}/"
        f"{settings.instagram_account_id}/messages"
    )
    payload = {"recipient": {"id": recipient_id}, "message": {"text": text}}
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            url,
            params={"access_token": settings.meta_access_token},
            json=payload,
        )
    if response.is_error:
        raise MetaAPIError(f"Meta API returned {response.status_code}: {response.text[:500]}")
    return response.json()


async def reply_to_comment(comment_id: str, text: str) -> dict:
    """Reply to a comment using the configured Meta token."""
    if not settings.meta_access_token:
        raise MetaAPIError("Configure META_ACCESS_TOKEN first")
    url = f"https://graph.facebook.com/{settings.graph_api_version}/{comment_id}/replies"
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(url, params={"access_token": settings.meta_access_token}, json={"message": text})
    if response.is_error:
        raise MetaAPIError(f"Meta API returned {response.status_code}: {response.text[:500]}")
    return response.json()


async def list_own_media(limit: int = 25) -> dict:
    """List media belonging to the connected professional account; does not scrape other users."""
    if not settings.meta_access_token or not settings.instagram_account_id:
        raise MetaAPIError("Configure META_ACCESS_TOKEN and INSTAGRAM_ACCOUNT_ID first")
    url = f"https://graph.facebook.com/{settings.graph_api_version}/{settings.instagram_account_id}/media"
    fields = "id,caption,media_type,media_url,permalink,timestamp,thumbnail_url"
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(url, params={"access_token": settings.meta_access_token, "fields": fields, "limit": max(1, min(limit, 100))})
    if response.is_error:
        raise MetaAPIError(f"Meta API returned {response.status_code}: {response.text[:500]}")
    return response.json()
