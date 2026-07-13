import { useEffect, useState, Fragment } from 'react'
import {
  Breadcrumb,
  BreadcrumbList,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb'
import { localizedPath, useTranslations, type Locale } from '@/i18n/utils'
import { useProjectStore } from '@/stores/projectStore'
import { getProject } from '@/lib/projects-api'

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

// Maps path segments to nav translation keys
const segmentLabelKey: Record<string, string> = {
  dashboard: 'dashboard',
  stories: 'stories',
  kanban: 'kanban',
  export: 'export',
  settings: 'settings',
  projects: 'projects',
}

interface AutoBreadcrumbProps {
  locale: Locale
  segments: string[]
}

export function AutoBreadcrumb({ locale, segments }: AutoBreadcrumbProps) {
  const t = useTranslations(locale)
  const [resolvedLabels, setResolvedLabels] = useState<Record<string, string>>(
    {},
  )

  // Resolve UUID segments to project titles
  useEffect(() => {
    const uuidSegments = segments.filter((seg) => UUID_RE.test(seg))
    if (uuidSegments.length === 0) return

    const store = useProjectStore.getState()

    uuidSegments.forEach((id) => {
      const cached = store.getById(id)
      if (cached) {
        setResolvedLabels((prev) => ({ ...prev, [id]: cached.name }))
        return
      }

      // Fetch from API if not in cache
      getProject(id).then((project) => {
        setResolvedLabels((prev) => ({ ...prev, [id]: project.name }))
      }).catch(() => {
        // Silently fail — keep showing the UUID
      })
    })
  }, [segments])

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
          const label = labelKey
            ? t.nav[labelKey as keyof typeof t.nav]
            : (resolvedLabels[seg] ?? (UUID_RE.test(seg) ? seg.slice(0, 8) : seg))
          const href = localizedPath(
            '/' + segments.slice(0, i + 1).join('/'),
            locale,
          )
          const isLast = i === segments.length - 1

          return (
            <Fragment key={seg}>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                {isLast ? (
                  <BreadcrumbPage>{label}</BreadcrumbPage>
                ) : (
                  <BreadcrumbLink href={href}>{label}</BreadcrumbLink>
                )}
              </BreadcrumbItem>
            </Fragment>
          )
        })}
      </BreadcrumbList>
    </Breadcrumb>
  )
}
