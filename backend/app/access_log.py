import logging
import re

ACCESS_LOGGER = "uvicorn.access"

_QUERY_RE = re.compile(r"\?[^\s\"']*")


def _strip_query(value: str) -> str:
    return _QUERY_RE.sub("", value)


class StripQueryStringFilter(logging.Filter):
    """Removes query strings (OAuth code/state and similar) from access log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) == 5 and isinstance(args[2], str):
            # uvicorn shape: (client_addr, method, full_path, http_version, status_code)
            client, method, path, version, status = args
            record.args = (client, method, path.split("?", 1)[0], version, status)
        elif isinstance(args, tuple):
            record.args = tuple(_strip_query(a) if isinstance(a, str) else a for a in args)
        elif isinstance(args, dict):
            record.args = {k: _strip_query(v) if isinstance(v, str) else v for k, v in args.items()}
        if not record.args and isinstance(record.msg, str):
            record.msg = _strip_query(record.msg)
        return True


def install_access_log_filter() -> None:
    logging.getLogger(ACCESS_LOGGER).addFilter(StripQueryStringFilter())
