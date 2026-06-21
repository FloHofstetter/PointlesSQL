"""Genie App Builder — natural-language authoring of hosted apps.

Turns a plain-language description into a runnable single-file app and
hands it to the existing app-hosting clone (the same managed-worker +
authenticating-reverse-proxy stack that serves operator-written apps).
This module is the wiring between two halves PointlesSQL already ships:
the Genie LLM plumbing (BYO workspace credential → Lens provider
adapter) and the hosted-apps lifecycle.

The scaffold assembly is pure and deterministic, so the feature works
end to end without any LLM configured: when no workspace credential is
available the builder emits a runnable placeholder app that renders the
prompt, which the author then edits in place.  When a credential *is*
configured the model drafts the body and the builder wraps it.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

    from pointlessql.config import Settings

#: App kinds the builder can author from a prompt.  ``command`` is a raw
#: argv template, not generated code, so it is intentionally excluded.
APP_BUILDER_KINDS: tuple[str, ...] = ("fastapi", "streamlit")

#: Header comment stamped on every generated source so an author can
#: tell a drafted scaffold apart from hand-written app code.
_PROVENANCE_HEADER = "# Drafted by the Genie App Builder from a natural-language prompt."

_PYTHON_FENCE_RE = re.compile(r"```(?:python|py)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_python(text: str) -> str:
    """Pull the Python out of an LLM reply (fenced block or raw).

    Args:
        text: The assistant text.

    Returns:
        The code inside the first ````python`` fence, or the whole
        reply stripped when there is no fence.
    """
    match = _PYTHON_FENCE_RE.search(text)
    candidate = match.group(1) if match else text
    return candidate.strip()


def default_title(prompt: str) -> str:
    """Derive a short app title from the first words of *prompt*.

    Args:
        prompt: The natural-language description.

    Returns:
        Up to the first six words, capped at 80 characters; a generic
        fallback when the prompt is empty.
    """
    words = prompt.split()
    if not words:
        return "Genie App"
    return " ".join(words[:6])[:80]


def build_system_prompt(kind: str) -> str:
    """Build the system prompt that pins the model to one app file.

    Args:
        kind: One of :data:`APP_BUILDER_KINDS`.

    Returns:
        A system prompt instructing the model to answer with a single
        runnable Python file for *kind*.

    Raises:
        ValueError: When *kind* is not a buildable app kind.
    """
    if kind == "fastapi":
        target = "a single-file FastAPI app that defines a module-level `app = FastAPI()`"
    elif kind == "streamlit":
        target = "a single-file Streamlit script written against the `streamlit` API"
    else:
        raise ValueError(f"Unknown app kind for the Genie App Builder: {kind!r}")
    return (
        f"You write {target}.  The file is saved as `app.py` and run as-is — "
        "it must be self-contained and importable.  Answer ONLY with the Python "
        "in a single ```python block: no prose and no explanation before or "
        "after the block."
    )


def _looks_runnable(body: str, kind: str) -> bool:
    """Return whether *body* already defines the entry point for *kind*.

    For FastAPI the hosting worker imports ``app`` from the module, so a
    draft only counts as runnable when it actually binds a module-level
    ``app`` — a passing mention of the word "app" in a comment or string
    is not enough, or the worker would fail to import a non-existent
    symbol.
    """
    if kind == "fastapi":
        return "FastAPI" in body and bool(re.search(r"(?m)^app\b\s*[:=]", body))
    return "streamlit" in body or "st." in body


def _fastapi_scaffold(*, title: str, prompt: str) -> str:
    """Render a runnable placeholder FastAPI app that shows the prompt."""
    lines = [
        _PROVENANCE_HEADER,
        "from fastapi import FastAPI",
        "from fastapi.responses import HTMLResponse",
        "",
        "app = FastAPI()",
        "",
        f"TITLE = {title!r}",
        f"PROMPT = {prompt!r}",
        "",
        "",
        '@app.get("/", response_class=HTMLResponse)',
        "def home() -> str:",
        '    """Render the requested app description as a placeholder page."""',
        "    return (",
        '        f"<h1>{TITLE}</h1>"',
        '        f"<p>{PROMPT}</p>"',
        '        "<p>Generated scaffold - edit the source to build out the app.</p>"',
        "    )",
        "",
    ]
    return "\n".join(lines)


def _streamlit_scaffold(*, title: str, prompt: str) -> str:
    """Render a runnable placeholder Streamlit app that shows the prompt."""
    lines = [
        _PROVENANCE_HEADER,
        "import streamlit as st",
        "",
        f"TITLE = {title!r}",
        f"PROMPT = {prompt!r}",
        "",
        "st.title(TITLE)",
        "st.write(PROMPT)",
        'st.info("Generated scaffold - edit the source to build out the app.")',
        "",
    ]
    return "\n".join(lines)


def scaffold_app(*, prompt: str, kind: str, body: str | None = None) -> str:
    """Assemble a runnable single-file app for *kind* from a prompt.

    When *body* (an LLM draft) already defines the entry point for
    *kind* it is used verbatim under a provenance header; otherwise a
    deterministic placeholder that renders the prompt is returned, so
    the result is always a runnable ``app.py``.

    Args:
        prompt: The natural-language description.
        kind: One of :data:`APP_BUILDER_KINDS`.
        body: Optional model-drafted Python to wrap.

    Returns:
        The complete ``app.py`` source.

    Raises:
        ValueError: When *kind* is not a buildable app kind.
    """
    if kind not in APP_BUILDER_KINDS:
        raise ValueError(f"Unknown app kind for the Genie App Builder: {kind!r}")
    cleaned = (body or "").strip()
    if cleaned and _looks_runnable(cleaned, kind):
        return f"{_PROVENANCE_HEADER}\n{cleaned}\n"
    title = default_title(prompt)
    if kind == "fastapi":
        return _fastapi_scaffold(title=title, prompt=prompt)
    return _streamlit_scaffold(title=title, prompt=prompt)


def _resolve_provider(
    factory: sessionmaker[Session],
    *,
    workspace_id: int,
    settings: Settings,
) -> tuple[str, str, str] | None:
    """Pick the workspace's first enabled BYO LLM credential, or ``None``.

    Shares the Lens credential rows the Genie SQL path consumes; the
    first enabled provider that decrypts wins.  Returns ``None`` (rather
    than raising) when no credential is available so the builder can
    fall back to a deterministic scaffold.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Active workspace (credential scope).
        settings: Resolved settings (model-default fallbacks).

    Returns:
        ``(provider_name, api_key, model)`` or ``None``.
    """
    from pointlessql.services.lens._provider_creds import (
        decrypt_provider_key,
        list_provider_creds,
    )

    for row in list_provider_creds(factory, workspace_id=workspace_id):
        if not row.enabled:
            continue
        api_key = decrypt_provider_key(factory, workspace_id=workspace_id, provider=row.provider)
        if api_key is None:
            continue
        default_model = settings.lens.model_default(row.provider)
        return row.provider, api_key, row.default_model or default_model
    return None


async def _draft_body(
    prompt: str,
    kind: str,
    *,
    provider_name: str,
    api_key: str,
    model: str,
) -> str:
    """Ask the configured LLM for the app body and extract its Python."""
    from pointlessql.services.lens.llm_provider import get_provider

    provider = get_provider(provider_name, api_key=api_key)
    content = f"Build this app:\n\n{prompt}"
    if provider_name == "anthropic":
        messages = [{"role": "user", "content": [{"type": "text", "text": content}]}]
    else:
        messages = [{"role": "user", "content": content}]
    completion = await provider.chat_with_tools(
        system=build_system_prompt(kind),
        messages=messages,
        model=model,
    )
    return extract_python(completion.text or "")


async def generate_app_source(
    prompt: str,
    kind: str,
    *,
    factory: sessionmaker[Session],
    workspace_id: int,
    settings: Settings,
) -> tuple[str, bool]:
    """Build a runnable ``app.py`` from *prompt* for *kind*.

    Drafts the body with the workspace's BYO LLM when one is configured
    and falls back to a deterministic scaffold otherwise, so the call
    always yields a runnable file.

    Args:
        prompt: The natural-language description.
        kind: One of :data:`APP_BUILDER_KINDS`.
        factory: SQLAlchemy session factory.
        workspace_id: Active workspace (credential scope).
        settings: Resolved settings (model defaults).

    Returns:
        ``(source_code, used_llm)`` — the assembled source and whether
        an LLM drafted the body.

    Raises:
        ValueError: When *kind* is not buildable or *prompt* is blank.
    """
    if kind not in APP_BUILDER_KINDS:
        raise ValueError(f"Unknown app kind for the Genie App Builder: {kind!r}")
    cleaned_prompt = prompt.strip()
    if not cleaned_prompt:
        raise ValueError("A prompt is required to build an app.")
    resolved = _resolve_provider(factory, workspace_id=workspace_id, settings=settings)
    if resolved is None:
        return scaffold_app(prompt=cleaned_prompt, kind=kind), False
    provider_name, api_key, model = resolved
    body = await _draft_body(
        cleaned_prompt, kind, provider_name=provider_name, api_key=api_key, model=model
    )
    return scaffold_app(prompt=cleaned_prompt, kind=kind, body=body), True
