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


def _saved_connector(workspace: str = "workspace") -> dict:
    """The connector settings kept in the workspace, where the connector was set up here."""
    path = Path(workspace) / "connector.json"
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def main(a) -> int:
    url = a.url or os.environ.get("HWPLOT_URL", "")
    token = a.token or os.environ.get("HWPLOT_TOKEN", "")
    saved = _saved_connector()
    if not url and saved.get("relay_project"):  # on the machine that set the connector up
        url = f"https://{saved['relay_project']}.pages.dev/mcp"
        token = token or saved.get("secret", "")
    if not url:
        raise SystemExit("Give the connector address with --url or HWPLOT_URL (e.g. https://hwplot-xxxx.pages.dev/mcp)")
    args = json.loads(a.args) if a.args else {}
    if a.photo:  # put_photo: send a local image file without pasting base64 on the command line
        args = {"filename": Path(a.photo).name, "data_base64": base64.b64encode(Path(a.photo).read_bytes()).decode()}
    if a.file:  # print_file: send a local G-code file, gzipped (too big for a command-line argument)
        import gzip
        data = gzip.compress(Path(a.file).read_bytes())
        args = {"filename": Path(a.file).name, "gcode_gzip_base64": base64.b64encode(data).decode()}
    return call(url, a.tool, args, a.out, token)
