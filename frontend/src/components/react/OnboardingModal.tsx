"use client"

import { useState, useRef, useEffect } from "react"
import { Sparkles, Puzzle, Layers } from "lucide-react"
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

  const { workspaceName, setOnboardingDone, setWorkspaceName } = useAuthStore()
  const [step, setStep] = useState(1)
  const [name, setName] = useState(workspaceName || "")
  const [provider, setProvider] = useState("ollama")
  const [open, setOpen] = useState(true)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const originalName = useRef(workspaceName || "")

  // Bloquear Escape a nivel DOM antes de que Base UI lo procese.
  // Base UI usa un listener en document para cerrar con Escape, y su
  // mecanismo de cancel() no siempre frena el cierre interno del store.
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault()
        e.stopImmediatePropagation()
      }
    }
    document.addEventListener("keydown", handler, { capture: true })
    return () => document.removeEventListener("keydown", handler, { capture: true })
  }, [open])

  // Focus management: al cambiar de step, mover el foco al elemento
  // donde el usuario debe prestar atención primero.
  useEffect(() => {
    // requestAnimationFrame asegura que el DOM ya se actualizó
    // después del render condicional.
    const raf = requestAnimationFrame(() => {
      if (step === 1) {
        document.getElementById("workspace-name")?.focus()
      } else if (step === 2) {
        document.getElementById("onboarding-next")?.focus()
      } else if (step === 3) {
        document.getElementById("llm-provider-trigger")?.focus()
      }
    })
    return () => cancelAnimationFrame(raf)
  }, [step])

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

  // No-op: el diálogo solo se cierra desde Skip o Complete.
  // Escape se bloquea a nivel DOM en el useEffect de arriba.
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const handleOpenChange = (_isOpen: boolean) => {}

  return (
    <Dialog open={open} onOpenChange={handleOpenChange} disablePointerDismissal>
      <DialogContent
        showCloseButton={false}
        className="sm:max-w-lg"
      >
        {/* Header — sin botón X, solo se puede salir con Skip o completando */}
        <DialogTitle className="text-lg">
          {t.onboarding.title}
        </DialogTitle>

        {/* Progress bar */}
        <div className="space-y-1">
          <Progress value={(step / 3) * 100} />
          <p className="text-center text-xs text-muted-foreground">
            {t.onboarding.step.replace("{step}", String(step))}
          </p>
        </div>

        {/* Step 1: Rename workspace */}
        {step === 1 && (
          <div className="space-y-3 py-2 min-h-[310px]">
            <DialogDescription className="text-sm">
              {t.onboarding.step1_description}
            </DialogDescription>
            <div className="space-y-1.5">
              <Label htmlFor="workspace-name">
                {t.onboarding.step1_title}
              </Label>
              <Input
                id="workspace-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t.onboarding.step1_placeholder}
                maxLength={100}
                autoFocus
              />
              <div className="flex justify-end text-xs">
                <span className="text-muted-foreground">{name.length}/100</span>
              </div>
            </div>
          </div>
        )}

        {/* Step 2: Tutorial cards */}
        {step === 2 && (
          <div className="space-y-3 py-2 min-h-[310px]">
            <DialogDescription className="text-sm">
              {t.onboarding.step2_description}
            </DialogDescription>

            <div className="space-y-2">
              {/* Card 1 */}
              <div className="flex gap-3 rounded-lg border bg-(--color-surface) p-3">
                <Sparkles className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
                <div>
                  <p className="text-sm font-medium">
                    {t.onboarding.step2_card1_title}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {t.onboarding.step2_card1_desc}
                  </p>
                </div>
              </div>

              {/* Card 2 */}
              <div className="flex gap-3 rounded-lg border bg-(--color-surface) p-3">
                <Puzzle className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
                <div>
                  <p className="text-sm font-medium">
                    {t.onboarding.step2_card2_title}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {t.onboarding.step2_card2_desc}
                  </p>
                </div>
              </div>

              {/* Card 3 */}
              <div className="flex gap-3 rounded-lg border bg-(--color-surface) p-3">
                <Layers className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
                <div>
                  <p className="text-sm font-medium">
                    {t.onboarding.step2_card3_title}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {t.onboarding.step2_card3_desc}
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Step 3: Optional LLM config */}
        {step === 3 && (
          <div className="space-y-3 py-2 min-h-[310px]">
            <DialogDescription className="text-sm">
              {t.onboarding.step3_description}
            </DialogDescription>

            <div className="space-y-1.5">
              <Label htmlFor="llm-provider">
                {t.onboarding.step3_title}
              </Label>
              <Select value={provider} onValueChange={(val) => { if (val !== null) setProvider(val); }}>
                <SelectTrigger id="llm-provider-trigger" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="ollama">
                    {t.onboarding.llm_ollama}
                  </SelectItem>
                  <SelectItem value="openai">
                    {t.onboarding.llm_openai}
                  </SelectItem>
                  <SelectItem value="anthropic">
                    {t.onboarding.llm_anthropic}
                  </SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                {t.onboarding.step3_note}
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
            {t.onboarding.skip}
          </Button>

          <div className="flex items-center gap-2">
            {step > 1 && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setStep(step - 1)}
              >
                {t.onboarding.back}
              </Button>
            )}

            {step < 3 ? (
              <Button id="onboarding-next" size="sm" onClick={() => setStep(step + 1)}>
                {t.onboarding.next}
              </Button>
            ) : (
              <Button
                id="onboarding-next"
                size="sm"
                onClick={handleComplete}
                disabled={isSubmitting}
              >
                {t.onboarding.get_started}
              </Button>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
