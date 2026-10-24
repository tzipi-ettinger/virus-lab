// Typed fetch for the API (PLAN-DEV-B 3.4). The session cookie goes along on
// the same origin, a problem+json answer becomes an ApiError, and a 401 tells the
// app to sign in again. Types come from schema.d.ts (npm run gen:api).
// Owner: A in CODEOWNERS; written by B (PLAN-DEV-B 3.2, A8)

import { t } from "../i18n";
import type { components } from "./schema";

export type Problem = components["schemas"]["Problem"];

const BASE = import.meta.env.VITE_API_BASE_URL ?? "";

export const NETWORK_ERROR = t("api.network");

export class ApiError extends Error {
  readonly status: number;
  readonly type: string;
  readonly detail: string | null;
  readonly blockingFields: string[];

  constructor(status: number, problem: Pick<Problem, "type" | "title"> & Partial<Problem>) {
    super(problem.title);
    this.name = "ApiError";
    this.status = status;
    this.type = problem.type;
    this.detail = problem.detail ?? null;
    this.blockingFields = problem.blocking_fields ?? [];
  }
}

let unauthorized: () => void = () => {};

/** Called on any 401 except a failed login. Returns a function that removes it. */
export function onUnauthorized(handler: () => void): () => void {
  unauthorized = handler;
  return () => {
    if (unauthorized === handler) unauthorized = () => {};
  };
}

export type RequestOptions = {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
  fetchImpl?: typeof fetch;
};

/** JSON in, JSON out. 204 resolves to undefined. Throws ApiError for any failure. */
export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, signal, fetchImpl = fetch } = options;
  let response: Response;
  try {
    response = await fetchImpl(`${BASE}${path}`, {
      method,
      credentials: "same-origin",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  } catch (error) {
    if (signal?.aborted) throw error; // the caller cancelled: not an error to show
    throw new ApiError(0, { type: "network_error", title: NETWORK_ERROR });
  }
  if (response.status === 401 && path !== LOGIN_PATH) unauthorized();
  if (!response.ok) throw new ApiError(response.status, await readProblem(response));
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

const LOGIN_PATH = "/api/v1/auth/login";

async function readProblem(response: Response): Promise<Problem> {
  if ((response.headers.get("content-type") ?? "").includes("json")) {
    try {
      const problem = (await response.json()) as Partial<Problem>;
      if (typeof problem.type === "string" && typeof problem.title === "string") {
        return { ...problem, type: problem.type, title: problem.title, status: response.status };
      }
    } catch {
      // not JSON after all: fall through to the generic message
    }
  }
  return {
    type: "http_error",
    title: t("api.server", { status: response.status }),
    status: response.status,
  };
}
