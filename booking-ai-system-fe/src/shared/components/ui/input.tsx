import { type InputHTMLAttributes } from "react";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

// Render input có label liên kết accessibility và thông báo validation ngay dưới trường dữ liệu.
export function Input({ label, error, className = "", id, ...rest }: InputProps) {
  const inputId = id ?? rest.name;
  return (
    <div className="mb-4">
      {label && (
        <label
          htmlFor={inputId}
          className="mb-1 block text-sm font-medium text-zinc-700"
        >
          {label}
        </label>
      )}
      <input
        id={inputId}
        className={`w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${
          error ? "border-red-500" : "border-zinc-300"
        } ${className}`}
        {...rest}
      />
      {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
    </div>
  );
}
