import { NextRequest, NextResponse } from "next/server";

// Same-origin proxy to the server-only API. The browser never talks to the
// backend directly and provider credentials never reach the client.
const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8000";
const ALLOWED_METHODS = new Set(["GET", "POST", "PATCH", "DELETE"]);

async function forward(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
): Promise<NextResponse> {
  if (!ALLOWED_METHODS.has(request.method)) {
    return NextResponse.json({ detail: "method not allowed" }, { status: 405 });
  }
  const { path } = await params;
  const search = request.nextUrl.search;
  const target = `${API_BASE_URL}/${path.map(encodeURIComponent).join("/")}${search}`;
  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  if (contentType) {
    headers.set("content-type", contentType);
  }
  try {
    const response = await fetch(target, {
      method: request.method,
      headers,
      body: request.method === "GET" ? undefined : request.body,
      // Streams (uploads) require half-open duplex in Node fetch.
      // @ts-expect-error duplex is not yet in the fetch types
      duplex: request.method === "GET" ? undefined : "half",
      signal: AbortSignal.timeout(120_000),
      cache: "no-store",
    });
    const responseHeaders = new Headers();
    for (const name of ["content-type", "content-disposition", "content-length"]) {
      const value = response.headers.get(name);
      if (value) {
        responseHeaders.set(name, value);
      }
    }
    return new NextResponse(response.body, {
      status: response.status,
      headers: responseHeaders,
    });
  } catch {
    return NextResponse.json({ detail: "backend unavailable" }, { status: 503 });
  }
}

export {
  forward as GET,
  forward as POST,
  forward as PATCH,
  forward as DELETE,
};
