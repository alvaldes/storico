## v0.5.1 (2026-09-24)

### Fix

- **config**: use gemini-embedding-001, text-embedding-004 is retired
- **vector**: log a lost RAG point instead of dropping it silently
- **health**: make the vector-store diagnostics tell the truth
- **i18n**: stop promising Trello export and guard the copy
- **observability**: configure application logging in the app factory
- **extraction**: record the real model and confidence on the RAG point
- **api**: report a foreign provider id as containment, not as absence

### Refactor

- **db**: drop the legacy few_shot_examples column

## v0.5.0 (2026-09-21)

### Feat

- **observability**: log the few-shot injection
- **deploy**: apply migrations inside a maintenance window

### Fix

- **config**: name the Ollama setting the application reads
- **vector**: give seed points valid ids and count only what landed
- **llm**: disable streaming in the Ollama chat payload
- **deploy**: stop the migration container, not just the watcher
- **deploy**: bound the migration and stop swallowing the tag failure
- **db**: convert extractions.status to its enum and drop the duplicate index
- **build**: compare the version field instead of grepping for the tag
- **build**: refuse to bump when a version file lags the tag

### Refactor

- **models**: declare JSONB by dialect variant and the two status indexes

## v0.4.0 (2026-09-21)

### Feat

- **backend**: make a code/schema mismatch observable
- **backend**: encrypt the credentials already in the database
- **backend**: encrypt the stored credential at the repository boundary
- **backend**: add a cipher port and a Fernet implementation
- **backend**: stamp the end time on every terminal path
- **backend**: persist when an extraction finished
- **frontend**: drop the per-user LLM config and persist the export default
- **backend**: drop llm from the user preferences contract
- **backend**: drop the stored per-user LLM preferences
- **backend**: define blank-means-absent for LLM config values once
- **frontend**: block extraction until the workspace LLM config is complete
- **frontend**: validate the LLM draft and refuse to save an incomplete one
- **frontend**: mirror the LLM config rule and validate the draft with zod
- **backend**: refuse to extract while the LLM config is incomplete
- **backend**: let a member read whether the LLM config is complete
- **backend**: declare the LLM config completeness rule once
- **frontend**: show the name counter and the reserved-name message
- **frontend**: mirror the free-form provider name rule
- **backend**: accept free-form custom provider names
- **frontend**: probe the provider the settings form holds
- **backend**: probe the model list for the pending provider selection
- **frontend**: pick providers from a list instead of typing them
- **frontend**: add the custom provider data layer
- **backend**: expose the custom provider registry API
- **backend**: register custom LLM providers per workspace
- **frontend**: load custom provider models on demand
- **backend**: probe custom LLM providers as OpenAI-compatible
- **frontend**: allow adding custom LLM providers in settings
- **frontend**: allow setting a model the provider does not list
- **frontend**: turn the few-shot limit into a slider
- **frontend**: replace the few-shot toggle with the shadcn switch
- **frontend**: few-shot config editor replacing manual examples
- **backend**: automatic few-shot retrieval from Qdrant
- **backend**: add EmbeddingPort abstraction with cloud adapters
- **backend**: add OpenAI and Anthropic LLM adapters
- **frontend**: restore SSR for all islands with hydration-safe theming
- simplify ErrorDisplay to placeholder for future use
- frontend error handling - ErrorDisplay + duplicate story toast
- add sort options to user stories list
- change duplicate detection from raw_text to parts (actor, feature, benefit)
- improve duplicate story error message with existing story ID
- prevent duplicate user stories within the same project
- **frontend**: implement domain-user-story-task-states UI integration
- implement domain-user-story-task-states with explicit enums and validated transitions
- **db**: migrate primary key generation from UUIDv4 to UUIDv7

### Fix

