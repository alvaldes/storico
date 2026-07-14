import { useEffect, useState, Fragment, type ReactNode } from "react";
import {
  Breadcrumb,
  BreadcrumbList,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { localizedPath, useTranslations, type Locale } from "@/i18n/utils";
import { useProjectStore } from "@/stores/projectStore";
import { useStoryStore } from "@/stores/storyStore";
import { getProject } from "@/lib/projects-api";
import { getStory } from "@/lib/stories-api";
import { House } from "lucide-react";
import { shortUUID, UUID_RE } from "@/lib/utils";

// Maps path segments to nav translation keys
const segmentLabelKey: Record<string, string> = {
  dashboard: "dashboard",
  stories: "stories",
  kanban: "kanban",
  export: "export",
  settings: "settings",
  projects: "projects",
};

interface BreadcrumbItem {
  label: string | ReactNode;
  href: string | null;
}

interface AutoBreadcrumbProps {
  locale: Locale;
  segments: string[];
}

function LoadingDots() {
  return (
    <span
      className="inline-flex text-muted-foreground/70"
      style={{
        width: "24px",
        aspectRatio: "2",
        background: [
          "no-repeat radial-gradient(circle closest-side,currentColor 90%,transparent) 0% 50%",
          "no-repeat radial-gradient(circle closest-side,currentColor 90%,transparent) 50% 50%",
          "no-repeat radial-gradient(circle closest-side,currentColor 90%,transparent) 100% 50%",
        ].join(","),
        backgroundSize: "calc(100%/3) 50%",
        animation: "loading-dots 1s infinite linear",
      }}
    />
  );
}

export function AutoBreadcrumb({ locale, segments }: AutoBreadcrumbProps) {
  const t = useTranslations(locale);
  const [resolvedLabels, setResolvedLabels] = useState<
    Record<string, string>
  >({});

  // UUIDs that failed all resolution attempts — fall back to shortUUID
  const [resolveErrors, setResolveErrors] = useState<
    Record<string, boolean>
  >({});

  /**
   * When the last URL segment is a story UUID (not a project UUID),
   * this stores the resolved project context so we can build a
   * contextual breadcrumb: Dashboard > Project Name > Story shortId
   * instead of Stories > Story shortId.
   */
  const [storyProject, setStoryProject] = useState<{
    projectId: string;
    projectName: string;
  } | null>(null);

  // Resolve UUID segments: first try as project, then as story context
  useEffect(() => {
    setStoryProject(null);
    setResolveErrors({});

    const uuidSegments = segments.filter((seg) => UUID_RE.test(seg));
    if (uuidSegments.length === 0) return;

    const projectStore = useProjectStore.getState();
    const storyStore = useStoryStore.getState();

    uuidSegments.forEach((id) => {
      const cachedProject = projectStore.getById(id);
      if (cachedProject) {
        setResolvedLabels((prev) => ({ ...prev, [id]: cachedProject.name }));
        return;
      }

      // Try as project first
      getProject(id)
        .then((project) => {
          setResolvedLabels((prev) => ({ ...prev, [id]: project.name }));
        })
        .catch(() => {
          // Not a project — try to resolve as story context
          // (only matters for the last segment, the current page)
          if (id !== segments[segments.length - 1]) {
            setResolveErrors((prev) => ({ ...prev, [id]: true }));
            return;
          }

          const cachedStory = storyStore.getById(id);
          if (cachedStory) {
            resolveStoryProject(cachedStory.projectId);
          } else {
            getStory(id)
              .then((story) => resolveStoryProject(story.projectId))
              .catch(() => {
                // Not a story either
                setResolveErrors((prev) => ({ ...prev, [id]: true }));
              });
          }
        });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [segments]);

  function resolveStoryProject(projectId: string) {
    const projectStore = useProjectStore.getState();
    const cached = projectStore.getById(projectId);
    if (cached) {
      setStoryProject({ projectId, projectName: cached.name });
    } else {
      getProject(projectId)
        .then((p) => setStoryProject({ projectId, projectName: p.name }))
        .catch(() => {
          setResolveErrors((prev) => ({ ...prev, [projectId]: true }));
        });
    }
  }

  // Resolve a segment label: known key, resolved name, loading dots, or short UUID
  function segmentLabel(seg: string): string | ReactNode {
    const labelKey = segmentLabelKey[seg];
    if (labelKey) return t.nav[labelKey as keyof typeof t.nav];
    if (resolvedLabels[seg]) return resolvedLabels[seg];
    // Show loading dots for any unresolved UUID that hasn't failed yet
    if (UUID_RE.test(seg) && !resolveErrors[seg]) return <LoadingDots />;
    return shortUUID(seg);
  }

  // Build breadcrumb trail — use contextual path when story project is known
  function buildItems(): BreadcrumbItem[] {
    const lastSeg = segments[segments.length - 1];

    // Detect story detail page synchronously from URL pattern: /stories/:uuid
    const isStoryDetail =
      segments.length >= 2 &&
      segments[segments.length - 2] === "stories" &&
      UUID_RE.test(lastSeg);

    if (isStoryDetail) {
      return [
        {
          label: t.nav.dashboard,
          href: localizedPath("/dashboard", locale),
        },
        {
          label: storyProject?.projectName ?? <LoadingDots />,
          href: storyProject
            ? localizedPath(`/projects/${storyProject.projectId}`, locale)
            : null,
        },
        { label: shortUUID(lastSeg), href: null },
      ];
    }

    // Default: URL-based breadcrumb
    return segments.map((seg, i) => {
      const href = localizedPath(
        "/" + segments.slice(0, i + 1).join("/"),
        locale,
      );
      return {
        label: segmentLabel(seg),
        href: i === segments.length - 1 ? null : href,
      };
    });
  }

  const items = buildItems();

  // FUTURE: If breadcrumbs get deeper (5+ items), use <BreadcrumbEllipsis />
  // from @/components/ui/breadcrumb to collapse middle items.
  // Example: Storico > Dashboard > ··· > a1b2c3d4
  return (
    <Breadcrumb>
      <BreadcrumbList>
        <BreadcrumbItem>
          <BreadcrumbLink
            href={localizedPath("/dashboard", locale)}
            aria-label={t.nav.dashboard}
          >
            <House className="h-4 w-4" />
          </BreadcrumbLink>
        </BreadcrumbItem>

        {items.map((item) => (
          <Fragment
            key={
              item.href ??
              (typeof item.label === "string" ? item.label : "\u2026")
            }
          >
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
  );
}
