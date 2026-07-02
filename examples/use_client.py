"""Use the package's async BeatportClient directly (token caching, auto
refresh and 401-retry included).

Usage:
    BEATPORT_USERNAME=you@example.com BEATPORT_PASSWORD=... \
        uv run python examples/use_client.py
"""

import asyncio

from beatport_mcp.client import BeatportClient
from beatport_mcp.formatters import slim_page, slim_track


async def main() -> None:
    async with BeatportClient() as client:
        data = await client.get("/catalog/tracks/", q="opus eric prydz", per_page=5)
        page = slim_page(data, slim_track)
        for track in page["results"]:
            print(track)


if __name__ == "__main__":
    asyncio.run(main())
