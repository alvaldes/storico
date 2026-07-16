import type { SVGProps } from "react";
import { OllamaDark } from "@/components/ui/svgs/ollamaDark";
import { OllamaLight } from "@/components/ui/svgs/ollamaLight";
import { Openai } from "@/components/ui/svgs/openai";
import { OpenaiDark } from "@/components/ui/svgs/openaiDark";
import { AnthropicWhite } from "@/components/ui/svgs/anthropicWhite";
import { AnthropicBlack } from "@/components/ui/svgs/anthropicBlack";

interface ProviderIconProps extends SVGProps<SVGSVGElement> {
  provider: string;
  theme: "light" | "dark";
}

export function ProviderIcon({ provider, theme, ...props }: ProviderIconProps) {
  const isDark = theme === "dark";

  switch (provider) {
    case "ollama":
      return isDark ? <OllamaDark {...props} /> : <OllamaLight {...props} />;
    case "openai":
      return isDark ? <OpenaiDark {...props} /> : <Openai {...props} />;
    case "anthropic":
      return isDark ? <AnthropicWhite {...props} /> : <AnthropicBlack {...props} />;
    default:
      return null;
  }
}
