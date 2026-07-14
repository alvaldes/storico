import { useState } from "react";

interface UserAvatarProps {
  src: string | null | undefined;
  name: string;
  size?: "sm" | "md" | "lg";
  className?: string;
  /** Override default fallback background/text/ring styles. */
  fallbackClass?: string;
}

const sizeMap = {
  sm: { container: "h-8 w-8 text-sm", icon: "h-8 w-8" },
  md: { container: "h-10 w-10 text-base", icon: "h-10 w-10" },
  lg: { container: "h-12 w-12 text-lg", icon: "h-12 w-12" },
};

const DEFAULT_FALLBACK =
  "bg-(--color-primary-500)/10 text-(--color-primary-600)";

export function UserAvatar({
  src,
  name,
  size = "md",
  className = "",
  fallbackClass,
}: UserAvatarProps) {
  const [failed, setFailed] = useState(false);
  const initial = name?.charAt(0)?.toUpperCase() || "?";

  if (src && !failed) {
    return (
      <img
        src={src}
        alt={name}
        onError={() => setFailed(true)}
        className={`${sizeMap[size].icon} shrink-0 rounded-full object-cover ring-2 ring-(--color-border) ${className}`}
      />
    );
  }

  return (
    <div
      className={`flex ${sizeMap[size].container} shrink-0 items-center justify-center rounded-full font-semibold ${fallbackClass ?? DEFAULT_FALLBACK} ${className}`}
    >
      {initial}
    </div>
  );
}
