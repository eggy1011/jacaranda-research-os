"use client";

import { useEffect, useState } from "react";

type HealthState = "checking" | "healthy" | "unavailable";

interface HealthResponse {
  status?: string;
  service?: string;
}

const statusCopy: Record<HealthState, { label: string; detail: string }> = {
  checking: {
    label: "Checking",
    detail: "Contacting the Jacaranda API…",
  },
  healthy: {
    label: "Operational",
    detail: "The web and API services are connected.",
  },
  unavailable: {
    label: "Unavailable",
    detail: "The API is not responding. Check the development services.",
  },
};

export default function Home() {
  const [health, setHealth] = useState<HealthState>("checking");

  useEffect(() => {
    const controller = new AbortController();

    async function checkHealth() {
      try {
        const response = await fetch("/api/health", {
          cache: "no-store",
          signal: controller.signal,
        });
        const result = (await response.json()) as HealthResponse;
        setHealth(response.ok && result.status === "ok" ? "healthy" : "unavailable");
      } catch {
        if (!controller.signal.aborted) {
          setHealth("unavailable");
        }
      }
    }

    void checkHealth();
    return () => controller.abort();
  }, []);

  const status = statusCopy[health];

  return (
    <main className="min-h-screen px-6 py-10 sm:px-10 lg:px-16">
      <div className="mx-auto flex min-h-[calc(100vh-5rem)] max-w-6xl flex-col justify-between rounded-[2rem] border border-white/10 bg-slate-950/75 p-7 shadow-2xl shadow-violet-950/30 backdrop-blur sm:p-10 lg:p-14">
        <header className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className="grid size-10 place-items-center rounded-xl bg-violet-500 text-lg font-bold text-white shadow-lg shadow-violet-500/20">
              J
            </span>
            <div>
              <p className="text-sm font-semibold tracking-wide text-white">Jacaranda Research OS</p>
              <p className="text-xs text-slate-400">蓝楹会 AI 股票研究平台</p>
            </div>
          </div>
          <span className="rounded-full border border-violet-400/20 bg-violet-400/10 px-3 py-1 text-xs font-medium text-violet-200">
            Engineering baseline
          </span>
        </header>

        <section className="grid gap-10 py-16 lg:grid-cols-[1.4fr_0.8fr] lg:items-end">
          <div>
            <p className="mb-5 text-sm font-semibold uppercase tracking-[0.22em] text-violet-300">
              Bilingual · Traceable · Human reviewed
            </p>
            <h1 className="max-w-3xl text-4xl font-semibold leading-tight tracking-tight text-white sm:text-6xl">
              Research infrastructure, ready for the first evidence.
            </h1>
            <p className="mt-6 max-w-2xl text-base leading-7 text-slate-300 sm:text-lg">
              The Phase 1 foundation connects a secure web application to the Jacaranda API. Market data,
              research generation, and presentation rendering remain intentionally disabled.
            </p>
          </div>

          <aside className="rounded-2xl border border-white/10 bg-white/[0.04] p-6">
            <div className="flex items-center justify-between gap-4">
              <p className="text-sm font-medium text-slate-300">Backend status</p>
              <span className={`status-dot status-dot--${health}`} aria-hidden="true" />
            </div>
            <p className="mt-5 text-2xl font-semibold text-white" aria-live="polite">
              {status.label}
            </p>
            <p className="mt-2 text-sm leading-6 text-slate-400">{status.detail}</p>
          </aside>
        </section>

        <footer className="flex flex-col gap-2 border-t border-white/10 pt-6 text-xs text-slate-500 sm:flex-row sm:items-center sm:justify-between">
          <span>A-shares first · US-ready provider architecture</span>
          <span>No provider credentials are sent to the browser.</span>
        </footer>
      </div>
    </main>
  );
}
