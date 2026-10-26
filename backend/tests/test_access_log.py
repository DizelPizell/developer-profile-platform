import io
import logging
import socket
import threading
import time

import httpx
import pytest
import uvicorn

from app.access_log import ACCESS_LOGGER, StripQueryStringFilter

_UVICORN_MSG = '%s - "%s %s HTTP/%s" %d'


def _record(msg, args) -> logging.LogRecord:
    return logging.LogRecord(ACCESS_LOGGER, logging.INFO, __file__, 1, msg, args, None)


def test_uvicorn_shaped_record_loses_query_string():
    record = _record(
        _UVICORN_MSG,
        (
            "127.0.0.1:5000",
            "GET",
            "/api/v1/auth/github/callback?code=SECRET&state=SECRET",
            "1.1",
            302,
        ),
    )
    assert StripQueryStringFilter().filter(record) is True
    message = record.getMessage()
    assert "SECRET" not in message
    assert message == '127.0.0.1:5000 - "GET /api/v1/auth/github/callback HTTP/1.1" 302'


@pytest.mark.parametrize(
    ("msg", "args"),
    [
        ("%s %s", ("GET", "/cb?code=SECRET&state=SECRET")),
        ("%s", ('"GET /cb?code=SECRET HTTP/1.1" 302',)),
        ("%(path)s", ({"path": "/cb?code=SECRET"},)),
        ('"GET /cb?code=SECRET&state=SECRET HTTP/1.1" 302', None),
    ],
)
def test_unexpected_record_shape_still_strips_query_string(msg, args):
    record = _record(msg, args)
    assert StripQueryStringFilter().filter(record) is True
    message = record.getMessage()
    assert "SECRET" not in message
    assert "/cb" in message


def test_uvicorn_access_log_has_no_query_string():
    """
    TestClient bypasses uvicorn's HTTP protocol, so uvicorn never writes an
    access record for it. Run a real uvicorn server on a random local port
    instead and capture what its access logger emits.
    """
    from app.main import app

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    access_logger = logging.getLogger(ACCESS_LOGGER)
    old_level, old_disabled = access_logger.level, access_logger.disabled
    access_logger.addHandler(handler)
    access_logger.setLevel(logging.INFO)
    # alembic's fileConfig (run by the db_engine fixture) disables existing loggers.
    access_logger.disabled = False

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_config=None, lifespan="off"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started:
            assert time.monotonic() < deadline, "uvicorn did not start"
            time.sleep(0.05)
        resp = httpx.get(
            f"http://127.0.0.1:{port}/api/v1/auth/github/callback?code=SECRET&state=SECRET"
        )
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
        access_logger.removeHandler(handler)
        access_logger.setLevel(old_level)
        access_logger.disabled = old_disabled

    assert resp.status_code == 302
    output = stream.getvalue()
    assert "/api/v1/auth/github/callback" in output
    assert "SECRET" not in output