- **test**: give the migration chain the master key revision 0024 requires
- **test**: keep the password when rendering the container URL for Alembic
- **backend**: cache only a successful expected-head read
- **ci**: fail the deploy when production is not ready
- **settings**: retire the trello export format on read, reject it on write
- **backend**: stop the health test from depending on the environment
- **backend**: stop the unauthenticated health route from publishing str(e)
- **backend**: stop the model probe from leaking the credential it uses
- **backend**: stop the model probe from leaking the credential it uses
- **backend**: validate the connection-test provider with the registry's own rule
- **frontend**: name Gemini in the copy, and guard both halves of the drift
- **backend**: stop the connection test from refusing the names extraction routes
- **frontend**: keep the whole failure in the stores, not just its message
- **frontend**: clean the legacy settings key on every page, not just /account
- **frontend**: drop the legacy settings key that held plaintext API keys
- **frontend**: keep one stable empty array for the task editor's siblings
- **review**: one removed-keys rule, deploy order, and the doc left behind
- **review**: scope the alert, handle two detail edges, keep the retry spinner
- **frontend**: render the error card and give Kanban a reachable failure
- **review**: normalize the credentials the connection test receives
- **backend**: treat a blank LLM endpoint or credential as absent
- **review**: correct the security doc and four imprecise claims
- **i18n**: stop promising a ready setup on the public docs page
- **i18n**: drop the duplicated keys and guard the locale files
- **frontend**: stop promising a ready workspace in onboarding
- **frontend**: stop claiming the API key is stored encrypted
- **review**: cover every mirrored length and drop a whitespace endpoint
- **frontend**: give custom provider rows the glyph the trigger already shows
- **review**: compare the built-in list by membership, and stop retyping it
- **review**: answer a legacy row's no-op rename before the reservation
- **backend**: stop the cache TTL test from depending on machine uptime
- **backend**: stop the Postgres integration probe from getting an async driver
- **frontend**: stop jamming the model id into its name in the dropdown
- **frontend**: make the discovered models a dropdown, not a button block
- **frontend**: show discovered models as a visible list in custom mode
- stop handing a cloud provider the Ollama host as its base URL
- **backend**: route custom providers to the OpenAI-compatible adapter
- **backend**: unify the authorization contract
- **backend**: require the workspace scope in the vector store
- **backend**: one authorization authority, and the two gaps it revealed
- **backend**: one authorization authority, and the two gaps it revealed
- **frontend**: close the workspace-scope leaks left in the stores
- **frontend**: make workspace switching atomic and workspace-scoped
- **frontend**: make the model field selection-only
- **i18n**: use neutral Spanish in the UI copy
- **frontend**: show the saved LLM model in the workspace settings field
- **backend**: repair the extraction API tests that lied about the contract
- **frontend**: persist few-shot config edits from workspace settings
- **frontend**: scope dark theme tokens to the dark variant
- **frontend**: sibling-only dependencies and empty-workspace export
- **backend**: resolve markdown export dependencies to task titles
- **frontend**: treat extraction 401 as auth failure and lock kanban cards
- **backend**: export markdown grouped by story
- **backend**: route OpenAI and Anthropic providers to their adapters
- **frontend**: align task status validation with the backend contract
- **backend**: treat a no-op status as a non-transition
- **frontend**: declare the locale prop ErrorDisplay already receives
- **frontend**: read translations as properties, not function calls
- **frontend**: let Vite prebundle @base-ui so islands can hydrate
- **frontend**: remove redundant use-sync-external-store Vite aliases
- add jose dependency for JWT signing in API proxy
- add packageManager field and regenerate pnpm-lock.yaml for Vercel deploy
- rename alembic migration 0c1d8af70444 to 0019 for sequential versioning
- **frontend**: resolve React 19 + Zustand SSR crash and sync-external-store aliases
- few-shot examples and frontend hydration
- enforce workspace authorization on all list endpoints (stories, tasks, extractions)
- ProjectsList error handling
- validateKeywords to accept 'As an user' and 'As a(n) user' formats
- update UserStory entity status during extraction lifecycle
- sync story status after extraction completes
- normalize DB URL for asyncpg in alembic migrations
- **extractions**: add missing user_story_status and completed_at to ExtractionResponse
- add user_story_status column to extractions table (migration 0017)
- eliminate silent errors in task extraction pipeline
- Gemini model selector display consistency
- disable prepared statement cache for pgbouncer compatibility
- show onboarding modal on any page, not only /dashboard
- persist LLM provider from onboarding to workspace config
- **app**: loggear excepcion de recover_stuck_extractions en lifespan
- **frontend**: sync stale state across auth, workspace, and task stores
- align character counters below inputs, add p-px to shell wrapper for card ring

