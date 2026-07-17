import { useState, useEffect } from "react";
import {
  User,
  Palette,
  Download,
  Info,
  TriangleAlert,
  LoaderCircle,
  ExternalLink,
  BookOpen,
  Activity,
  Code,
  Sun,
  Moon,
  Monitor,
} from "lucide-react";
import { useTranslations, type Locale, localizedPath } from "@/i18n/utils";
import { useSettingsStore } from "@/stores/settingsStore";
import { useAuthStore } from "@/stores/authStore";
import { useUIStore } from "@/stores/uiStore";
import { UserAvatar } from "@/components/react/UserAvatar";
import { DeleteAccountDialog } from "@/components/react/DeleteAccountDialog";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from "@/components/ui/select";
import { Field, FieldLabel, FieldDescription } from "@/components/ui/field";
import { SegmentedControl } from "@/components/react/SegmentedControl";
import { GithubLight } from "@/components/ui/svgs/githubLight";
import { GithubDark } from "@/components/ui/svgs/githubDark";
import type { ExportFormat } from "@/types/settings";
import pkg from "../../../package.json";

/* ── Provider detection ────────────────────────────────────────── */

function formatProvider(user: { email: string; authProvider?: string }): string {
  if (user.authProvider) {
    return user.authProvider.charAt(0).toUpperCase() + user.authProvider.slice(1)
  }
  // Fallback when backend hasn't stored authProvider yet
  const email = user.email.toLowerCase()
  if (email.endsWith("@gmail.com") || email.includes("google")) return "Google"
  if (email.includes("github")) return "GitHub"
  return "OAuth"
}

/* ── Main Account Page Component ────────────────────────────── */

interface AccountPageProps {
  locale: Locale;
}

