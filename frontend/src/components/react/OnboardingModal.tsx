"use client"

import { useState, useRef } from "react"
import { Sparkles, Puzzle, Layers, XIcon } from "lucide-react"
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Progress } from "@/components/ui/progress"
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from "@/components/ui/select"
import { useAuthStore } from "@/stores/authStore"
import { completeOnboarding } from "@/lib/user-api"
import { useTranslations, type Locale } from "@/i18n/utils"

interface OnboardingModalProps {
  locale?: Locale
}

export function OnboardingModal({ locale = "en" }: OnboardingModalProps) {
  const t = useTranslations(locale)
  const tOnboarding = t.onboarding as Record<string, string> | undefined

  const { workspaceName, setOnboardingDone, setWorkspaceName } = useAuthStore()
  const [step, setStep] = useState(1)
  const [name, setName] = useState(workspaceName || "")
  const [provider, setProvider] = useState("ollama")
  const [open, setOpen] = useState(true)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const originalName = useRef(workspaceName || "")
  const isCompleting = useRef(false)

  const T = (key: string, fallback: string): string => {
    if (tOnboarding && typeof tOnboarding[key] === "string") {
      return tOnboarding[key] as string
    }
    return fallback
  }

  const handleSkip = async () => {
    if (isSubmitting) return
    setIsSubmitting(true)
    try {
      await completeOnboarding()
    } catch {
      // Silently fail — the user can still continue
    } finally {
      setOnboardingDone()
      setOpen(false)
      setIsSubmitting(false)
    }
  }

  const handleComplete = async () => {
    if (isSubmitting) return
    isCompleting.current = true
    setIsSubmitting(true)
    const shouldRename = name.trim() !== originalName.current.trim() && name.trim().length > 0
    try {
      await completeOnboarding(shouldRename ? name.trim() : undefined)
      if (shouldRename) {
        setWorkspaceName(name.trim())
      }
    } catch {
      // Silently fail — the user can still continue
    } finally {
      setOnboardingDone()
      setOpen(false)
      setIsSubmitting(false)
    }
  }

  const handleOpenChange = (isOpen: boolean) => {
    if (!isOpen && !isCompleting.current) {
      handleSkip()
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent
        showCloseButton={false}
        className="sm:max-w-lg"
        onInteractOutside={(e: Event) => e.preventDefault()}
      >
        {/* Header with close button */}
        <div className="flex items-start justify-between">
          <DialogTitle className="text-lg">
            {T("title", "Welcome to Storico")}
          </DialogTitle>
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={handleSkip}
            disabled={isSubmitting}
            aria-label="Close"
          >
            <XIcon className="h-4 w-4" />
          </Button>
        </div>

        {/* Progress bar */}
        <div className="space-y-1">
          <Progress value={(step / 3) * 100} />
          <p className="text-center text-xs text-muted-foreground">
            {T("step", "Step {step} of 3").replace(
              "{step}",
              String(step)
            )}
          </p>
        </div>

        {/* Step 1: Rename workspace */}
        {step === 1 && (
          <div className="space-y-3 py-2">
            <DialogDescription className="text-sm">
              {T(
                "step1_description",
                "Your workspace was automatically created. Give it a name that reflects your team or project."
              )}
            </DialogDescription>
            <div className="space-y-1.5">
              <Label htmlFor="workspace-name">
                {T("step1_title", "Name your workspace")}
              </Label>
              <Input
                id="workspace-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={T("step1_placeholder", "My Team's Workspace")}
              />
            </div>
          </div>
        )}

        {/* Step 2: Tutorial cards */}
        {step === 2 && (
          <div className="space-y-3 py-2">
            <DialogDescription className="text-sm">
              {T(
                "step2_description",
                "Here's a quick overview of what you can do with Storico."
              )}
            </DialogDescription>

            <div className="space-y-2">
              {/* Card 1 */}
              <div className="flex gap-3 rounded-lg border bg-(--color-surface) p-3">
                <Sparkles className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
                <div>
                  <p className="text-sm font-medium">
                    {T("step2_card1_title", "What is Storico?")}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {T(
                      "step2_card1_desc",
                      "Storico uses AI to break down user stories into structured Kanban tasks automatically."
                    )}
                  </p>
                </div>
              </div>

              {/* Card 2 */}
              <div className="flex gap-3 rounded-lg border bg-(--color-surface) p-3">
                <Puzzle className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
                <div>
                  <p className="text-sm font-medium">
                    {T("step2_card2_title", "How extraction works")}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {T(
                      "step2_card2_desc",
                      "Paste a user story, choose your LLM, and get technical tasks with descriptions and labels."
                    )}
                  </p>
                </div>
              </div>

              {/* Card 3 */}
              <div className="flex gap-3 rounded-lg border bg-(--color-surface) p-3">
                <Layers className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
                <div>
                  <p className="text-sm font-medium">
                    {T("step2_card3_title", "Workspaces")}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {T(
                      "step2_card3_desc",
                      "Organize projects and collaborate with your team in dedicated workspaces."
                    )}
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Step 3: Optional LLM config */}
        {step === 3 && (
          <div className="space-y-3 py-2">
            <DialogDescription className="text-sm">
              {T(
                "step3_description",
                "Choose your AI provider. You can change this later in Settings."
              )}
            </DialogDescription>

            <div className="space-y-1.5">
              <Label htmlFor="llm-provider">
                {T("step3_title", "Configure your LLM")}
              </Label>
              <Select value={provider} onValueChange={setProvider}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="ollama">
                    {T("llm_ollama", "Ollama (Local)")}
                  </SelectItem>
                  <SelectItem value="openai">
                    {T("llm_openai", "OpenAI")}
                  </SelectItem>
                  <SelectItem value="anthropic">
                    {T("llm_anthropic", "Anthropic")}
                  </SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                {T(
                  "step3_note",
                  "Ollama works out of the box with no API key."
                )}
              </p>
            </div>
          </div>
        )}

        {/* Footer */}
        <div className="flex items-center justify-between border-t pt-4">
          <Button
            variant="ghost"
            size="sm"
            onClick={handleSkip}
            disabled={isSubmitting}
          >
            {T("skip", "Skip")}
          </Button>

          {step < 3 ? (
            <Button size="sm" onClick={() => setStep(step + 1)}>
              {T("next", "Next")}
            </Button>
          ) : (
            <Button
              size="sm"
              onClick={handleComplete}
              disabled={isSubmitting}
            >
              {T("get_started", "Get Started")}
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
