export type DependencyHealth = { status: "ok" | "error"; detail: string };
export type ReadinessResponse = { status: "ready" | "not_ready"; dependencies: Record<string, DependencyHealth> };
export type ProductVersion = { id: string; version: string; platform: string | null };
export type ProductModel = { id: string; model: string; aliases: string[]; hardware_revisions: string[]; versions: ProductVersion[] };
export type Product = { id: string; brand: string; name: string; category: string; aliases: string[]; models: ProductModel[] };
export type Document = { id: string; product_id: string; product_model_id: string | null; product_version_id: string | null; title: string; source_type: string; source_url: string | null; language: string; document_type: string; content_hash: string; status: string; error_message: string | null };
export type Job = { id: string; document_id: string; status: string; attempts: number; max_attempts: number; error_message: string | null };
export type TrustedSource = { id: string; brand: string; canonical_host: string; allowed_subdomains: string[]; allowed_path_prefixes: string[]; source_type: string; enabled: boolean };
export type IndexVersion = { id: string; version: string; status: string; document_count: number; chunk_count: number; published_at: string | null };

async function request<T>(path: string, apiKey?: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (apiKey) headers.set("X-Admin-API-Key", apiKey);
  const response = await fetch(path, { ...init, headers });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(body?.detail ?? `请求失败 (${response.status})`);
  }
  return (await response.json()) as T;
}

export function getReadiness(): Promise<ReadinessResponse> { return request<ReadinessResponse>("/api/v1/health/ready"); }
export const adminApi = {
  products: (key: string) => request<Product[]>("/api/v1/admin/products", key),
  seed: (key: string) => request<{ created: number; products: number; trusted_sources: number }>("/api/v1/admin/catalog/seed", key, { method: "POST" }),
  documents: (key: string) => request<Document[]>("/api/v1/admin/documents", key),
  sources: (key: string) => request<TrustedSource[]>("/api/v1/admin/trusted-sources", key),
  jobs: (key: string) => request<Job[]>("/api/v1/admin/ingestion-jobs", key),
  indexes: (key: string) => request<IndexVersion[]>("/api/v1/admin/index-versions", key),
  archive: (key: string, id: string) => request<Document>(`/api/v1/admin/documents/${id}/archive`, key, { method: "POST" }),
  retry: (key: string, id: string) => request<Job>(`/api/v1/admin/ingestion-jobs/${id}/retry`, key, { method: "POST" }),
  upload: (key: string, form: FormData) => request<Document>("/api/v1/admin/documents", key, { method: "POST", body: form }),
};
