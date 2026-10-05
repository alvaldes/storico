import { useEffect, useState } from 'react';
import { useTranslations, type Locale } from '@/i18n/utils';
import { serviceStatus, summarizeHealth, type ServiceStatus } from '@/lib/health';
import { fetchServiceHealth, type HealthOutcome } from '@/lib/status-health-api';

// The probe names the banner rule evaluates: the five the backend publishes. The `api` row
// is synthetic — it reports the outcome of the health call itself, not a probe — and is
// never a probe. (`status-probes-mirror.test.ts` pins this literal to the backend source.)
const DIAGNOSTIC_PROBES = ['database', 'schema', 'ollama', 'qdrant', 'embeddings'] as const;

/**
 * Four states, not two. "Unavailable" means the backend did not report the probe;
 * "Error" means it probed and failed; "Unknown" is the backend's own degraded answer when it
 * could not determine a status at all (the schema probe publishes it). Collapsing the first
 * into the second would claim a measurement nobody took — and a missing probe is exactly when
 * this page matters most.
 *
 * While the fetch is in flight none of these states is shown: the badge slot renders a
 * pending loader instead (see `renderBadge`), so no state here ever lies about being settled.
 */
type BadgeState = 'ok' | 'error' | 'unknown' | 'unavailable';

const badgeState = (probe: ServiceStatus | null): BadgeState => {
  if (!probe) return 'unavailable';
  return probe.status;
};

const badgeDotClass = (state: BadgeState) => {
  if (state === 'ok') return 'bg-(--color-success)';
  if (state === 'unknown') return 'bg-amber-500';
  return 'bg-red-500';
};

const badgeTextClass = (state: BadgeState) => {
  if (state === 'ok') return 'text-(--color-success-text)';
  if (state === 'unknown') return 'text-amber-800 dark:text-amber-300';
  return 'text-red-600 dark:text-red-400';
};

const bannerBgClass = (state: string) => {
  if (state === 'ok') return 'bg-(--color-success-bg) border-(--color-success-border)';
  if (state === 'degraded')
    return 'bg-amber-50 border-amber-200 dark:bg-amber-950/40 dark:border-amber-800';
  if (state === 'pending') return 'border-(--color-border)';
  return 'bg-red-50 border-red-200 dark:bg-red-950/40 dark:border-red-800';
};

const bannerDotClass = (state: string) => {
  if (state === 'ok') return 'bg-(--color-success)';
  if (state === 'degraded') return 'bg-amber-500';
  if (state === 'pending') return 'bg-(--color-text-tertiary)';
  return 'bg-red-500';
};

const bannerTextClass = (state: string) => {
  if (state === 'ok') return 'text-(--color-success-text)';
  if (state === 'degraded') return 'text-amber-800 dark:text-amber-300';
  if (state === 'pending') return 'text-(--color-text-secondary)';
  return 'text-red-800 dark:text-red-300';
};

