import { afterEach, describe, expect, it, vi } from "vitest";

import { GET } from "../src/app/api/health/route";

describe("GET /api/health", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns the backend health response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ status: "ok", service: "jacaranda-api" }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      ),
    );

    const response = await GET();

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({ status: "ok", service: "jacaranda-api" });
    expect(fetch).toHaveBeenCalledWith(
      "http://localhost:8000/health",
      expect.objectContaining({ cache: "no-store" }),
    );
  });

  it("returns a safe unavailable response when the backend cannot be reached", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("connection refused")));

    const response = await GET();

    expect(response.status).toBe(503);
    await expect(response.json()).resolves.toEqual({ status: "unavailable" });
  });
});
