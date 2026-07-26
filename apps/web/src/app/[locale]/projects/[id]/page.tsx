"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import Link from "next/link";
import { use, useRef, useState } from "react";

import { api, ApiError } from "@/lib/api";
import { Card, CardTitle, Button, EmptyState, ErrorNote, StatusBadge } from "@/components/ui";

export default function ProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const t = useTranslations("project");
  const tRun = useTranslations("run");
  const tPkg = useTranslations("package");
  const tc = useTranslations("common");
  const locale = useLocale();
  const queryClient = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const project = useQuery({ queryKey: ["project", id], queryFn: () => api.getProject(id) });
  const uploads = useQuery({
    queryKey: ["uploads", id],
    queryFn: () => api.listUploads(id),
    refetchInterval: (query) =>
      query.state.data?.some((item) => item.status === "stored" || item.status === "parsing")
        ? 2000
        : false,
  });
  const runs = useQuery({
    queryKey: ["runs", id],
    queryFn: () => api.listRuns(id),
    refetchInterval: (query) =>
      query.state.data?.some((item) => item.status === "queued" || item.status === "running")
        ? 2000
        : false,
  });
  const packages = useQuery({
    queryKey: ["packages", id],
    queryFn: () => api.listPackages(id),
  });

  const upload = useMutation({
    mutationFn: (file: File) => api.uploadFile(id, file),
    onSuccess: () => {
      setActionError(null);
      void queryClient.invalidateQueries({ queryKey: ["uploads", id] });
    },
    onError: (error: unknown) => setActionError(String(error)),
  });
  const startRun = useMutation({
    mutationFn: () => api.createRun(id),
    onSuccess: () => {
      setActionError(null);
      void queryClient.invalidateQueries({ queryKey: ["runs", id] });
    },
    onError: (error: unknown) =>
      setActionError(
        error instanceof ApiError && error.status === 409 ? t("runInProgress") : String(error),
      ),
  });

  if (project.isLoading) {
    return <p className="text-sm text-[#563F7C]">{tc("loading")}</p>;
  }
  if (project.isError || !project.data) {
    return <ErrorNote>{tc("error", { message: String(project.error) })}</ErrorNote>;
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-[#34234F]">
          {project.data.symbol} · {t("overview")}
        </h1>
        <Button
          onClick={() => startRun.mutate()}
          disabled={startRun.isPending || runs.data?.some((r) => r.status === "queued" || r.status === "running")}
        >
          {t("startRun")}
        </Button>
      </div>
      <p className="-mt-4 text-sm text-[#563F7C]">{t("startRunHint")}</p>
      {actionError ? <ErrorNote>{actionError}</ErrorNote> : null}

      <Card>
        <CardTitle>{t("uploads")}</CardTitle>
        <p className="mb-3 text-sm text-[#563F7C]">{t("uploadHint")}</p>
        <input
          ref={fileInput}
          type="file"
          accept=".pdf,.docx,.xlsx"
          className="hidden"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) {
              upload.mutate(file);
              event.target.value = "";
            }
          }}
        />
        <Button
          variant="secondary"
          disabled={upload.isPending}
          onClick={() => fileInput.current?.click()}
        >
          {upload.isPending ? t("uploading") : t("uploadButton")}
        </Button>
        <ul className="mt-4 flex flex-col gap-2">
          {uploads.data?.map((item) => (
            <li
              key={item.id}
              className="flex items-center justify-between rounded-lg border border-[#B7A3CB]/40 px-3 py-2 text-sm"
            >
              <span className="truncate font-medium text-[#34234F]">{item.filename}</span>
              <span className="flex items-center gap-3">
                <span className="text-xs text-slate-500">
                  {(item.size_bytes / 1024).toFixed(0)} KB
                </span>
                <StatusBadge
                  status={item.status}
                  label={t(`uploadStatus.${item.status}` as never)}
                />
              </span>
            </li>
          ))}
        </ul>
      </Card>

      <Card>
        <CardTitle>{t("runs")}</CardTitle>
        {runs.data && runs.data.length > 0 ? (
          <ul className="flex flex-col gap-2">
            {runs.data.map((run) => (
              <li
                key={run.id}
                className="flex items-center justify-between rounded-lg border border-[#B7A3CB]/40 px-3 py-2 text-sm"
              >
                <span className="flex items-center gap-3">
                  <StatusBadge status={run.status} label={tRun(`status.${run.status}` as never)} />
                  <span className="text-xs text-slate-500">
                    {new Date(run.created_at).toLocaleString()}
                  </span>
                </span>
                <Link
                  className="font-medium text-[#563F7C] hover:text-[#34234F]"
                  href={`/${locale}/projects/${id}/runs/${run.id}`}
                >
                  {t("viewRun")} →
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState>{t("noRuns")}</EmptyState>
        )}
      </Card>

      <Card>
        <CardTitle>{t("packages")}</CardTitle>
        {packages.data && packages.data.length > 0 ? (
          <ul className="flex flex-col gap-2">
            {packages.data.map((item) => (
              <li
                key={item.id}
                className="flex items-center justify-between rounded-lg border border-[#B7A3CB]/40 px-3 py-2 text-sm"
              >
                <span className="flex items-center gap-3">
                  <span className="font-medium text-[#34234F]">{item.package_uid}</span>
                  <StatusBadge
                    status={item.status}
                    label={tPkg(`status.${item.status}` as never)}
                  />
                </span>
                <Link
                  className="font-medium text-[#563F7C] hover:text-[#34234F]"
                  href={`/${locale}/projects/${id}/packages/${item.id}`}
                >
                  {t("viewPackage")} →
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState>{t("noPackages")}</EmptyState>
        )}
      </Card>
    </div>
  );
}
