import type { ReactNode } from "react";

interface CardProps {
  children: ReactNode;
  className?: string;
}

// Card layout dùng chung để tránh lặp class wrapper ở các section landing.
export function Card({ children, className = "" }: CardProps) {
  return <article className={`card${className ? ` ${className}` : ""}`}>{children}</article>;
}
