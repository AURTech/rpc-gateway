import { getApiBaseUrl } from "@/api/base-url";

/** Default per-request timeout in milliseconds. */
const DEFAULT_TIMEOUT_MS = 15_000;
const CSRF_HEADER = "X-RPC-Gateway-CSRF";
const MUTATING_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  /**
   * Query params. Array values are repeated (`?k=a&k=b`) so list-typed FastAPI
   * params (e.g. `chain: list[RpcChain]`) deserialize correctly.
   */
  params?: Record<string, string | string[]>;
  /** Override the default request timeout (ms). Pass 0 to disable. */
  timeoutMs?: number;
}

/** How a request failed — drives user-facing messaging and retry strategy. */
type ApiErrorKind = "http" | "network" | "timeout";

/**
 * The backend returns errors as `{ success: false, msg: "<human readable>" }`
 * (see server/app/core/response.py::ErrorResponse). We surface `msg` as the error
 * message so users see real text instead of a generic HTTP status.
 */
interface ApiErrorBody {
  success?: boolean;
  msg?: string;
}

function defaultMessage(kind: ApiErrorKind, status: number): string {
  if (kind === "network") return "Network request failed";
  if (kind === "timeout") return "Request timed out";
  return `Request failed with status ${status}`;
}

class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number;
  readonly data: unknown;

  constructor(params: {
    kind: ApiErrorKind;
    status: number;
    data?: unknown;
    message?: string;
  }) {
    const { kind, status, data, message } = params;
    super(message?.trim() ? message : defaultMessage(kind, status));
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
    this.data = data;
  }

  /** 401 — session missing or expired. */
  get isUnauthorized(): boolean {
    return this.status === 401;
  }

  /** 403 — authenticated but not allowed. */
  get isForbidden(): boolean {
    return this.status === 403;
  }

  /** 404 — resource not found. */
  get isNotFound(): boolean {
    return this.status === 404;
  }

  /** 5xx — server-side failure. */
  get isServer(): boolean {
    return this.status >= 500;
  }

  /** 4xx — client-side error (auth, validation, not found). */
  get isClient(): boolean {
    return this.status >= 400 && this.status < 500;
  }
}

function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

async function request<T>(
  endpoint: string,
  options: RequestOptions = {},
): Promise<T> {
  const {
    body,
    params,
    headers: customHeaders,
    timeoutMs = DEFAULT_TIMEOUT_MS,
    signal: callerSignal,
    ...rest
  } = options;

  let url = `${getApiBaseUrl()}${endpoint}`;
  if (params) {
    const searchParams = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (Array.isArray(value)) {
        for (const v of value) searchParams.append(key, v);
      } else {
        searchParams.append(key, value);
      }
    }
    const qs = searchParams.toString();
    if (qs) url += `?${qs}`;
  }

  const headers = new Headers(customHeaders);
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (rest.method && MUTATING_METHODS.has(rest.method.toUpperCase())) {
    headers.set(CSRF_HEADER, "1");
  }

  // Token injection point — integrate your auth logic here
  // const token = getToken();
  // if (token) headers["Authorization"] = `Bearer ${token}`;

  const controller = new AbortController();
  let timedOut = false;
  const timer =
    timeoutMs > 0
      ? setTimeout(() => {
          timedOut = true;
          controller.abort();
        }, timeoutMs)
      : undefined;

  // Honour an externally-provided abort signal (e.g. React Query cancellation).
  if (callerSignal) {
    if (callerSignal.aborted) controller.abort();
    else
      callerSignal.addEventListener("abort", () => controller.abort(), {
        once: true,
      });
  }

  let response: Response;
  try {
    response = await fetch(url, {
      ...rest,
      credentials: "include",
      headers,
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
  } catch (error) {
    // fetch only rejects on network failure or abort — never on HTTP status.
    if (timedOut) {
      throw new ApiError({ kind: "timeout", status: 0 });
    }
    if (error instanceof DOMException && error.name === "AbortError") {
      // Caller-initiated cancellation: re-throw so React Query treats it as such.
      throw error;
    }
    throw new ApiError({ kind: "network", status: 0 });
  } finally {
    if (timer) clearTimeout(timer);
  }

  if (!response.ok) {
    const errorData = (await response
      .json()
      .catch(() => null)) as ApiErrorBody | null;
    throw new ApiError({
      kind: "http",
      status: response.status,
      data: errorData,
      message: errorData?.msg,
    });
  }

  // Handle 204 No Content
  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export const api = {
  get: <T>(endpoint: string, options?: RequestOptions) =>
    request<T>(endpoint, { ...options, method: "GET" }),

  post: <T>(endpoint: string, body?: unknown, options?: RequestOptions) =>
    request<T>(endpoint, { ...options, method: "POST", body }),

  put: <T>(endpoint: string, body?: unknown, options?: RequestOptions) =>
    request<T>(endpoint, { ...options, method: "PUT", body }),

  patch: <T>(endpoint: string, body?: unknown, options?: RequestOptions) =>
    request<T>(endpoint, { ...options, method: "PATCH", body }),

  delete: <T>(endpoint: string, options?: RequestOptions) =>
    request<T>(endpoint, { ...options, method: "DELETE" }),
};

export { ApiError, isApiError };
export type { ApiErrorKind };
