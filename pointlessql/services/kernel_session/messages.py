"""Per-message dataclasses + per-subscriber queue handles.

The pump tasks on :class:`KernelSession` translate raw Jupyter wire
messages into :class:`KernelMessage` dataclasses and fan them out to
every :class:`_Subscription` registered on the session. Kept as a
standalone module so the message shape can evolve without touching
the larger session lifecycle code.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

_SUBSCRIBER_QUEUE_MAXSIZE = 1024


@dataclass
class KernelMessage:
    """A single iopub / shell message on its way from kernel to client.

    Attributes:
        content_hash: Source cell's content-hash identity
            (``sha256(source)[:16]``) when the kernel's parent
            message originated from a tracked ``execute_request``.
            Kernel-initiated messages (status heartbeats, display
            from untracked code) carry ``None``. Replaces an earlier
            UUID-based ``cell_id`` field.
        channel: ``"iopub"`` or ``"shell"``.
        msg_type: Raw Jupyter msg type (``stream``,
            ``execute_result``, ``display_data``, ``error``,
            ``status``, ``execute_input``, ``execute_reply``, …).
        content: Raw message content dict — structure varies by
            msg_type. See the Jupyter messaging spec.
        metadata: Raw metadata dict. Rare; usually empty.
        parent_msg_id: The ``execute_request`` msg_id this is a reply
            to, when applicable.
    """

    content_hash: str | None
    channel: str
    msg_type: str
    content: dict[str, Any]
    metadata: dict[str, Any]
    parent_msg_id: str | None


@dataclass(eq=False)
class Subscription:
    """A pair of per-client queues fed by the session pump tasks.

    ``eq=False`` keeps the dataclass hashable by object identity so
    instances can live in the ``set[Subscription]`` on
    :class:`KernelSession` without colliding on value-equality.
    """

    iopub: asyncio.Queue[KernelMessage] = field(
        default_factory=lambda: asyncio.Queue(maxsize=_SUBSCRIBER_QUEUE_MAXSIZE)
    )
    shell: asyncio.Queue[KernelMessage] = field(
        default_factory=lambda: asyncio.Queue(maxsize=_SUBSCRIBER_QUEUE_MAXSIZE)
    )
