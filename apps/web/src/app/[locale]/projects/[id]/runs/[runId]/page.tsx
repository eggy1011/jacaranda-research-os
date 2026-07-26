"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import Link from "next/link";
import { use } from "react";

import { api } from "@/lib/api";
import { Card, CardTitle, Button, EmptyState, ErrorNote, StatusBadge } from "@/components/ui";

// The pipeline's canonical stage keys in execution order.
const STAGE_ORDER = [
  "00-evidence",
  "01-extraction",
  "02-source-verification",
  "03-S3a",
  "03-S3b",
  "03-S3c",
  "03-S3d",
  "04-valuation-narrative",
  "05-catalysts-risks",
  "06-translation",
  "07-deck-zh-CN",
  "07-deck-en-AU",
];

export default function RunPage({
  params,
}: {
  params: Promise<{ id: string; runId: string }>;
}) {
  const { id, runId } = use(params);
  const t = useTranslations("run");
  const tc = useTranslations("common");
  const locale = useLocale();
  const queryClient = useQueryClient();

  const run = useQuery({
    queryKey: ["run", runId],
    queryFn: () => api.getRun(runId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "queued" || status === "running" ? 2000 : false;
    },
  });
  const artifacts = useQuery({
    queryKey: ["artifacts", runId],
    queryFn: () => api.listArtifacts(runId),
    enabled: run.data?.status === "succeeded",
  });
  const retry = useMutation({
    mutationFn: () => api.retryRun(runId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["run", runId] }),
  });

  if (run.isLoading) {
    return <p className="text-sm text-[#563F7C]">{tc("loading")}</p>;
  }
  if (run.isError || !run.data) {
    return <ErrorNote>{tc("error", { message: String(run.error) })}</ErrorNote>;
  }

  const stagesByKey = new Map(run.data.stages.map((stage) => [stage.key, stage]));
  const orderedKeys = [
    ...STAGE_ORDER.filter((key) => stagesByKey.has(key)),
    ...run.data.stages.map((stage) => stage.key).filter((key) => !STAGE_ORDER.includes(key)),
  ];

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="flex items-center gap-3 text-2xl font-bold text-[#34234F]">
          {t("title")}
          <StatusBadge status={run.data.status} label={t(`status.${run.data.status}` as never)} />
        </h1>
        <Link
          className="text-sm font-medium text-[#563F7C] hover:text-[#34234F]"
          href={`/${locale}/projects/${id}`}
        >
          ← {t("backToProject")}
        </Link>
      </div>
      <p className="-mt-4 text-sm text-slate-500">
        {run.data.symbol} · {t("attempt", { n: run.data.attempt })}
      </p>

      {run.data.error ? (
        <ErrorNote>
          {t("error")}: {run.data.error.code ?? ""} {run.data.error.message ?? ""}
        </ErrorNote>
      ) : null}
      {run.data.status === "failed" ? (
        <div>
          <Button onClick={() => retry.mutate()} disabled={retry.isPending}>
            {t("retry")}
          </Button>
        </div>
      ) : null}

      <Card>
        <CardTitle>{t("stages")}</CardTitle>
        {orderedKeys.length === 0 ? (
          <EmptyState>{t("noStages")}</EmptyState>
        ) : (
          <ol className="flex flex-col gap-1.5">
            {orderedKeys.map((key) => {
              const stage = stagesByKey.get(key);
              return (
                <li
                  key={key}
                  className="flex items-center justify-between rounded-lg border border-[#B7A3CB]/30 px-3 py-2 text-sm"
                >
                  <span className="font-mono text-[#34234F]">{key}</span>
                  {stage ? (
                    <StatusBadge
                      status={stage.status}
                      label={t(`stageStatus.${stage.status}` as never)}
                    />
                  ) : null}
                </li>
              );
            })}
          </ol>
        )}
      </Card>

      {run.data.status === "succeeded" && artifacts.data ? (
        <Card>
          <CardTitle>{t("artifacts")}</CardTitle>
          <ul className="flex flex-col gap-2">
            {artifacts.data
              .filter((artifact) => ["pptx", "package", "deck-json"].includes(artifact.kind))
              .map((artifact) => (
                <li key={artifact.id}>
                  <a
                    className="text-sm font-medium text-[#563F7C] underline hover:text-[#34234F]"
                    href={api.artifactDownloadUrl(artifact.id)}
                  >
                    {artifact.kind}
                    {artifact.edition ? ` · ${artifact.edition}` : ""}
                  </a>
                </li>
              ))}
          </ul>
        </Card>
      ) : null}
    </div>
  );
}
