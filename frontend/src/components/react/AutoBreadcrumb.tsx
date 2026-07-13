import {
  Breadcrumb,
  BreadcrumbList,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb'
import { localizedPath, useTranslations, type Locale } from '@/i18n/utils'

// Maps path segments to nav translation keys
const segmentLabelKey: Record<string, string> = {
  dashboard: 'dashboard',
  stories: 'stories',
  kanban: 'kanban',
  export: 'export',
  settings: 'settings',
}

interface AutoBreadcrumbProps {
  locale: Locale
  segments: string[]
}

export function AutoBreadcrumb({ locale, segments }: AutoBreadcrumbProps) {
  const t = useTranslations(locale)

  return (
    <Breadcrumb>
      <BreadcrumbList>
        <BreadcrumbItem>
          <BreadcrumbLink href={localizedPath('/', locale)}>
            {t.app.name}
          </BreadcrumbLink>
        </BreadcrumbItem>

        {segments.map((seg, i) => {
          const labelKey = segmentLabelKey[seg]
          const label = labelKey ? t.nav[labelKey as keyof typeof t.nav] : seg
          const href = localizedPath(
            '/' + segments.slice(0, i + 1).join('/'),
            locale,
          )
          const isLast = i === segments.length - 1

          return (
            <>
              <BreadcrumbSeparator key={`sep-${i}`} />
              <BreadcrumbItem key={`item-${i}`}>
                {isLast ? (
                  <BreadcrumbPage>{label}</BreadcrumbPage>
                ) : (
                  <BreadcrumbLink href={href}>{label}</BreadcrumbLink>
                )}
              </BreadcrumbItem>
            </>
          )
        })}
      </BreadcrumbList>
    </Breadcrumb>
  )
}
