import type { ButtonHTMLAttributes, ReactNode } from "react";

type ButtonVariant = "primary" | "secondary" | "danger" | "ghost";
type ButtonSize = "sm" | "md" | "icon";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  children: ReactNode;
}

const variantClass: Record<ButtonVariant, string> = {
  primary: "bg-[#2a8587] text-white hover:bg-[#246f71]",
  secondary:
    "border border-[#dfe6f1] bg-white text-[#4d5874] hover:border-[#2f9b9d] hover:text-[#2a8587]",
  danger:
    "border border-[#e06666] bg-white text-[#e06666] hover:bg-[#fcefef]",
  ghost: "text-[#4d5874] hover:bg-[#f5f7f9] hover:text-[#2a8587]",
};

const sizeClass: Record<ButtonSize, string> = {
  sm: "h-9 px-3 text-sm",
  md: "h-10 px-4 text-sm",
  icon: "h-9 w-9 p-0",
};

export function Button({
  variant = "secondary",
  size = "md",
  className = "",
  children,
  type = "button",
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      className={[
        "inline-flex items-center justify-center gap-2 rounded-lg font-extrabold transition disabled:cursor-not-allowed disabled:opacity-60",
        variantClass[variant],
        sizeClass[size],
        className,
      ].join(" ")}
      {...props}
    >
      {children}
    </button>
  );
}
