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
  const response = await fetch(base + path, {
    ...init,
    credentials: "same-origin",
    cache: "no-store",
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = body?.detail;
    throw new ApiError(
      response.status,
      typeof detail === "string"
        ? detail
        : "The request could not be completed.",
    );
  }
  return response;
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
