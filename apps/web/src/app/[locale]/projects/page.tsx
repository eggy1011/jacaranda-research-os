"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import Link from "next/link";
import { useState } from "react";

import { api, ApiError } from "@/lib/api";
import { Card, CardTitle, Button, EmptyState, ErrorNote } from "@/components/ui";

export default function ProjectsPage() {
  const t = useTranslations("projects");
  const tc = useTranslations("common");
  const locale = useLocale();
  const queryClient = useQueryClient();
  const [symbol, setSymbol] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  const projects = useQuery({ queryKey: ["projects"], queryFn: api.listProjects });
  const create = useMutation({
    mutationFn: api.createProject,
    onSuccess: () => {
      setSymbol("");
      setFormError(null);
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
    onError: (error: unknown) => {
      setFormError(
        error instanceof ApiError && error.status === 422 ? t("symbolInvalid") : String(error),
      );
    },
  });

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-bold text-[#34234F]">{t("title")}</h1>

      <Card>
        <CardTitle>{t("create")}</CardTitle>
        <form
          className="flex flex-wrap items-center gap-3"
          onSubmit={(event) => {
            event.preventDefault();
            if (symbol.trim()) {
              create.mutate(symbol.trim());
            }
          }}
        >
          <input
            value={symbol}
            onChange={(event) => setSymbol(event.target.value)}
            placeholder={t("symbolPlaceholder")}
            className="w-72 rounded-lg border border-[#B7A3CB] px-3 py-2 text-sm focus:border-[#563F7C] focus:outline-none"
          />
          <Button type="submit" disabled={create.isPending || !symbol.trim()}>
            {t("create")}
          </Button>
        </form>
        {formError ? <div className="mt-3"><ErrorNote>{formError}</ErrorNote></div> : null}
      </Card>

      {projects.isLoading ? (
        <p className="text-sm text-[#563F7C]">{tc("loading")}</p>
      ) : projects.isError ? (
        <ErrorNote>{tc("error", { message: String(projects.error) })}</ErrorNote>
      ) : projects.data && projects.data.length > 0 ? (
        <div className="grid gap-4 sm:grid-cols-2">
          {projects.data.map((project) => (
            <Link key={project.id} href={`/${locale}/projects/${project.id}`}>
              <Card className="transition hover:border-[#563F7C]">
                <p className="text-lg font-semibold text-[#34234F]">{project.symbol}</p>
                <p className="mt-1 text-sm text-[#563F7C]">
                  {t("market")}: {project.market}
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  {t("created")}: {new Date(project.created_at).toLocaleString()}
                </p>
              </Card>
            </Link>
          ))}
        </div>
      ) : (
        <EmptyState>{t("empty")}</EmptyState>
      )}
    </div>
  );
}
