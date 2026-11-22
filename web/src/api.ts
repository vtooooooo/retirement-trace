import type { Role } from "./workflow";

export interface Session {
  tenant: string;
  role: Role;
  name: string;
}

export interface Participant {
  id: string;
  name: string;
  case_id: string | null;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

const base = import.meta.env.VITE_API_BASE || "/api/v1";
if (!/^\/api\/[\w/-]+$/.test(base) || base.endsWith("/")) {
  throw new Error("VITE_API_BASE must be a same-origin API path");
}

export async function api(path: string, init?: RequestInit): Promise<Response> {
  const readOnly = !init?.method || init.method === "GET";
  const maxAttempts = readOnly ? 2 : 1;
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    const deadline = AbortSignal.timeout(82_000);
    const signal = init?.signal
      ? AbortSignal.any([init.signal, deadline])
      : deadline;
    let response;
    try {
      response = await fetch(base + path, {
        ...init,
        signal,
        credentials: "same-origin",
        cache: "no-store",
      });
    } catch (error) {
      if (init?.signal?.aborted) throw error;
      if (attempt + 1 < maxAttempts) {
        await new Promise((resolve) => setTimeout(resolve, 2_000));
        init?.signal?.throwIfAborted();
        continue;
      }
      throw new ApiError(
        503,
        "The backend did not respond. Try again in a moment.",
      );
    }
    if (response.ok) return response;
    if (
      attempt + 1 < maxAttempts &&
      [502, 503, 504].includes(response.status)
    ) {
      await response.body?.cancel();
      const delay = Math.min(
        5,
        Math.max(1, Number(response.headers.get("Retry-After")) || 2),
      );
      await new Promise((resolve) => setTimeout(resolve, delay * 1_000));
      init?.signal?.throwIfAborted();
      continue;
    }
    const body = await response.json().catch(() => null);
    throw new ApiError(
      response.status,
      typeof body?.detail === "string"
        ? body.detail
        : "The request could not be completed.",
    );
  }
  throw new ApiError(
    503,
    "The backend did not respond. Try again in a moment.",
  );
}

export function post(
  body: object,
  headers?: Record<string, string>,
): RequestInit {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify(body),
  };
}
