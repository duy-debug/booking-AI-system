"use client";

import type { ReactNode } from "react";
import { Button } from "@/components/ui/Button";

export const OPEN_CHAT_EVENT = "komorebi:open-chat";

interface ChatOpenButtonProps {
  children: ReactNode;
  className?: string;
  variant?: "primary" | "secondary" | "ghost";
}

// CTA dùng chung để các section landing mở popup chat bằng cùng một custom event.
export function ChatOpenButton({
  children,
  className,
  variant = "primary",
}: ChatOpenButtonProps) {
  return (
    <Button
      className={className}
      type="button"
      variant={variant}
      onClick={() => window.dispatchEvent(new Event(OPEN_CHAT_EVENT))}
    >
      {children}
    </Button>
  );
}
