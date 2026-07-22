import { type ReactNode } from "react";

interface CardProps {
  title?: string;
  children: ReactNode;
  className?: string;
  actions?: ReactNode;
}

// Hiển thị khung nội dung dùng chung với tiêu đề, vùng action và style card quản trị nhất quán.
export function Card({ title, children, className = "", actions }: CardProps) {
  return (
    <div className={`rounded-xl border border-zinc-200 bg-white p-5 shadow-sm ${className}`}>
      {(title || actions) && (
        <div className="mb-4 flex items-center justify-between">
          {title && <h2 className="text-lg font-semibold text-zinc-900">{title}</h2>}
          {actions}
        </div>
      )}
      {children}
    </div>
  );
}
