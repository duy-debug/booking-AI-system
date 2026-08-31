import type { AnchorHTMLAttributes, ButtonHTMLAttributes, ReactNode } from "react";

type ButtonVariant = "primary" | "secondary" | "ghost";

interface CommonProps {
  children: ReactNode;
  className?: string;
  variant?: ButtonVariant;
}

// Button dùng chung để giữ variant/class nhất quán giữa landing page và CTA mở chatbot.
export function Button({
  children,
  className = "",
  variant = "primary",
  ...props
}: CommonProps & ButtonHTMLAttributes<HTMLButtonElement>) {
  const classes = `button button-${variant}${className ? ` ${className}` : ""}`;

  return (
    <button className={classes} {...props}>
      {children}
    </button>
  );
}

// Phiên bản link có style giống Button, dùng cho CTA điều hướng trong landing page.
export function ButtonLink({
  children,
  className = "",
  variant = "primary",
  ...props
}: CommonProps & AnchorHTMLAttributes<HTMLAnchorElement>) {
  const {
    href = "#",
  } = props;
  const classes = `button button-${variant}${className ? ` ${className}` : ""}`;

  return (
    <a className={classes} {...props} href={href}>
      {children}
    </a>
  );
}
