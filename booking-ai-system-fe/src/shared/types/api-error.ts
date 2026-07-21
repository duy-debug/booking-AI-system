// RFC 9457 Problem Details — format lỗi đồng nhất của backend.
// Căn cứ: app/core/exceptions.py, app/main.py:31-66, docs/frontend-analysis.md §6.4.

export interface ValidationErrorDetail {
  field: string;
  message: string;
}

export interface ApiErrorBody {
  type: string;
  title: string;
  status: number;
  detail: string;
  code: string;
  instance?: string;
  errors?: ValidationErrorDetail[];
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly detail: string;
  readonly instance?: string;
  readonly errors?: ValidationErrorDetail[];
  readonly body: ApiErrorBody;

  constructor(body: ApiErrorBody) {
    super(body.detail || body.title || "Lỗi không xác định");
    this.name = "ApiError";
    this.status = body.status;
    this.code = body.code;
    this.detail = body.detail;
    this.instance = body.instance;
    this.errors = body.errors;
    this.body = body;
  }

  // Trả về map field -> message để feed vào React Hook Form.
  fieldErrors(): Record<string, string> {
    const out: Record<string, string> = {};
    for (const e of this.errors ?? []) {
      out[e.field] = e.message;
    }
    return out;
  }
}
