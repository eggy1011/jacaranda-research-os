import { NextResponse } from "next/server";

const DEFAULT_API_BASE_URL = "http://localhost:8000";
const HEALTH_TIMEOUT_MS = 3_000;

export async function GET() {
  const apiBaseUrl = process.env.API_BASE_URL || DEFAULT_API_BASE_URL;

  try {
    const response = await fetch(`${apiBaseUrl}/health`, {
      cache: "no-store",
      signal: AbortSignal.timeout(HEALTH_TIMEOUT_MS),
    });
    const body: unknown = await response.json();

    if (!response.ok) {
      return NextResponse.json({ status: "unavailable" }, { status: 503 });
    }

    return NextResponse.json(body, { status: 200 });
  } catch {
    return NextResponse.json({ status: "unavailable" }, { status: 503 });
  }
}