export function StatusPanel({ locale }: { locale: Locale }) {
  const t = useTranslations(locale);

  const [outcome, setOutcome] = useState<HealthOutcome | null>(null);
  const [pending, setPending] = useState(true);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    fetchServiceHealth().then((result) => {
      if (cancelled) return;
      setOutcome(result);
      setPending(false);
    });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const retry = () => {
    // Back to the pending state immediately, synchronously with the click: the loaders
    // reappear before the new request resolves, and the effect refires on `attempt`.
    setPending(true);
    setAttempt((n) => n + 1);
  };

  // Only an `ok` outcome carries a verified services document; every other kind becomes
  // `null` here, and the rows below fall back to "Unavailable". That keeps the existing
  // rule intact: a probe the backend did not report is never a synthetic `error` — the
  // absence is rendered as "Unavailable", a measured failure as "Error".
  const health = outcome?.kind === 'ok' ? outcome.health : null;

  // The banner is derived here, from the core probes only — not read off `health.status`, which
  // is the backend's own answer about its required probes (and which before commit `b90ded2` was
  // degraded by any probe). One pure, tested rule keeps the page and the backend from
  // disagreeing: `summarizeHealth` in `@/lib/health`. While pending there is no verdict yet,
  // so the banner renders a neutral pending style with the same layout.
  const summary = summarizeHealth(health, DIAGNOSTIC_PROBES);
  const bannerState = pending ? 'pending' : summary.banner;

  let bannerTitle: string;
  let bannerDesc: string;
  if (pending) {
    bannerTitle = t.pages.status.checking;
    bannerDesc = t.pages.status.description;
  } else if (!health) {
    bannerTitle = t.pages.status.down_title;
    // Where the old SSR page appended the raw `fetchError` message, the client design only
    // knows outcome kinds; the one honest short reason it can state is the HTTP status that
    // answered. Everything else stays as the plain "unreachable" copy.
    bannerDesc =
      outcome?.kind === 'http-error'
        ? `${t.pages.status.down_desc} (HTTP ${outcome.status})`
        : t.pages.status.down_desc;
  } else if (bannerState === 'ok') {
    bannerTitle = t.pages.status.all_operational;
    bannerDesc = t.pages.status.running_normally;
  } else {
    bannerTitle = t.pages.status.degraded_title;
    bannerDesc = t.pages.status.degraded_desc;
  }

  // Decision D2, "OK con avisos": when the core is healthy but an optional integration is not,
  // the banner stays green and this note names what is unavailable, using the same translated
  // row titles the table below renders. An unknown probe name falls back to the raw name
  // instead of disappearing from the note.
  const optionalTitle = (name: string): string => {
    const titles: Record<string, string> = {
      ollama: t.pages.status.llm_runner,
      qdrant: t.pages.status.vector_store,
      embeddings: t.pages.status.embeddings,
    };
    return titles[name] ?? name;
  };
  const optionalNote = summary.degradedOptional.map(optionalTitle).join(', ');

  // The translated label for a settled badge, mirroring the four states above.
  const badgeLabel = (state: BadgeState) => {
    if (state === 'ok') return t.pages.status.operational;
    if (state === 'error') return t.pages.status.error;
    if (state === 'unknown') return t.pages.status.unknown;
    return t.pages.status.unavailable;
  };

  /**
   * `api` row semantics, changed by the client-fetch design and deliberately so: the page
   * can no longer prove the API by "the document arrived", because the document now arrives
   * from the same-origin endpoint before (or without) the backend probes. The row is derived
   * from the outcome instead: `ok` only when a services document was produced, `unknown`
   * when something answered unwell, `unavailable` when nothing usable answered — never a
   * synthetic `error`, which the wire never measured.
   */
  const apiState: BadgeState =
    outcome === null
      ? 'unavailable' // never painted: while pending the badge slot shows the loader
      : outcome.kind === 'ok'
        ? 'ok'
        : outcome.kind === 'http-error'
          ? 'unknown'
          : 'unavailable';

  // Read once so the embeddings row's state and its provider/model detail come from the same
  // validated probe. Declared before `serviceRows` because the embeddings entry reads it.
  const embeddingsProbe = serviceStatus(health, 'embeddings');

  // Two groups, in the order the deployment needs them: the core the page cannot serve without,
  // then the optional integrations a workspace may never use. The banner is computed from the
  // core probes only (`summarizeHealth` above), so an optional row failing shows up here and in
  // the amber note — never in the banner color.
  const serviceRows: {
    key: string;
    group: 'core' | 'optional';
    title: string;
    description: string;
    state: BadgeState;
    detail?: string;
  }[] = [
    {
      key: 'api',
      group: 'core',
      title: t.pages.status.api_server,
      description: t.pages.status.api_server_desc,
      // Derived from the fetch outcome, not from a probe: see the comment above `apiState`.
      state: apiState,
    },
    {
      key: 'database',
      group: 'core',
      title: t.pages.status.database,
      description: t.pages.status.database_desc,
      state: badgeState(serviceStatus(health, 'database')),
    },
    {
      // The newest probe, and the one that would have caught the 2026-09-20 incident, where the
      // code ran four revisions ahead of the schema and 56 extractions failed on a missing column.
      key: 'schema',
      group: 'core',
      title: t.pages.status.schema,
      description: t.pages.status.schema_desc,
      state: badgeState(serviceStatus(health, 'schema')),
    },
    {
      // Decision D5: this row used to claim to speak for every LLM provider under the title
      // "LLM Runner", but the only probe behind it is the server's default Ollama host. The
      // cloud providers are per-workspace configuration verified when that workspace saves it,
      // so the row now says what is actually measured and where the rest is configured.
      key: 'ollama',
      group: 'optional',
      title: t.pages.status.llm_runner,
      description: t.pages.status.llm_runner_desc,
      state: badgeState(serviceStatus(health, 'ollama')),
    },
    {
      key: 'qdrant',
      group: 'optional',
      title: t.pages.status.vector_store,
      description: t.pages.status.vector_store_desc,
      state: badgeState(serviceStatus(health, 'qdrant')),
    },
    {
      // Decision D6: the payload carries the provider and model the probe actually used, and
      // this row is the only place they reach the operator.
      key: 'embeddings',
      group: 'optional',
      title: t.pages.status.embeddings,
      description: t.pages.status.embeddings_desc,
      state: badgeState(embeddingsProbe),
      detail:
        embeddingsProbe?.provider && embeddingsProbe?.model
          ? `${embeddingsProbe.provider} / ${embeddingsProbe.model}`
          : undefined,
    },
    // `status-probes-mirror.test.ts` reads this array's copy keys straight from the
    // source, matching the literal from `const serviceRows` to its closing `];`; the
    // terminator's indentation is not part of the pin, only that the array is a literal.
    // The drift guarantee therefore survives the move out of the `.astro` frontmatter.
  ];

  // The per-group views of `serviceRows`, declared after the array they read. The old SSR
  // page guarded this ordering against a frontmatter TDZ that would have 500'd every request
  // with a green build; in the island the same throw now crashes the client render of the
  // panel instead — and unlike the `.astro` frontmatter, this file is executed and asserted
  // by vitest, so the class of failure that shipped on 2026-09-20 is at least visible to the
  // suite now.
  const coreRows = serviceRows.filter((row) => row.group === 'core');
  const optionalRows = serviceRows.filter((row) => row.group === 'optional');

  // Pending loader: a pulsing dot plus the `checking` copy, occupying the badge slot (with a
  // fixed minimum width, right-aligned) so nothing shifts when the real badge lands.
  const renderBadge = (state: BadgeState) =>
    pending ? (
      <span className="inline-flex min-w-24 items-center justify-end gap-1.5 text-sm font-medium text-(--color-text-tertiary)">
        <span className="h-2 w-2 animate-pulse rounded-full bg-(--color-text-tertiary)" />
        {t.pages.status.checking}
      </span>
    ) : (
      <span
        className={`inline-flex min-w-24 items-center justify-end gap-1.5 text-sm font-medium ${badgeTextClass(state)}`}
      >
        <span className={`h-2 w-2 rounded-full ${badgeDotClass(state)}`} />
        {badgeLabel(state)}
      </span>
    );

  const renderRow = (row: (typeof serviceRows)[number]) => (
    <div className="flex items-center justify-between p-4">
      <div>
        <p className="font-medium text-(--color-text)">{row.title}</p>
        <p className="text-sm text-(--color-text-secondary)">{row.description}</p>
        {row.detail && <p className="text-xs text-(--color-text-tertiary)">{row.detail}</p>}
      </div>
      {renderBadge(row.state)}
    </div>
  );

  const lastUpdated = pending
    ? t.pages.status.checking
    : health
      ? new Date(health.timestamp).toLocaleString(locale)
      : // Settled with nothing: an em dash, never a perpetual "Checking…".
        '—';

  return (
    <section aria-busy={pending} aria-label={t.pages.status.services_title}>
      {/* Status indicator banner. `role="status"` + `aria-live="polite"` on the verdict text
          announces the settled result once, without the pending state spamming the reader. */}
      <div
        className={`flex items-center gap-3 rounded-lg border p-4 mb-2 ${bannerBgClass(bannerState)}`}
      >
        <span
          className={`relative block h-3 w-3 shrink-0 rounded-full ${bannerDotClass(bannerState)}`}
        >
          {bannerState !== 'pending' && (
            <span
              className={`absolute inline-flex h-3 w-3 animate-ping rounded-full ${bannerDotClass(bannerState)} opacity-75`}
            />
          )}
        </span>
        <div role="status" aria-live="polite">
          <p className={`font-semibold ${bannerTextClass(bannerState)}`}>{bannerTitle}</p>
          <p className={`text-sm ${bannerTextClass(bannerState)}`}>{bannerDesc}</p>
        </div>
      </div>

      {/* Decision D2: a green banner with a visible caveat, never a bare "degraded".
          `bannerState === 'ok'` already implies a document arrived and settled: the summary
          answers `down` otherwise, so no separate `health` check is needed here. */}
      {bannerState === 'ok' && optionalNote && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300">
          {t.pages.status.optional_unavailable_note.replace('{list}', optionalNote)}
        </div>
      )}

      <h2 className="mt-8 text-xl font-bold text-(--color-text)">
        {t.pages.status.services_title}
      </h2>

      <h3 className="text-sm font-semibold tracking-wide text-(--color-text-secondary) uppercase">
        {t.pages.status.core_group}
      </h3>

      <div className="mt-2 divide-y divide-(--color-border) rounded-lg border border-(--color-border)">
        {coreRows.map(renderRow)}
      </div>

      <h3 className="mt-8 text-sm font-semibold tracking-wide text-(--color-text-secondary) uppercase">
        {t.pages.status.optional_group}
      </h3>

      <div className="my-2 divide-y divide-(--color-border) rounded-lg border border-(--color-border)">
        {optionalRows.map(renderRow)}
      </div>

      <p className="flex items-center gap-3 text-sm text-(--color-text-tertiary)">
        <span>
          {t.pages.status.last_updated}: {lastUpdated}
        </span>
        {!pending && (
          <button
            type="button"
            onClick={retry}
            className="rounded-md border border-(--color-border) px-2 py-0.5 text-xs font-medium text-(--color-text-secondary) hover:bg-(--color-surface-secondary)"
          >
            {t.pages.status.retry}
          </button>
        )}
      </p>
    </section>
  );
}
