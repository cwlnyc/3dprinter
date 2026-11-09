// Exercise the relay function with a fake KV and a fake Mac behind it.
import { onRequest } from "./functions/[[path]].js";
const store = new Map();
const env = { HWPLOT_SECRET: "s3cret", HWPLOT: { put: async (k, v) => store.set(k, v), get: async (k) => store.get(k) ?? null } };
const seen = [];
globalThis.fetch = async (url, init) => { seen.push([url, init.method, init.headers.get("host")]); return new Response("from mac", { status: 200 }); };
const call = (path, init = {}) => onRequest({ request: new Request("https://relay.pages.dev" + path, init), env });
const check = (name, ok) => { console.log((ok ? "ok   " : "FAIL ") + name); if (!ok) process.exitCode = 1; };

check("no secret -> 404", (await call("/mcp")).status === 404);
check("wrong secret -> 404", (await call("/nope/mcp")).status === 404);
check("before registering -> 503", (await call("/s3cret/mcp")).status === 503);
check("registering a non-tunnel address is refused", (await call("/s3cret/register", { method: "POST", body: JSON.stringify({ origin: "https://evil.example.com" }) })).status === 400);
const reg = await call("/s3cret/register", { method: "POST", body: JSON.stringify({ origin: "https://brave-lion.trycloudflare.com" }) });
check("registering the tunnel works", reg.status === 200 && store.get("origin") === "https://brave-lion.trycloudflare.com");
const r = await call("/s3cret/mcp?x=1", { method: "POST", body: "{}", headers: { "content-type": "application/json" } });
check("requests are forwarded to the Mac", r.status === 200 && (await r.text()) === "from mac");
check("…to the right place, path and all", seen[0][0] === "https://brave-lion.trycloudflare.com/s3cret/mcp?x=1" && seen[0][1] === "POST" && seen[0][2] === null);
