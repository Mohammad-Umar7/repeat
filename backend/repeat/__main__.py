"""`python -m repeat` starts the local service."""

import uvicorn

from .config import get_settings


def main() -> None:
    s = get_settings()
    uvicorn.run(
        "repeat.api.app:app",
        host="127.0.0.1",
        port=s.repeat_port,
        log_level=s.repeat_log_level.lower(),
        access_log=s.repeat_log_level == "DEBUG",
        reload=False,
    )


if __name__ == "__main__":
    main()
