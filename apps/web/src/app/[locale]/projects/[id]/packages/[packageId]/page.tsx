"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import Link from "next/link";
import { use, useState } from "react";

import { api } from "@/lib/api";
import { Button, Card, CardTitle, ErrorNote, StatusBadge } from "@/components/ui";

interface LocalizedText {
  zh_CN: string;
  en_AU: string;
}

interface PackageDocument {
  package_id?: string;
  as_of_date?: string;
  sections?: { section_id: string; title: LocalizedText; claim_ids: string[] }[];
  claims?: {
    claim_id: string;
    type: string;
    text: LocalizedText;
    is_counterevidence?: boolean;
  }[];
  metrics?: {
    metric_id: string;
    name: LocalizedText;
    value: number;
    unit: string;
    period: string;
    as_of_date: string;
    source_id: string;
  }[];
  sources?: {
    source_id: string;
    title: string;
    type: string;
    url_or_document: string;
    reliability_tier: string;
  }[];
  quality?: { checks: { check_id: string; result: string; details?: string }[] };
}

export default function PackagePage({
  params,
}: {
  params: Promise<{ id: string; packageId: string }>;
}) {
  const { id, packageId } = use(params);
  const t = useTranslations("package");
  const tc = useTranslations("common");
  const tRun = useTranslations("run");
  const locale = useLocale();
  const lang = locale === "zh" ? "zh_CN" : "en_AU";

  const queryClient = useQueryClient();
  const [actionError, setActionError] = useState<string | null>(null);
  const pkg = useQuery({
    queryKey: ["package", packageId],
    queryFn: () => api.getPackage(packageId),
  });
  const artifacts = useQuery({
    queryKey: ["artifacts", pkg.data?.run_id],
    queryFn: () => api.listArtifacts(pkg.data!.run_id!),
    enabled: Boolean(pkg.data?.run_id),
  });
  const versions = useQuery({
    queryKey: ["versions", packageId],
    queryFn: () => api.listVersions(packageId),
  });
  const transition = useMutation({
    mutationFn: (action: "verify" | "approve" | "reject") =>
      action === "verify"
        ? api.verifyPackage(packageId)
        : action === "approve"
          ? api.approvePackage(packageId)
          : api.rejectPackage(packageId),
    onSuccess: () => {
      setActionError(null);
      void queryClient.invalidateQueries({ queryKey: ["package", packageId] });
      void queryClient.invalidateQueries({ queryKey: ["versions", packageId] });
    },
    onError: (error: unknown) => setActionError(String(error)),
  });

  if (pkg.isLoading) {
    return <p className="text-sm text-[#563F7C]">{tc("loading")}</p>;
  }
  if (pkg.isError || !pkg.data) {
    return <ErrorNote>{tc("error", { message: String(pkg.error) })}</ErrorNote>;
  }

  const document = pkg.data.document as PackageDocument;
  const claimsById = new Map((document.claims ?? []).map((claim) => [claim.claim_id, claim]));

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="flex items-center gap-3 text-2xl font-bold text-[#34234F]">
          {t("title")}
          <StatusBadge status={pkg.data.status} label={t(`status.${pkg.data.status}` as never)} />
          <StatusBadge
            status={pkg.data.is_mock ? "draft" : "verified"}
            label={pkg.data.is_mock ? t("mock") : t("real")}
          />
        </h1>
        <Link
          className="text-sm font-medium text-[#563F7C] hover:text-[#34234F]"
          href={`/${locale}/projects/${id}`}
        >
          ← {tRun("backToProject")}
        </Link>
      </div>
      <p className="-mt-4 text-sm text-slate-500">
        {document.package_id} · {document.as_of_date}
      </p>

      <div className="flex flex-wrap items-center gap-3">
        {pkg.data.status === "draft" || pkg.data.status === "rejected" ? (
          <Button onClick={() => transition.mutate("verify")} disabled={transition.isPending}>
            {t("verify")}
          </Button>
        ) : null}
        {pkg.data.status === "verified" && !pkg.data.is_mock ? (
          <Button onClick={() => transition.mutate("approve")} disabled={transition.isPending}>
            {t("approve")}
          </Button>
        ) : null}
        {pkg.data.status !== "approved" && pkg.data.status !== "rejected" ? (
          <Button
            variant="danger"
            onClick={() => transition.mutate("reject")}
            disabled={transition.isPending}
          >
            {t("reject")}
          </Button>
        ) : null}
        {(artifacts.data ?? [])
          .filter((artifact) => artifact.kind === "pdf" || artifact.kind === "pptx")
          .map((artifact) => (
            <a
              key={artifact.id}
              className="text-sm font-medium text-[#563F7C] underline hover:text-[#34234F]"
              href={api.artifactDownloadUrl(artifact.id)}
            >
              {t("download")} {artifact.kind.toUpperCase()}
              {artifact.edition ? ` · ${artifact.edition}` : ""}
            </a>
          ))}
      </div>
      {actionError ? <ErrorNote>{actionError}</ErrorNote> : null}
      {versions.data && versions.data.length > 0 ? (
        <p className="text-xs text-slate-500">
          {t("versions")}:{" "}
          {versions.data
            .map((item) => `v${item.version} ${item.status} (${item.digest.slice(0, 8)})`)
            .join(" · ")}
        </p>
      ) : null}

      <Card>
        <CardTitle>{t("sections")}</CardTitle>
        <div className="flex flex-col gap-4">
          {(document.sections ?? []).map((section) => (
            <div key={section.section_id}>
              <h3 className="font-semibold text-[#34234F]">{section.title[lang]}</h3>
              <ul className="mt-1 flex flex-col gap-1">
                {section.claim_ids.map((claimId) => {
                  const claim = claimsById.get(claimId);
                  if (!claim) {
                    return null;
                  }
                  return (
                    <li key={claimId} className="flex items-start gap-2 text-sm">
                      <span className="mt-0.5 shrink-0 font-mono text-xs text-slate-400">
                        {claimId}
                      </span>
                      <span
                        className={
                          claim.is_counterevidence ? "text-red-800" : "text-[#25232A]"
                        }
                      >
                        {claim.text[lang]}
                      </span>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>
      </Card>

      <Card>
        <CardTitle>{t("metrics")}</CardTitle>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#B7A3CB]/40 text-left text-xs text-slate-500">
                <th className="py-1.5 pr-3">ID</th>
                <th className="py-1.5 pr-3">{t("metrics")}</th>
                <th className="py-1.5 pr-3 text-right">Value</th>
                <th className="py-1.5 pr-3">Unit</th>
                <th className="py-1.5 pr-3">Period</th>
                <th className="py-1.5">Source</th>
              </tr>
            </thead>
            <tbody>
              {(document.metrics ?? []).map((metric) => (
                <tr key={metric.metric_id} className="border-b border-[#B7A3CB]/20">
                  <td className="py-1.5 pr-3 font-mono text-xs text-slate-400">
                    {metric.metric_id}
                  </td>
                  <td className="py-1.5 pr-3">{metric.name[lang]}</td>
                  <td className="py-1.5 pr-3 text-right font-mono">
                    {metric.value.toLocaleString()}
                  </td>
                  <td className="py-1.5 pr-3">{metric.unit}</td>
                  <td className="py-1.5 pr-3">{metric.period}</td>
                  <td className="py-1.5 font-mono text-xs text-slate-400">{metric.source_id}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card>
        <CardTitle>{t("sources")}</CardTitle>
        <ul className="flex flex-col gap-1.5 text-sm">
          {(document.sources ?? []).map((source) => (
            <li key={source.source_id} className="flex items-start gap-2">
              <span className="mt-0.5 shrink-0 font-mono text-xs text-slate-400">
                {source.source_id}
              </span>
              <span>
                {source.title}
                <span className="ml-2 text-xs text-slate-500">
                  {source.type} · {source.reliability_tier} · {source.url_or_document}
                </span>
              </span>
            </li>
          ))}
        </ul>
      </Card>

      <Card>
        <CardTitle>{t("quality")}</CardTitle>
        <ul className="grid gap-1.5 sm:grid-cols-2">
          {(document.quality?.checks ?? []).map((check) => (
            <li
              key={check.check_id}
              className="flex items-center justify-between rounded-lg border border-[#B7A3CB]/30 px-3 py-1.5 text-sm"
            >
              <span className="font-mono text-xs">{check.check_id}</span>
              <StatusBadge
                status={
                  check.result === "pass"
                    ? "succeeded"
                    : check.result === "fail"
                      ? "failed"
                      : "queued"
                }
                label={check.result}
              />
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
