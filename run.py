#!/usr/bin/env python3
"""
Entry point for running the Dot Service directly:
    python run.py
"""

import uvicorn

from app.config import get_settings


def main():
    s = get_settings()
    uvicorn.run(
        "app.main:app",
        host=s.service_host,
        port=s.service_port,
        reload=True,
    )


if __name__ == "__main__":
    main()
