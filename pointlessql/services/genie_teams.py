"""Microsoft Bot Framework Activity adapter for the Genie connector.

Pure shaping between the Bot Framework ``Activity`` JSON that Microsoft
Teams / M365 Copilot POST to the inbound webhook and the plain question
string the Genie engine answers — plus building the reply ``Activity``
the channel renders back into the thread.  No I/O, no auth, no engine
work: just dict / string assembly so the webhook stays thin and this
layer is exhaustively unit-testable.
"""

from __future__ import annotations

import re
from typing import Any

#: ``<at>BotName</at>`` mention spans Teams injects into message text.
_AT_TAG_RE = re.compile(r"<at\b[^>]*>.*?</at>", re.IGNORECASE | re.DOTALL)

#: A leading bare ``@mention`` token (channels that send plain text).
_LEADING_AT_RE = re.compile(r"^\s*@\S+\s*")


def strip_mention(text: str) -> str:
    """Remove ``@Genie`` mentions from an incoming message's text.

    Teams wraps a bot mention as ``<at>Genie</at>`` inside the activity
    text (and also lists it in ``entities``); some channels send a bare
    ``@Genie`` prefix.  Both are stripped so the engine sees only the
    question.

    Args:
        text: The raw activity text.

    Returns:
        The text with mention spans removed and whitespace collapsed.
    """
    without_tags = _AT_TAG_RE.sub(" ", text or "")
    without_leading = _LEADING_AT_RE.sub("", without_tags)
    return re.sub(r"\s+", " ", without_leading).strip()


def parse_activity(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalise a Bot Framework Activity into the fields the webhook uses.

    Args:
        payload: The decoded Activity JSON.

    Returns:
        ``{"type", "text", "id", "conversation", "from", "recipient",
        "channel_id", "service_url", "locale"}`` — missing fields default
        to empty values so callers never ``KeyError``.
    """
    return {
        "type": str(payload.get("type") or ""),
        "text": str(payload.get("text") or ""),
        "id": payload.get("id"),
        "conversation": payload.get("conversation"),
        "from": payload.get("from"),
        "recipient": payload.get("recipient"),
        "channel_id": payload.get("channelId"),
        "service_url": payload.get("serviceUrl"),
        "locale": payload.get("locale"),
    }


def is_message(payload: dict[str, Any]) -> bool:
    """Return whether the Activity is a user message (vs. a system event)."""
    return str(payload.get("type") or "").lower() == "message"


def extract_question(payload: dict[str, Any]) -> str:
    """Pull the mention-stripped question out of a message Activity.

    Args:
        payload: The decoded Activity JSON.

    Returns:
        The user's question with any bot mention removed.
    """
    return strip_mention(str(payload.get("text") or ""))


def build_reply_activity(payload: dict[str, Any], text: str) -> dict[str, Any]:
    """Build a Bot Framework reply Activity carrying *text*.

    The reply swaps the incoming ``from`` / ``recipient`` (the bot, which
    was the recipient, now sends) and threads under the incoming activity
    via ``replyToId`` so the channel renders it in the same conversation.

    Args:
        payload: The incoming Activity JSON.
        text: The answer text to send back.

    Returns:
        A reply Activity dict.
    """
    reply: dict[str, Any] = {
        "type": "message",
        "text": text,
        "inputHint": "acceptingInput",
    }
    if payload.get("id") is not None:
        reply["replyToId"] = payload.get("id")
    if payload.get("conversation") is not None:
        reply["conversation"] = payload.get("conversation")
    # The bot was the recipient of the incoming activity; it is the
    # sender of the reply, so swap the two roles.
    if payload.get("recipient") is not None:
        reply["from"] = payload.get("recipient")
    if payload.get("from") is not None:
        reply["recipient"] = payload.get("from")
    if payload.get("channelId") is not None:
        reply["channelId"] = payload.get("channelId")
    if payload.get("serviceUrl") is not None:
        reply["serviceUrl"] = payload.get("serviceUrl")
    return reply
