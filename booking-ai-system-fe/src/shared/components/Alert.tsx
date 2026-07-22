"use client";

import { CheckCircle2, CircleAlert, Info, TriangleAlert, X } from "lucide-react";

export type AlertTone = "success" | "error" | "warning" | "info";

const alertStyles: Record<AlertTone, { icon: typeof Info; className: string }> = {
  success: {
    icon: CheckCircle2,
    className: "border-emerald-200 bg-emerald-50 text-emerald-800",
  },
  error: {
    icon: CircleAlert,
    className: "border-red-200 bg-red-50 text-red-800",
  },
  warning: {
    icon: TriangleAlert,
    className: "border-amber-200 bg-amber-50 text-amber-800",
  },
  info: {
    icon: Info,
    className: "border-blue-200 bg-blue-50 text-blue-800",
  },
};

// Hiển thị một thông báo có màu và icon theo mức độ, kèm nút đóng hỗ trợ accessibility.
export function Alert({
  message,
  tone,
  onDismiss,
}: {
  message: string;
  tone: AlertTone;
  onDismiss: () => void;
}) {
  const style = alertStyles[tone];
  const Icon = style.icon;

  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={`pointer-events-auto flex w-full items-start gap-2.5 rounded-lg border px-3 py-2.5 shadow-lg ${style.className}`}
    >
      <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <p className="min-w-0 flex-1 text-sm font-medium leading-5">{message}</p>
      <button
        type="button"
        onClick={onDismiss}
        className="-mr-1 flex h-6 w-6 shrink-0 items-center justify-center rounded opacity-60 transition-opacity hover:bg-black/5 hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-current"
        aria-label="Đóng thông báo"
      >
        <X className="h-3.5 w-3.5" aria-hidden="true" />
      </button>
    </div>
  );
}
