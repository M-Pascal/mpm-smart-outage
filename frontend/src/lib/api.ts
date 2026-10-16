/** Thin client for the PowerChat API. Unwraps {"data": ...} and turns {"error": ...} into ApiError. */
export interface FieldError { field: string | null; message: string }

export class ApiError extends Error {
  constructor(public status: number, message: string, public code = "error", public details: FieldError[] = []) {
    super(message);
  }
  fieldErrors(): Record<string, string> {
    const out: Record<string, string> = {};
    for (const d of this.details) if (d.field) out[d.field.split(".")[0]] = d.message;
    return out;
  }
}

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "/api";

async function request<T>(method: string, path: string, body?: unknown): Promise<{ data: T; meta?: Record<string, unknown> }> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      method,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "Cannot reach the PowerChat server. Make sure the backend is running on port 8000.", "network");
  }
  let json: any = null;
  try {
    json = await res.json();
  } catch {
    /* empty body */
  }
  if (!res.ok) {
    const err = json?.error;
    throw new ApiError(res.status, err?.message ?? `Request failed (${res.status})`, err?.code, err?.details ?? []);
  }
  return json;
}

export const api = {
  get: async <T>(path: string) => (await request<T>("GET", path)).data,
  getWithMeta: <T>(path: string) => request<T>("GET", path),
  post: async <T>(path: string, body?: unknown) => (await request<T>("POST", path, body ?? {})).data,
  postWithMeta: <T>(path: string, body?: unknown) => request<T>("POST", path, body ?? {}),
  put: async <T>(path: string, body: unknown) => (await request<T>("PUT", path, body)).data,
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, body),
};

export function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}
