import type { ReactNode } from "react";

interface ContainerProps {
  children: ReactNode;
  className?: string;
}

// Container chuẩn hóa chiều rộng nội dung để các section landing có spacing thống nhất.
export function Container({ children, className = "" }: ContainerProps) {
  return <div className={`container${className ? ` ${className}` : ""}`}>{children}</div>;
}
