"""Unit tests for the Jupyter subprocess manager and notebook routes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from pointlessql.services.jupyter import managed_jupyter
from pointlessql.settings import Settings

# ------------------------------------------------------------------
# Settings defaults
# ------------------------------------------------------------------


class TestSettingsJupyterDefaults:
    def test_jupyter_enabled_default(self) -> None:
        s = Settings()
        assert s.jupyter_enabled is True

    def test_jupyter_port_default(self) -> None:
        s = Settings()
        assert s.jupyter_port == 8888


# ------------------------------------------------------------------
# managed_jupyter — disabled
# ------------------------------------------------------------------


class TestManagedJupyterDisabled:
    async def test_yields_none_when_disabled(self) -> None:
        settings = Settings(jupyter_enabled=False)
        with patch("pointlessql.services.jupyter.asyncio") as mock_aio:
            async with managed_jupyter(settings) as proc:
                assert proc is None
            mock_aio.create_subprocess_exec.assert_not_called()


# ------------------------------------------------------------------
# managed_jupyter — enabled (mocked subprocess)
# ------------------------------------------------------------------


def _make_mock_process(*, returncode: int | None = None) -> MagicMock:
    """Create a mock asyncio.subprocess.Process."""
    proc = MagicMock()
    proc.pid = 12345
    proc.returncode = returncode
    proc.send_signal = MagicMock()
    proc.kill = MagicMock()
    proc.wait = AsyncMock(return_value=0)
    return proc


class TestManagedJupyterStartsProcess:
    async def test_starts_and_terminates(self) -> None:
        mock_proc = _make_mock_process()
        settings = Settings(jupyter_enabled=True, jupyter_port=9999)

        with (
            patch(
                "pointlessql.services.jupyter.asyncio.create_subprocess_exec",
                new_callable=AsyncMock,
                return_value=mock_proc,
            ) as mock_create,
            patch(
                "pointlessql.services.jupyter._wait_until_ready",
                new_callable=AsyncMock,
            ),
        ):
            async with managed_jupyter(settings) as proc:
                assert proc is mock_proc

            # Verify correct command was constructed
            args = mock_create.call_args
            cmd_args = args[0]
            assert "-m" in cmd_args
            assert "jupyterlab" in cmd_args
            assert "--no-browser" in cmd_args
            assert "--port=9999" in cmd_args
            assert "--ServerApp.token=''" in cmd_args
            assert "--ServerApp.password=''" in cmd_args

    async def test_sends_sigterm_on_exit(self) -> None:
        import signal

        mock_proc = _make_mock_process()
        settings = Settings(jupyter_enabled=True)

        with (
            patch(
                "pointlessql.services.jupyter.asyncio.create_subprocess_exec",
                new_callable=AsyncMock,
                return_value=mock_proc,
            ),
            patch(
                "pointlessql.services.jupyter._wait_until_ready",
                new_callable=AsyncMock,
            ),
        ):
            async with managed_jupyter(settings):
                pass

        mock_proc.send_signal.assert_called_once_with(signal.SIGTERM)

    async def test_kills_on_timeout(self) -> None:
        mock_proc = _make_mock_process()
        settings = Settings(jupyter_enabled=True)

        with (
            patch(
                "pointlessql.services.jupyter.asyncio.create_subprocess_exec",
                new_callable=AsyncMock,
                return_value=mock_proc,
            ),
            patch(
                "pointlessql.services.jupyter._wait_until_ready",
                new_callable=AsyncMock,
            ),
            patch("pointlessql.services.jupyter.asyncio.wait_for", new_callable=AsyncMock) as wf,
        ):
            wf.side_effect = TimeoutError
            async with managed_jupyter(settings):
                pass

        mock_proc.kill.assert_called_once()

    async def test_skips_shutdown_if_already_exited(self) -> None:
        mock_proc = _make_mock_process(returncode=0)
        settings = Settings(jupyter_enabled=True)

        with (
            patch(
                "pointlessql.services.jupyter.asyncio.create_subprocess_exec",
                new_callable=AsyncMock,
                return_value=mock_proc,
            ),
            patch(
                "pointlessql.services.jupyter._wait_until_ready",
                new_callable=AsyncMock,
            ),
        ):
            async with managed_jupyter(settings):
                pass

        mock_proc.send_signal.assert_not_called()


# ------------------------------------------------------------------
# Notebook route tests
# ------------------------------------------------------------------


class TestNotebookRoute:
    @pytest.fixture()
    def _app(self) -> None:
        """Prepare app.state so the route handlers work without the real lifespan."""
        from pointlessql.api.main import app

        app.state.settings = Settings(jupyter_enabled=True, jupyter_port=9999)
        app.state.uc_client = MagicMock()
        app.state.jupyter_process = None

    @pytest.mark.usefixtures("_app")
    async def test_notebook_enabled_returns_loader(self) -> None:
        from pointlessql.api.main import app

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/notebook")

        assert resp.status_code == 200
        assert "jupyterLoader" in resp.text
        assert "pql-notebook-iframe" in resp.text
        assert "localhost:9999" in resp.text
        assert "Starting JupyterLab" in resp.text

    @pytest.mark.usefixtures("_app")
    async def test_notebook_disabled_shows_message(self) -> None:
        from pointlessql.api.main import app

        app.state.settings = Settings(jupyter_enabled=False)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/notebook")

        assert resp.status_code == 200
        assert "Notebook Disabled" in resp.text
        assert "pql-notebook-iframe" not in resp.text


# ------------------------------------------------------------------
# Jupyter status API
# ------------------------------------------------------------------


class TestJupyterStatusAPI:
    @pytest.fixture()
    def _app(self) -> None:
        from pointlessql.api.main import app

        app.state.settings = Settings(jupyter_enabled=True, jupyter_port=8888)
        app.state.uc_client = MagicMock()
        app.state.jupyter_process = None

    @pytest.mark.usefixtures("_app")
    async def test_status_when_not_running(self) -> None:
        from pointlessql.api.main import app

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/jupyter/status")

        data = resp.json()
        assert data["enabled"] is True
        assert data["running"] is False
        assert data["port"] == 8888

    @pytest.mark.usefixtures("_app")
    async def test_status_when_running(self) -> None:
        from pointlessql.api.main import app

        mock_proc = _make_mock_process()
        app.state.jupyter_process = mock_proc

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/jupyter/status")

        data = resp.json()
        assert data["running"] is True
