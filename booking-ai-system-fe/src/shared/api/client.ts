import { supabase } from "@/shared/lib/supabase";
import { ApiError, type ApiErrorBody } from "@/shared/types/api-error";

// API client tập trung: tự động gắn Bearer token từ Supabase session,
// unwrap response { data, meta }, và ném ApiError (RFC 9457) khi lỗi.
// Căn cứ: app/main.py (bọc {data}), app/core/exceptions.py (format lỗi),
//          docs/frontend-analysis.md §6.3, §6.4.

// Chuẩn hóa URL backend từ biến môi trường và loại bỏ dấu gạch chéo cuối để ghép đường dẫn API chính xác.
const API_BASE_URL = (() => {
  const url = process.env.NEXT_PUBLIC_API_URL;
  return url ? url.replace(/\/$/, "") : "http://localhost:8000";
})();

export interface ApiMeta {
  total?: number;
  limit?: number;
  next_cursor?: string | null;
}

export interface ApiListResponse<T> {
  data: T[];
  meta: ApiMeta;
}

export interface ApiSingleResponse<T> {
  data: T;
}

// Đọc Supabase session hiện tại và trả access token để gắn vào Authorization header nếu có.
async function getAccessToken(): Promise<string | null> {
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}

// Gửi HTTP request chung, parse JSON envelope và chuyển Problem Details của backend thành ApiError.
async function request<T>(
  method: string,
  path: string,
  options: {
    body?: unknown;
    query?: Record<string, string | number | boolean | undefined | null>;
    headers?: Record<string, string>;
    anonymous?: boolean;
  } = {},
): Promise<T> {
  const url = new URL(`${API_BASE_URL}${path}`);
  if (options.query) {
    for (const [k, v] of Object.entries(options.query)) {
      if (v !== undefined && v !== null) {
        url.searchParams.set(k, String(v));
      }
    }
  }

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers ?? {}),
  };

  if (!options.anonymous) {
    const token = await getAccessToken();
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
  }

  const res = await fetch(url.toString(), {
    method,
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });

  if (!res.ok) {
    let body: ApiErrorBody;
    try {
      body = (await res.json()) as ApiErrorBody;
    } catch {
      body = {
        type: "about:blank",
        title: "Unknown Error",
        status: res.status,
        detail: res.statusText,
        code: "UNKNOWN_ERROR",
      };
    }
    throw new ApiError(body);
  }

  // 204 No Content
  if (res.status === 204) {
    return undefined as T;
  }

  const json = (await res.json()) as { data?: unknown; meta?: ApiMeta };
  // Unwrap: list endpoint trả { data: [], meta }, single trả { data: {} }
  if (json && typeof json === "object" && "data" in json) {
    return json.data as T;
  }
  return json as T;
}

export const apiClient = {
  baseUrl: API_BASE_URL,
  get: <T>(path: string, opts?: Parameters<typeof request>[2]) =>
    request<T>("GET", path, opts),
  post: <T>(path: string, body?: unknown, opts?: Parameters<typeof request>[2]) =>
    request<T>("POST", path, { ...opts, body }),
  patch: <T>(path: string, body?: unknown, opts?: Parameters<typeof request>[2]) =>
    request<T>("PATCH", path, { ...opts, body }),
  delete: <T>(path: string, opts?: Parameters<typeof request>[2]) =>
    request<T>("DELETE", path, opts),
  // POST với header tuỳ chỉnh (vd Idempotency-Key)
  postWithHeaders: <T>(
    path: string,
    body: unknown,
    headers: Record<string, string>,
    opts?: Parameters<typeof request>[2],
  ) => request<T>("POST", path, { ...opts, body, headers }),
};