### Refactor

- **settings**: drop the stale RAG placeholders from .env.example
- **settings**: remove the two RAG settings nothing reads
- **backend**: declare the settings dependencies as PEP 695 type aliases
- **backend**: single authority for task state transitions
- **backend**: drop the unused extraction use case and its DI factories
- **frontend**: single source of truth for task status transitions
- **db**: standardize Alembic revision 3fefad99b84d to 0003

### Perf

- **api**: eliminar N+1 en workspaces, members y projects; fix race condition pool_pre_ping + asyncio.gather
- **users**: paralelizar las 3 queries de get_me con asyncio.gather
- **db**: singleton de session factory en get_session_factory
- **projects**: eliminar count_stories extra en get_project y update_project
- **auth**: cachear usuario autenticado 30s por user_id
- **db**: desactivar pool_pre_ping a favor de pool_recycle
- **db**: subir pool_size/max_overflow a 10/20 y agregar pool_recycle 30min
- **config**: cachear Settings con lru_cache y exponer get_settings
- **projects**: eliminar N+1 en list_projects con JOIN y group_by

## v0.3.2 (2026-07-22)

### Fix

- include .j2 prompt templates in installed package

## v0.3.1 (2026-07-22)

### Fix

- **deploy**: use git reset --hard to handle local changes on VM

## v0.3.0 (2026-07-22)

### Feat

- Oracle VM deployment, auth fix, and auto-deploy workflow
- **kanban**: ScrollArea component for per-column scroll
- **sidebar**: active state + Projects collapsible
- implement user story decomposition to Kanban tasks

### Fix

- **frontend**: route extraction through workspace-scoped endpoint

## v0.2.0 (2026-07-18)

### Feat

- add workspace members by email instead of UUID
- **onboarding**: add spinner to Get Started button while submitting
- **onboarding**: add icon picker to workspace name step
- add onboarding illustrations with ProviderIcon in step 3
- implement delete account flow with cascade FK migration
- workspace deletion with two-step confirmation and workspace switch navigation
- add workspace name/icon editing to settings with store sync
- add icon picker with i18n for workspaces and projects
- add 404 page with i18n support and PublicLayout
- replace Lucide provider icons with brand SVGs from SVGL
- add provider icons to LLM config selector
- add ChevronsUpDown icon to sidebar avatar dropdown trigger
- **ui**: auto-populate model suggestions per LLM provider with Combobox
- adapt LLM config fields to selected provider
- **ui**: replace Lucide brand icons with SVGL icons (Ollama, OpenAI, Anthropic, GitHub)
- **i18n**: complete frontend internationalization coverage
- **ui**: remove close button and prevent escape dismissal on onboarding
- **ui**: add back button and focus management to onboarding
- limit workspace name to 100 chars across db, api, and frontend
- complete first-login onboarding flow with schema drift alignment
- **ui**: wire onboarding modal into Dashboard
- **i18n**: add onboarding translations
- **ui**: create OnboardingModal component
- **api**: populate isFirstLogin and workspaceName from user profile
- **api**: add completeOnboarding to user-api
- **store**: add isFirstLogin to authStore
- **api**: add patch method to ApiClient
- move header controls into sidebar user menu
- **workspaces**: full workspace management with members, roles, and LLM config
- **projects**: extract ProjectsList from Dashboard, add /projects page with sidebar link
- **ui**: show short UUID on story cards and detail page
- **breadcrumb**: shorten UUIDs like GitHub commit hashes
- **stories**: add hover-card info icon for disabled create button
- show project name in create story dialog title
- card click goes to detail, ExternalLink replaced with Edit button
- add status field to UserStory backend + frontend fallback
- story detail page with extraction, input-group addons for parts mode
- story form with parts/full-text modes, live preview, keyword validation
- add Zod 4 validation with max length limits across frontend and backend
- add Vercel deployment config for frontend (Astro) and backend (FastAPI + Mangum)
- **projects, stories**: full CRUD frontend with API libs, stores, forms, and pages
- **settings**: Sonner toasts, i18n, real button state, camelCase API
- **backend**: add settings API endpoints and connect frontend
- **frontend**: add Settings page with LLM, appearance, and export configuration
- dynamic tooltips for sidebar collapse toggle
- collapsible sidebar with icon-only mode on desktop
- auto breadcrumb from path segments
- add breadcrumb to dashboard page via shadcn CLI
- add tooltips to icon-only elements across the UI
- **backend**: implement OAuth account linking by email
- add last updated date to docs and api pages
- **terms**: expand terms of service from 4 to 14 sections
- **privacy**: add Geist Mono section numbers (01-13) to all headings
- **nav**: add '← Back to home' button to public pages
- **privacy**: expand privacy policy from 5 to 13 sections
- **status**: live health checks for DB, Ollama, and Qdrant services
- **nav**: add GitHub icon, active link highlighting, and updated nav links
- **i18n**: extract static page content to i18n keys and add Spanish translations
- **auth**: redirect landing CTAs to dashboard when already logged in
- unify theme toggle across all layouts via React ThemeToggle component
- replace theme SVGs with Lucide, add LangToggle component, use shadcn Button tokens for CTA
- replace hardcoded mobile drawer with Sheet island in landing page
- replace feature cards with shadcn Card + Lucide icons
- use shadcn Button and Card in Dashboard
- replace FAQ details with shadcn Accordion, remove inline script
- init shadcn v2, replace mobile drawer with Sheet, clean CSS vars
- landing nav/footer real routes, auth guard, static pages
- **hero**: move favicon watermark behind hero left column as absolute bg
- **footer**: add blurred favicon watermark as bg decoration in CTA+footer section
- **landing**: unify brand colors, shadows under @theme, add favicon logo to navbar/hero/footer
- **landing**: add background texture and CTA grid overlay
- **landing**: add FAQ section with accordion and i18n support
- implement i18n with astro:before-swap theme fix
- dark/light theme system for landing page and layouts
- add Qdrant vector store for RAG extraction context

