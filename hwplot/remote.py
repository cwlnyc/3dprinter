"""Call the connector's tools from somewhere else: python3 -m hwplot remote <tool> '<json args>'

For a Claude session that can't use the connector as a Claude connector (a
Claude Code cloud session, or while claude.ai's custom connectors are broken):
it calls one tool, prints the text it returns, and saves any images to files.

The address is the front door's /mcp with the secret as a bearer token. Where
the token comes from a saved network credential, nothing needs passing here:
the network adds it on the way out.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path


def call(url: str, tool: str, args: dict, out_dir: str = "remote-out", token: str = "") -> int:
    import anyio
    import httpx2
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    status = {"error": False}

    async def go():
        async with httpx2.AsyncClient(headers=headers, timeout=httpx2.Timeout(120, read=300)) as http:
            async with streamable_http_client(url, http_client=http) as streams:
                async with ClientSession(streams[0], streams[1]) as session:
                    await session.initialize()
                    if tool == "list":
                        for t in (await session.list_tools()).tools:
                            print(f"{t.name}: {(t.description or '').splitlines()[0]}")
                        return
                    result = await session.call_tool(tool, args)
                    status["error"] = bool(result.is_error)
                    n = 0
                    for c in result.content:
                        if getattr(c, "type", "") == "text":
                            print(c.text)
                        elif getattr(c, "type", "") == "image":
                            n += 1
                            ext = (c.mime_type or "image/jpeg").split("/")[-1].replace("jpeg", "jpg")
                            path = out / f"{tool}-{n}.{ext}"
                            path.write_bytes(base64.b64decode(c.data))
                            print(f"[image saved: {path.resolve()}]")

    anyio.run(go)
    return 1 if status["error"] else 0


def main(a) -> int:
    url = a.url or os.environ.get("HWPLOT_URL", "")
    if not url:
        raise SystemExit("Give the connector address with --url or HWPLOT_URL (e.g. https://hwplot-xxxx.pages.dev/mcp)")
    args = json.loads(a.args) if a.args else {}
    return call(url, a.tool, args, a.out, a.token or os.environ.get("HWPLOT_TOKEN", ""))
