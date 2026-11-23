import type {
  HealthResponse,
  PresetRepoInfo,
  RepoSummary,
  SeanceAskResponse,
} from "./types";

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/+$/, "");

async function parseErrorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as {
      detail?: string | Array<{ msg?: string }>;
    };
    if (typeof body.detail === "string" && body.detail.trim()) {
      return body.detail;
    }
    if (Array.isArray(body.detail) && body.detail.length > 0) {
      return body.detail
        .map((item) => item.msg || "Validation error")
        .join("; ");
    }
  } catch {
    // Ignore JSON parse fallback
  }
  return `Request failed with HTTP ${response.status}`;
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response));
  }
  return (await response.json()) as T;
}

export function fetchHealth(): Promise<HealthResponse> {
  return requestJson<HealthResponse>("/api/health");
}

export function fetchPresets(): Promise<PresetRepoInfo[]> {
  return requestJson<PresetRepoInfo[]>("/api/presets");
}

export function summonRepo(params: {
  preset_id?: string;
  repo_url?: string;
}): Promise<RepoSummary> {
  return requestJson<RepoSummary>("/api/repo/summon", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export function askSeance(
  repo_id: string,
  question: string,
  top_k = 5
): Promise<SeanceAskResponse> {
  return requestJson<SeanceAskResponse>("/api/seance/ask", {
    method: "POST",
    body: JSON.stringify({ repo_id, question, top_k }),
  });
}
