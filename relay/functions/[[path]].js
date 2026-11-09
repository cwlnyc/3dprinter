// A permanent front door for the hwplot connector, on Cloudflare Pages.
//
// The connector runs on the user's Mac behind a free "quick" Cloudflare
// tunnel, whose address changes every time it starts. This site's address
// doesn't: Claude's connector points here, and every request is passed on to
// whatever tunnel address the Mac last registered.
//
//   POST /<secret>/register  {"origin": "https://xxx.trycloudflare.com"}  (the Mac, at start-up)
//   *    /<secret>/...        forwarded to <origin>/<secret>/...             (Claude)
//
// Anything without the secret gets a plain 404, the same as a page that
// doesn't exist, so the site gives nothing away.

const TUNNEL = /^https:\/\/[a-z0-9-]+\.trycloudflare\.com$/;

export async function onRequest({ request, env }) {
  const url = new URL(request.url);
  const [first, second] = url.pathname.split("/").filter(Boolean);
  if (!env.HWPLOT_SECRET || first !== env.HWPLOT_SECRET) {
    return new Response("Not found", { status: 404 });
  }

  if (second === "register" && request.method === "POST") {
    let origin;
    try {
      ({ origin } = await request.json());
    } catch {
      return new Response("expected JSON", { status: 400 });
    }
    // Only ever forward to a Cloudflare quick tunnel, never to an arbitrary address.
    if (typeof origin !== "string" || !TUNNEL.test(origin)) {
      return new Response("origin must be an https://….trycloudflare.com address", { status: 400 });
    }
    await env.HWPLOT.put("origin", origin);
    return Response.json({ ok: true, origin });
  }

  const origin = await env.HWPLOT.get("origin", { cacheTtl: 30 });
  if (!origin) {
    return new Response("The Mac isn't connected yet: start `python3 -m hwplot mcp --relay` on it.", { status: 503 });
  }
  // Pass the request on as-is, minus what Cloudflare added on the way in: a
  // request carrying another Cloudflare hop's headers (cf-*, cdn-loop) into a
  // Cloudflare tunnel can be taken for a loop and refused.
  const headers = new Headers();
  for (const [k, v] of request.headers) {
    const name = k.toLowerCase();
    if (name === "host" || name === "cdn-loop" || name.startsWith("cf-") || name.startsWith("x-forwarded-") || name === "x-real-ip") continue;
    headers.set(k, v);
  }
  const init = { method: request.method, headers, redirect: "manual" };
  if (!["GET", "HEAD"].includes(request.method)) {
    init.body = request.body;
    init.duplex = "half";
  }
  try {
    // The response is returned as it streams, so the connector's live updates pass straight through.
    return await fetch(origin + url.pathname + url.search, init);
  } catch {
    return new Response("The Mac didn't answer: is the connector still running?", { status: 502 });
  }
}