export function AccountPage({ locale }: AccountPageProps) {
  const t = useTranslations(locale);
  const {
    settings,
    setExportFormat,
    loadFromApi,
  } = useSettingsStore();
  const { user, loading: authLoading } = useAuthStore();
  const { theme, setTheme } = useUIStore();
  const [mounted, setMounted] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);

  useEffect(() => {
    setMounted(true);
    loadFromApi();
  }, [loadFromApi]);

  if (!mounted) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-(--color-border) border-t-(--color-primary-500)" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl space-y-8 pb-12">
      {/* ── Page Header ── */}
      <div>
        <h1 className="text-2xl font-semibold text-(--color-text)">
          {t.account.page_title}
        </h1>
        <p className="mt-1 text-sm text-(--color-text-secondary)">
          {t.account.page_description}
        </p>
      </div>

      {/* ── Profile ── */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <User className="h-4 w-4 text-(--color-text-secondary)" />
            <CardTitle>{t.settings.profile_title}</CardTitle>
          </div>
          <CardDescription>{t.settings.profile_description}</CardDescription>
        </CardHeader>
        <CardContent>
          {authLoading ? (
            <div className="flex items-center gap-2 text-sm text-(--color-text-secondary)">
              <LoaderCircle className="h-4 w-4 animate-spin" />
              {t.common.loading}
            </div>
          ) : user ? (
            <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
              <UserAvatar src={user.avatar_url} name={user.name} size="lg" />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-(--color-text)">
                  {user.name}
                </p>
                <p className="text-sm text-(--color-text-secondary)">
                  {user.email}
                </p>
              </div>
              <Badge variant="outline" className="w-full text-xs sm:w-auto">
                {t.settings.profile_signed_in_with}{" "}
                {formatProvider(user)}
              </Badge>
            </div>
          ) : (
            <p className="text-sm text-(--color-text-secondary)">
              {t.settings.profile_not_signed_in}
            </p>
          )}
        </CardContent>
      </Card>

      {/* ── Appearance ── */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Palette className="h-4 w-4 text-(--color-text-secondary)" />
            <CardTitle>{t.settings.appearance_title}</CardTitle>
          </div>
          <CardDescription>{t.settings.appearance_description}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          {/* Theme */}
          <Field>
            <FieldLabel>{t.settings.appearance_theme}</FieldLabel>
            <SegmentedControl
              value={theme}
              onValueChange={(value) => {
                setTheme(value as "light" | "dark" | "system")
              }}
              options={[
                { value: "light", label: <><Sun className="h-4 w-4" /> {t.settings.appearance_theme_light}</> },
                { value: "dark", label: <><Moon className="h-4 w-4" /> {t.settings.appearance_theme_dark}</> },
                { value: "system", label: <><Monitor className="h-4 w-4" /> {t.settings.appearance_theme_system}</> },
              ]}
            />
          </Field>

          {/* Language */}
          <Field>
            <FieldLabel>{t.settings.appearance_language}</FieldLabel>
            <SegmentedControl
              value={locale}
              onValueChange={(value) => {
                if (value !== locale) {
                  window.location.href = localizedPath("/account", value as "en" | "es")
                }
              }}
              options={[
                { value: "en", label: <>🇺🇸 {t.settings.appearance_language_en}</> },
                { value: "es", label: <>🇪🇸 {t.settings.appearance_language_es}</> },
              ]}
            />
          </Field>
        </CardContent>
      </Card>

      {/* ── Export Defaults ── */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Download className="h-4 w-4 text-(--color-text-secondary)" />
            <CardTitle>{t.settings.export_title}</CardTitle>
          </div>
          <CardDescription>{t.settings.export_description}</CardDescription>
        </CardHeader>
        <CardContent>
          <Field>
            <FieldLabel htmlFor="export-format">
              {t.settings.export_format}
            </FieldLabel>
            <Select
              value={settings.export.defaultFormat}
              onValueChange={(value) => setExportFormat(value as ExportFormat)}
            >
              <SelectTrigger id="export-format" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="trello">{t.settings.export_format_trello}</SelectItem>
                <SelectItem value="json">{t.settings.export_format_json}</SelectItem>
                <SelectItem value="markdown">
                  {t.settings.export_format_markdown}
                </SelectItem>
              </SelectContent>
            </Select>
          </Field>
        </CardContent>
      </Card>

      {/* ── About ── */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Info className="h-4 w-4 text-(--color-text-secondary)" />
            <CardTitle>{t.settings.about_title}</CardTitle>
          </div>
          <CardDescription>{t.settings.about_description}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <span className="text-sm text-(--color-text-secondary)">
              {t.settings.about_version}:
            </span>{" "}
            <span className="text-sm font-medium text-(--color-text)">
              v{pkg.version}
            </span>
          </div>
          <div>
            <p className="mb-1.5 text-sm font-medium text-(--color-text)">
              {t.settings.about_links}
            </p>
            <div className="flex flex-wrap gap-2">
              <a
                href={localizedPath("/docs", locale)}
                className="inline-flex items-center gap-1.5 rounded-lg border border-(--color-border) px-3 py-1.5 text-sm text-(--color-text-secondary) transition-colors hover:border-(--color-primary-300) hover:text-(--color-text)"
              >
                <BookOpen className="h-3.5 w-3.5" />
                {t.settings.about_docs}
                <ExternalLink className="h-3 w-3" />
              </a>
              <a
                href={localizedPath("/api", locale)}
                className="inline-flex items-center gap-1.5 rounded-lg border border-(--color-border) px-3 py-1.5 text-sm text-(--color-text-secondary) transition-colors hover:border-(--color-primary-300) hover:text-(--color-text)"
              >
                <Code className="h-3.5 w-3.5" />
                {t.settings.about_api}
                <ExternalLink className="h-3 w-3" />
              </a>
              <a
                href={localizedPath("/status", locale)}
                className="inline-flex items-center gap-1.5 rounded-lg border border-(--color-border) px-3 py-1.5 text-sm text-(--color-text-secondary) transition-colors hover:border-(--color-primary-300) hover:text-(--color-text)"
              >
                <Activity className="h-3.5 w-3.5" />
                {t.settings.about_status}
                <ExternalLink className="h-3 w-3" />
              </a>
              <a
                href="https://github.com/alvaldes/storico"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 rounded-lg border border-(--color-border) px-3 py-1.5 text-sm text-(--color-text-secondary) transition-colors hover:border-(--color-primary-300) hover:text-(--color-text)"
              >
                <>
                  <span className="block dark:hidden"><GithubLight className="h-3.5 w-3.5" /></span>
                  <span className="hidden dark:block"><GithubDark className="h-3.5 w-3.5" /></span>
                </>
                GitHub
                <ExternalLink className="h-3 w-3" />
              </a>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* ── Danger Zone ── */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <TriangleAlert className="h-4 w-4 text-red-500" />
            <CardTitle className="text-red-600">
              {t.settings.danger_title}
            </CardTitle>
          </div>
          <CardDescription>{t.settings.danger_description}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="rounded-lg border border-red-200 bg-red-50 p-4 dark:border-red-900 dark:bg-red-950/30">
            <p className="text-sm font-medium text-red-800 dark:text-red-200">
              {t.settings.danger_delete_account}
            </p>
            <p className="mt-1 text-sm text-red-600 dark:text-red-300">
              {t.settings.danger_delete_description}
            </p>
            <Button
              variant="outline"
              onClick={() => setDeleteDialogOpen(true)}
              className="mt-3 cursor-pointer border-red-300 text-red-600 hover:bg-red-100 hover:text-red-700 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-900/50 dark:hover:text-red-300"
            >
              {t.settings.danger_delete_account}
            </Button>
          </div>
        </CardContent>
      </Card>

      <DeleteAccountDialog
        locale={locale}
        open={deleteDialogOpen}
        onOpenChange={setDeleteDialogOpen}
      />
    </div>
  );
}
