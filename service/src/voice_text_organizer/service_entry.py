from __future__ import annotations

import os

import uvicorn

from voice_text_organizer.main import app


def main() -> None:
    host = os.getenv("VTO_HOST", "127.0.0.1")
    port = int(os.getenv("VTO_PORT", "8775"))
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
