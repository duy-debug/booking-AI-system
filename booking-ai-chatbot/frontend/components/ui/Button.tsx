import type { AnchorHTMLAttributes, ButtonHTMLAttributes, ReactNode } from "react";

type ButtonVariant = "primary" | "secondary" | "ghost";

interface CommonProps {
  children: ReactNode;
  className?: string;
  variant?: ButtonVariant;
}

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
