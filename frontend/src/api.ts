export type DependencyHealth = {
  status: "ok" | "error";
  detail: string;
};

export type ReadinessResponse = {
  status: "ready" | "not_ready";
  dependencies: Record<string, DependencyHealth>;
};

export async function getReadiness(): Promise<ReadinessResponse> {
  const response = await fetch("/api/v1/health/ready");
  const data = (await response.json()) as ReadinessResponse;
  if (!response.ok && response.status !== 503) {
    throw new Error("无法读取后端状态");
  }
  return data;
}
