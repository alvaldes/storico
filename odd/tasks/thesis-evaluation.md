# thesis-evaluation

> **Status**: planning. The owner's inputs are recorded on 2026-10-07; the instrument decision is
> **deliberately parked for another session**. Nothing here is authorized implementation work yet.
> **Created**: 2026-10-07

## What this document is

The design of the thesis's experimental evaluation. It **does not exist anywhere in this repository
today**, and that is the finding that opened this record: `TCR`, `TAS` and `IFI` appear only as
**names** — in `AGENTS.md`'s KPI table and glossary, and as open rows in `prod.todo.md` — while
`CONTRIBUTING.md:226` calls them "planned in the thesis", `README.md:23` says the evaluation is
pending, and the application has **no way for anyone to score anything**. Measured on 2026-10-07 by
searching the metric names across every document: four files, none of them a protocol, a rubric or an
instrument.

So the evaluation is not a task waiting to be executed. **It is a design that has to be produced
first**, and it has to exist before the six experts are invited, because six people scoring without a
shared rubric produce six incomparable datasets.

## The owner's decisions, 2026-10-07

| Decision | Chosen |
| --- | --- |
| **Models to compare** | Gemini + OpenAI + Anthropic (cloud) **and one local model through Ollama** |
| **Corpus** | the user stories already registered in the owner's **second-brain vault** — not Salony |
| **Instrument** | **not decided**: parked on purpose, to be taken in another session |

## What the model comparison still needs

- **Two cloud credentials that do not exist in production today.** Gemini is configured; OpenAI and
  Anthropic have real adapters (`backend/src/storico/infrastructure/llm/`) and no key.
- **Ollama is not running on this machine** — measured 2026-10-07, `health/services` reports
  `ollama: not reachable` with `scope: optional` — and no local model is downloaded. The local axis
  needs Ollama installed plus a model (single-digit GB), and one decision the record cannot make:
  **where it is measured.** Local latency on this machine is not comparable with cloud latency
  unless both are measured under the same conditions and the difference is stated rather than
  smoothed over.
- **The comparison's methodology**: the same stories, the same rendered prompt, the same time
  recording. The thesis's placeholder table asks for precision, consistency, speed and cost per
  extraction — the first two need the corpus and the instrument below, and the last two are
  measurable from the row the extraction already stores (`completed_at - created_at`,
  `prompt_config -> 'usage'`).

## What the corpus still needs

- **The vault is not in this repository and no path is recorded in it.** The repository references
  the vault as a second-brain of notes (seventeen documents mention it) and once records that it is
  owned by a separate live session, so the corpus has to come out of it **with the owner's hand or
  his explicit authorization**, and this record does not assume access to it.
- Once the notes are identified: **how many stories**, in **what format**, and whether they are
  already user stories in the INVEST shape the application requires (`As a(n) …, I want …, so that
  …`). A corpus written for another purpose needs converting, and whoever converts it becomes part of
  the measurement — that is a bias risk to state, not to discover later.
- **The sample size is a real decision, not a detail.** Six experts cannot review hundreds of
  stories. A usable expert judgment uses a bounded sample, and the stories must be **drawn**, never
  chosen for having worked well: picking the successful ones makes the result circular.

## The instrument, parked with everything the decision needs

Three options were put to the owner and the decision was deferred to another session. What each
costs, so the next session does not have to reconstruct it:

1. **Protocol and rubric versioned in the repository, plus one spreadsheet per expert.** The cheapest
   auditable option: the protocol becomes evidence of the thesis, and the data can be re-analysed.
   The expert fills it by hand, which is a load error waiting to happen.
2. **A scoring screen in the application.** The only option that puts the data in one place with
   structure — and the most expensive: a new data model, endpoints, UI and export, touching the
   product immediately before the evaluation, where a bug contaminates the data. It earns its cost
   only if the judgment will be repeated or run with more experts.
3. **An external form.** No development, and the instrument becomes a black box whose definition
   lives outside the repository — the same class of invisible configuration that got the Caddy rate
   limit rejected.

**Why it is not decided here**: it changes the evaluation's workload and depends on academic choices
— what exactly each metric scores and on what scale — that belong to the author and his director, not
to this repository. What the repository can do is prepare everything around that choice.

## The order that cannot be inverted

**Rubric → corpus → instrument → experts.** The instrument and the corpus have to exist before the
six experts are invited. The application's URL is already shareable, and inviting them first is how a
judgment ends up with six incomparable datasets.

## The boundary of what this repository does

The **academic validity** — which metrics, on what scale, with what analysis, and what the thesis
argues — belongs to the author and his director. The **engineering** — a reproducible protocol, the
corpus preparation and its validation, the instrument, and the evidence that each step ran as
described — is what this repository can carry, and it should be versioned here rather than in a
document nobody can audit.

## Open, with its owner

| Item | Owner |
| --- | --- |
| The instrument decision | the owner, in another session (parked deliberately) |
| The vault's path and which stories | the owner — the repository names no path |
| Two cloud keys, and Ollama with a model installed | the owner |
| The metrics' definitions and scales | the owner and his director |
| The protocol, the corpus preparation and the instrument | this repository, once the rows above exist |
