import type { SVGProps } from "react";

export function Gemini(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}>
      <path
        d="M8 0C9.6 4.8 11.2 6.4 16 8c-4.8 1.6-6.4 3.2-8 8-1.6-4.8-3.2-6.4-8-8 4.8-1.6 6.4-3.2 8-8z"
        fill="url(#geminiGradient)"
      />
      <defs>
        <linearGradient id="geminiGradient" x1="0" y1="0" x2="16" y2="16" gradientUnits="userSpaceOnUse">
          <stop stopColor="#4285F4" />
          <stop offset="1" stopColor="#9B72CB" />
        </linearGradient>
      </defs>
    </svg>
  );
}
