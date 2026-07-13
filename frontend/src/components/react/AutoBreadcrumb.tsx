import { useEffect, useState, Fragment, type ReactNode } from 'react'
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
import { useStoryStore } from '@/stores/storyStore'
import { getProject } from '@/lib/projects-api'
import { getStory } from '@/lib/stories-api'
import { shortUUID, UUID_RE } from '@/lib/utils'

// Maps path segments to nav translation keys
const segmentLabelKey: Record<string, string> = {
  dashboard: 'dashboard',
  stories: 'stories',
  kanban: 'kanban',
  export: 'export',
  settings: 'settings',
  projects: 'projects',
}

interface BreadcrumbItem {
  label: string | ReactNode
  href: string | null
}

interface AutoBreadcrumbProps {
  locale: Locale
  segments: string[]
}

/** Subtle loading indicator for unresolved breadcrumb segments. */
function LoadingDots() {
  return (
    <span className="inline-flex animate-pulse tracking-[0.15em]">
      ...
    </span>
  )
}

export function AutoBreadcrumb({ locale, segments }: AutoBreadcrumbProps) {
  const t = useTranslations(locale)
  const [resolvedLabels, setResolvedLabels] = useState<Record<string, string>>({})
  const [resolving, setResolving] = useState<Record<string, boolean>>({})

  /**
   * When the last URL segment is a story UUID (not a project UUID),
   * this stores the resolved project context so we can build a
   * contextual breadcrumb: Dashboard > Project Name > Story shortId
   * instead of Stories > Story shortId.
   */
  const [storyProject, setStoryProject] = useState<{
    projectId: string
    projectName: string
  } | null>(null)

  // Resolve UUID segments: first try as project, then as story context
  useEffect(() => {
    setStoryProject(null)

    const uuidSegments = segments.filter((seg) => UUID_RE.test(seg))
    if (uuidSegments.length === 0) return

    const projectStore = useProjectStore.getState()
    const storyStore = useStoryStore.getState()

    uuidSegments.forEach((id) => {
      const cachedProject = projectStore.getById(id)
      if (cachedProject) {
        setResolvedLabels((prev) => ({ ...prev, [id]: cachedProject.name }))
        return
      }

      // Mark as resolving
      setResolving((prev) => ({ ...prev, [id]: true }))

      // Try as project first
      getProject(id)
        .then((project) => {
          setResolvedLabels((prev) => ({ ...prev, [id]: project.name }))
        })
        .catch(() => {
          // Not a project — try to resolve as story context
          // (only matters for the last segment, the current page)
          if (id !== segments[segments.length - 1]) return

          const cachedStory = storyStore.getById(id)
          if (cachedStory) {
            resolveStoryProject(cachedStory.projectId)
          } else {
            getStory(id)
              .then((story) => resolveStoryProject(story.projectId))
              .catch(() => {
                /* Not a story either — leave as-is */
              })
          }
        })
        .finally(() => {
          setResolving((prev) => ({ ...prev, [id]: false }))
        })
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [segments])

  function resolveStoryProject(projectId: string) {
    setResolving((prev) => ({ ...prev, [projectId]: true }))

    const projectStore = useProjectStore.getState()
    const cached = projectStore.getById(projectId)
    if (cached) {
      setStoryProject({ projectId, projectName: cached.name })
      setResolving((prev) => ({ ...prev, [projectId]: false }))
    } else {
      getProject(projectId)
        .then((p) => setStoryProject({ projectId, projectName: p.name }))
        .catch(() => {
          /* Project not found */
        })
        .finally(() => {
          setResolving((prev) => ({ ...prev, [projectId]: false }))
        })
    }
  }

  // Resolve a segment label: known key, resolved name, loading dots, or short UUID
  function segmentLabel(seg: string): string | ReactNode {
    const labelKey = segmentLabelKey[seg]
    if (labelKey) return t.nav[labelKey as keyof typeof t.nav]
    if (resolvedLabels[seg]) return resolvedLabels[seg]
    if (resolving[seg]) return <LoadingDots />
    return shortUUID(seg)
  }

  // Build breadcrumb trail — use contextual path when story project is known
  function buildItems(): BreadcrumbItem[] {
    const lastSeg = segments[segments.length - 1]

    if (storyProject && lastSeg && UUID_RE.test(lastSeg) && !resolvedLabels[lastSeg]) {
      // Contextual: Dashboard > Project Name > Story shortId
      return [
        {
          label: t.nav.dashboard,
          href: localizedPath('/dashboard', locale),
        },
        {
          label: storyProject.projectName,
          href: localizedPath(`/projects/${storyProject.projectId}`, locale),
        },
        { label: shortUUID(lastSeg), href: null },
      ]
    }

    // Default: URL-based breadcrumb
    return segments.map((seg, i) => {
      const href = localizedPath(
        '/' + segments.slice(0, i + 1).join('/'),
        locale,
      )
      return { label: segmentLabel(seg), href: i === segments.length - 1 ? null : href }
    })
  }

  const items = buildItems()

  return (
    <Breadcrumb>
      <BreadcrumbList>
        <BreadcrumbItem>
          <BreadcrumbLink href={localizedPath('/', locale)}>
            {t.app.name}
          </BreadcrumbLink>
        </BreadcrumbItem>

        {items.map((item) => (
          <Fragment key={item.href ?? item.label}>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              {item.href ? (
                <BreadcrumbLink href={item.href}>{item.label}</BreadcrumbLink>
              ) : (
                <BreadcrumbPage>{item.label}</BreadcrumbPage>
              )}
            </BreadcrumbItem>
          </Fragment>
        ))}
      </BreadcrumbList>
    </Breadcrumb>
  )
}