### Fix

- start workspaceStore loading=true so idle state is always loading
- preserve persisted workspace name in TeamSwitcher during loading
- hide ownership section after transfer
- prevent admins from changing their own role
- refresh workspace store after ownership transfer
- show admin name instead of UUID in transfer ownership Select
- 500 error on workspace ownership transfer
- i18n for workspace role in sidebar TeamSwitcher
- show translated label in role change Select trigger
- add loading spinner to role change Select in MemberManagement
- add consistent loading state pattern to async buttons
- sonner toast background invisible due to wrong CSS variable names
- **auth**: redirect to login after sign out
- **i18n**: replace hardcoded English strings with translation keys
- **onboarding**: dim text instead of hiding it during submission
- make login logo link to home page
- sync form state from initialData when dialog reopens
- lang-toggle history replace + sonner CSS persistence via persist <link>
- project icon persistence and related fixes
- **api**: throw Error subclass instead of plain object, prevent [object Object] in error messages
- show provider label (not raw value) in SelectTrigger
- **i18n**: normalize Spanish to neutral (remove voseo forms)
- **ui**: make dashboard header sticky on scroll
- **ui**: simplify workspace settings breadcrumb to just 'Settings'
- **types**: resolve all TypeScript errors, zero errors on npx tsc --noEmit
- block escape key at dom level to prevent base ui dialog close
- detect auth provider correctly when backend not available
- populate auth store in DashboardShell for SettingsPage
- persist sidebar state across page navigations without flash
- **ui**: handle ORB-blocked Google avatars with UserAvatar fallback
- **breadcrumb**: House icon root linking to /dashboard
- **dashboard**: link User Stories button in recent stories section
- **stories**: contextual back link syncs with breadcrumb hierarchy
- **breadcrumb**: immediate contextual path for story details
- **breadcrumb**: show loading dots while resolving UUIDs
- **breadcrumb**: show contextual path for story details
- stories filter by project
- stories from wrong project visible due to View Transitions stale store
- stories from wrong project showing on project detail page
- StoryForm edit dialog not showing story data
- replace @tailwindcss/vite with @tailwindcss/postcss for SSR CSS generation
- proxy 502 al hacer DELETE de proyectos
- boton delete invisible por conflicto de clases
- toast de proyecto creado no se mostraba
- dropdown trigger navegaba pese a stopPropagation
- click en tres puntos navegaba al proyecto
- asChild deprecated en shadcn v4, usar render prop
- proxy 502 al crear projects
- settings responsive <468px — badge y botones
- mostrar breadcrumb encima del título en mobile
- reemplazar mobile sidebar toggle por shadcn DropdownMenu
- normalize asyncpg DB URL — convert sslmode to ssl param
- configure Astro security.allowedDomains for Vercel
- disable Astro's built-in CSRF origin check for Vercel
- add explicit trustHost: true to auth.config for Vercel serverless
- correct testcontainers-postgres version constraint
- use module:object format for Vercel entrypoint
- configure Vercel FastAPI entrypoint for Mangum handler
- **proxy**: build clean headers instead of copying from request
- **oauth**: set explicit base URL in Auth.js config for ngrok HTTPS redirect URIs
- **dev**: add .ngrok-free.app to Vite allowedHosts for tunnel access
- **oauth**: set explicit base URL in Auth.js config for localhost callbacks
- **oauth**: add AUTH_URL to force localhost base for Google OAuth callbacks
- **settings**: use backend auth_provider instead of parsing email for OAuth provider badge
- **i18n**: translate UserMenu tooltip with locale prop
- add LangToggle to dashboard header and translate empty state
- resolve auth-astro client loading and Google OAuth IPv6 timeout
- replace hardcoded UI text with i18n translations across 11 files
- remove /about from desktop nav links
- remove disabled prop from ThemeToggle to prevent hydration mismatch
- mobile nav uses all public links grouped by category
- **nav**: constrain separator width to link content with w-fit wrapper
- **frontend**: make API docs link clickable and add GitHub link to privacy contact
- **status**: make API Server indicator consistent with other services for unavailable state
- **status**: add missing success text color on API Server indicator
- **status**: add missing Qdrant service indicator to status page
- **status**: keep indicator circle perfectly circular on mobile
- **i18n**: normalize spanish from voseo (Rioplatense) to neutral tuteo
- **landing**: hide phone mockup on mobile, center orphan feature card on md
- position MobileNav dropdown below header with 3.75rem top offset
- **nav**: active link highlighting broken for English locale and View Transitions
- replace deprecated ViewTransitions with ClientRouter and fix Locale types
- **theme**: prevent React 19 hydration mismatch in ThemeToggle
- add zustand to optimizeDeps.include to prevent Vite 504 on dynamic import
- **dark**: change --color-surface to #0f141d
- **hero**: bump watermark to 0.20 opacity and 50px blur
- **footer**: lower watermark opacity to 0.18, remove dark mode bg for cleaner overlay
- **footer**: adjust watermark to full height, blur-20, opacity-0.3
- preserve scroll position across language toggle navigation
- remove 'Free' from CTA buttons, no paid tiers exist
- center nav items between logo and controls in header
- replace 'All rights reserved' with MIT license notice in footer
- correct CTA subtitle, app is free and open source, not just while in development

### Refactor

- unify .env structure — single root + symlinks, session pooler for Supabase IPv4
- **ui**: separate user account from workspace settings, fix hydration error
- replace ToggleGroup with SegmentedControl for single-select settings
- **ui**: migrate all forms to shadcn Field pattern, replace all raw inputs
- **breadcrumb**: responsive breadcrumb with ellipsis for mobile
- move GitHub link from sidebar user menu to Settings About section
- **layout**: unify all pages on shadcn Sidebar 07
- proxy hardening — timeout, path sanitization, header forwarding
- extract auto breadcrumb to reusable React component
- move breadcrumb from Dashboard to Header
- use Locale type instead of string for Astro.params.locale
- replace category labels with separators in mobile nav
- **frontend**: centralize env vars in frontend/.env with config module
- **footer**: restructure layout with responsive column ordering and brand repositioning
- extract PublicNavbar and PublicFooter, unify public pages under PublicLayout
- **theme**: remove dead code and unify colors with CSS tokens
- unify 3 separate theme systems into shared module

## v0.1.0 (2026-07-09)

### Feat

- inizial commit - Storico project
