import type { ReactNode } from "react";

interface CardProps {
  children: ReactNode;
  className?: string;
}

export function Card({ children, className = "" }: CardProps) {
  return <article className={`card${className ? ` ${className}` : ""}`}>{children}</article>;
}
