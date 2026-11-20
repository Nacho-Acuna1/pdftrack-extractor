"""Dynamic port-binding entrypoint (Twelve-Factor VII).

Reads ``PORT`` from the environment and starts Uvicorn.
This module is the ``CMD`` target in the Dockerfile.
"""

import uvicorn

from extractor.config import settings


def main() -> None:
    uvicorn.run(
        "extractor.main:app",
        host="0.0.0.0",
        port=settings.PORT,
        log_level=settings.LOG_LEVEL.lower(),
        access_log=False,
    )


if __name__ == "__main__":
    main()
