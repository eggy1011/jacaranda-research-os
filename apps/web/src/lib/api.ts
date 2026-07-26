// Typed client for the same-origin backend proxy (/api/backend/...).

export interface Project {
  id: string;
  symbol: string;
  market: string;
  company_name_zh: string | null;
  company_name_en: string | null;
  created_at: string;
  updated_at: string;
}

export interface RunStage {
  key: string;
  status: "started" | "completed" | "cached" | "failed" | string;
  detail: Record<string, unknown> | null;
  updated_at: string;
}

export interface Run {
  id: string;
  project_id: string;
  symbol: string;
  status: "queued" | "running" | "succeeded" | "failed" | string;
  attempt: number;
  error: { code?: string; message?: string } | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface RunDetail extends Run {
  stages: RunStage[];
}

export interface Upload {
  id: string;
  project_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  status: "stored" | "parsing" | "parsed" | "failed" | string;
  error: { code?: string; message?: string } | null;
  created_at: string;
  updated_at: string;
}

export interface PackageSummary {
  id: string;
  project_id: string;
  run_id: string | null;
  package_uid: string;
  status: "draft" | "verified" | "approved" | "rejected" | string;
  is_mock: boolean;
  created_at: string;
  updated_at: string;
}

export interface PackageDetail extends PackageSummary {
  document: Record<string, unknown>;
}

export interface Artifact {
  id: string;
  run_id: string;
  kind: string;
  edition: string | null;
  path: string;
  sha256: string | null;
}

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/backend/${path}`, { cache: "no-store", ...init });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") {
        detail = body.detail;
      }
    } catch {
      // keep the status text
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

export const api = {
  listProjects: () => request<Project[]>("projects"),
  createProject: (symbol: string) =>
    request<Project>("projects", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ symbol }),
    }),
  getProject: (id: string) => request<Project>(`projects/${id}`),
  listRuns: (projectId: string) => request<Run[]>(`projects/${projectId}/runs`),
  createRun: (projectId: string) =>
    request<Run>(`projects/${projectId}/runs`, { method: "POST" }),
  getRun: (runId: string) => request<RunDetail>(`runs/${runId}`),
  retryRun: (runId: string) => request<Run>(`runs/${runId}/retry`, { method: "POST" }),
  listUploads: (projectId: string) => request<Upload[]>(`projects/${projectId}/uploads`),
  uploadFile: (projectId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<Upload>(`projects/${projectId}/uploads`, { method: "POST", body: form });
  },
  listPackages: (projectId: string) =>
    request<PackageSummary[]>(`projects/${projectId}/packages`),
  getPackage: (packageId: string) => request<PackageDetail>(`packages/${packageId}`),
  verifyPackage: (packageId: string) =>
    request<PackageSummary>(`packages/${packageId}/verify`, { method: "POST" }),
  approvePackage: (packageId: string) =>
    request<PackageSummary>(`packages/${packageId}/approve`, { method: "POST" }),
  rejectPackage: (packageId: string) =>
    request<PackageSummary>(`packages/${packageId}/reject`, { method: "POST" }),
  listVersions: (packageId: string) =>
    request<{ version: number; status: string; digest: string; created_at: string }[]>(
      `packages/${packageId}/versions`,
    ),
  listArtifacts: (runId: string) => request<Artifact[]>(`runs/${runId}/artifacts`),
  artifactDownloadUrl: (artifactId: string) =>
    `/api/backend/artifacts/${artifactId}/download`,
};
