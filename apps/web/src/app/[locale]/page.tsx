"use client";

import { useTranslations, useLocale } from "next-intl";
import Link from "next/link";
import { useEffect, useState } from "react";

import { Card } from "@/components/ui";

type HealthState = "checking" | "healthy" | "unavailable";

export default function Home() {
  const t = useTranslations("home");
  const locale = useLocale();
  const [health, setHealth] = useState<HealthState>("checking");

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/health", { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        const body = (await response.json()) as { status?: string };
        setHealth(response.ok && body.status === "ok" ? "healthy" : "unavailable");
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setHealth("unavailable");
        }
      });
    return () => controller.abort();
  }, []);

  return (
    <div className="flex flex-col gap-8 py-8">
      <div>
        <h1 className="max-w-2xl text-4xl font-bold leading-tight text-[#34234F]">
          {t("heading")}
        </h1>
        <p className="mt-4 max-w-xl text-base text-[#563F7C]">{t("sub")}</p>
        <Link
          href={`/${locale}/projects`}
          className="mt-6 inline-block rounded-lg bg-[#563F7C] px-5 py-2.5 text-sm font-medium text-white hover:bg-[#34234F]"
        >
          {t("cta")}
        </Link>
      </div>
      <Card className="max-w-sm">
        <div className="flex items-center justify-between">
          <span className="text-sm text-[#563F7C]">{t("backend")}</span>
          <span
            className={`size-3 rounded-full ${
              health === "healthy"
                ? "bg-green-500"
                : health === "checking"
                  ? "bg-amber-400"
                  : "bg-red-500"
            }`}
            aria-label={health}
          />
        </div>
      </Card>
    </div>
  );
}
