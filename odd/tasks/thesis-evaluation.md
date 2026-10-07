# thesis-evaluation

> **Status**: planning. The owner's inputs are recorded on 2026-10-07, the corpus was then measured,
> and the instrument decision stays **parked for another session** — narrower than it looked once the
> thesis's own specification was read. Nothing here authorizes implementation yet.
> **Created**: 2026-10-07

## What this document is

The design of the thesis's experimental evaluation. It **did not exist in this repository** when this
record opened, and that was measured rather than assumed: `TCR`, `TAS` and `IFI` appear only as
**names** — in `AGENTS.md`'s KPI table and glossary and as open rows in `prod.todo.md` — while
`CONTRIBUTING.md:226` calls them "planned in the thesis", `README.md:23` says the evaluation is
pending, and the application has **no way for anyone to score anything**.

What the repository also did not know is that **the specification and the corpus already exist outside
it**, in the owner's vault. This record now carries what those say, measured, so a session can plan
without re-reading a personal knowledge base.

## The owner's decisions, 2026-10-07

| Decision | Chosen |
| --- | --- |
| **Models to compare** | Gemini + OpenAI + Anthropic (cloud) **and one local model through Ollama** |
| **Corpus** | the user stories registered in the owner's vault — which turned out to be a real collection, measured below |
| **Instrument** | **not decided**, parked on purpose |

## The corpus: it exists, and it does not load as it stands

The vault note *Requirements data sets (user stories)* documents a published collection — Dalpiaz,
2024, 22 real user-story datasets from products and public bodies, curated at Utrecht University and
published on Zenodo and Mendeley — and **its folder holds the 22 `.txt` files**, one story per line.
Measured on 2026-10-07:

| Fact | Measured |
| --- | --- |
| Files | **22 `.txt`**, one dataset each |
| Lines | **1,680** — the same figure the note cites from the article's Table 4 |
| Lines that are actually stories | **1,673** tolerate the story shape once a BOM, a capitalised `AS` and the `As the …` phrasing are allowed; the **5** that are not are 3 epic headings in `g16-mis.txt` and 2 continuation lines in `g23-archivesspace.txt` |
| **Accepted by the application's own regex** | **955 — 57%** |
| **Refused by it** | **725 — 43%**, and the breakdown is the actionable part |

Why the 725 are refused, applying the exact pattern `story_import.py` and the frontend share (`As a
/an/a(n)`, optional commas, case-insensitive, and **`so that` required**):

| Cause | Count | Example |
| --- | --- | --- |
| No `so that` clause — the story has a role, an action and no benefit | **697** | `As a Data user, I want to have the 12-19-2017 deletions processed.` |
| `I don't want` instead of `I want` | **17** | `As a user, I don't want to see NASA grants displayed as contracts.` |
| `As the …`, or the article missing | **11** | `As the site editor, I want to include a teaser with each article, so that …` |
| All three markers present and still refused | **0** | — |

So the app's pattern is complete relative to those three markers, and the corpus is **57%
compatible**. 698 of the refused lines end in a period: they are finished sentences missing a benefit
clause, not truncations — which means the real decision is **not "which corpus" but "which subset, and
what normalization"**, and that choice is the owner's, because synthesizing the missing benefit would
be inventing corpus content.

**Parser traps, documented by the note and reproduced here** (any loader needs them):
`g13-planningpoker.txt`, `g24-unibath.txt` and `g28-zooniverse.txt` **are not valid UTF-8** (bytes
`0x92`, `0x93` and `0xad`, Windows-1252 leftovers); `g02-federalspending.txt` and `g12-camperplus.txt`
**start with a BOM**; the files mix CRLF and LF and 15 of 22 **do not end with a newline**.

**Two caveats from the note that belong in the thesis, not in a footnote.** The declared licence is CC
BY 4.0, but the curator states he does not know the intellectual-property status of the original
requirements. And the collection is **not neutral**: it was built to test terminological-ambiguity
detection, and the experiment that used it concluded that **manual inspection beat the tool**
(macro-recall 0.25 against 0.37). A corpus built to expose a tool's weakness is a fine stimulus and a
bad benchmark to claim victory over.

## The instrument: the shape is specified, the rubric is not

The vault note *Storico — validación con expertos* says plainly that **no instrument is built** — no
questionnaire, no form, no interview guide, no metric sheet, no rubric, no recruitment, no informed
consent — and that what exists is the **specification**, in thesis chapters that are currently
commented out and do not compile. What that specification already fixes:

- **Structured questionnaires**: **Likert 1–7** scales for quality, open questions for qualitative
  feedback, comparison matrices between approaches.
- **Interview guides**: semi-structured protocols, focus-group scripts, observation instruments.
- **Reliability**: **Cohen's Kappa** for inter-rater agreement plus intraclass correlation, rater
  calibration, internal-consistency validation.
- **Bias management**: blind evaluation where technically feasible, hard cases and counterexamples,
  stratification with documented inclusion criteria.
- **Ethics**: anonymization of identifying information, GDPR/LOPD compliance, restricted access.

**What is genuinely missing is the rubric.** The vault note is blunt about the consequence, and it is
right: the glossary **names** TCR, TAS and IFI but defines neither scale nor scoring criteria, and
*"without a rubric two experts score differently and Cohen's Kappa is worth nothing"*. That is the
decision that cannot be delegated to a repository: what each metric scores, and on what scale.

So the instrument decision parked on 2026-10-07 is narrower than the three options below suggest: the
**questionnaire form** and the **channel** are open, and the **rubric** has to come from the author
and his director.

## The models: three positions that do not agree

This is worth naming before the evaluation starts, because the thesis is judged against the thesis
text:

| Where | What it says |
| --- | --- |
| The thesis | **GPT-3.5-turbo** as the main model with **GPT-4** as fallback — in a passage that is currently commented out |
| The repository | multi-provider and **Ollama-first** (`ADR-002`), with real adapters for Gemini, OpenAI and Anthropic |
| The owner's decision, 2026-10-07 | Gemini + OpenAI + Anthropic **plus one local model** |

The owner has also already decided something upstream of this record: on 2026-09-28 the extraction
**versioning** work was excluded from what the panel judges. It contributes the evidence chain of each
run — the rendered-prompt snapshot, the model, the temperature, the few-shots — which is what makes
what is judged reproducible, and it goes into the thesis as discussion and future work rather than as
a measurable object.

**Timeline**, from a cronograma that is also commented out: expert evaluation in **month 15**,
quantitative analysis in **month 17**, complete thesis in **month 18**.

## What the model comparison still needs

- **Two cloud credentials that do not exist in production**: Gemini is configured; OpenAI and
  Anthropic have real adapters and no key.
- **Ollama is not running on this machine** — measured 2026-10-07, `health/services` reports
  `ollama: not reachable` with `scope: optional` — and no local model is downloaded. The local axis
  needs Ollama plus a model, and one decision this record cannot make: **where** it is measured,
  because local latency is not comparable to cloud latency unless both are measured under the same
  conditions and the difference is stated instead of smoothed over.
- **The comparison's method**: the same stories, the same rendered prompt, the same way of recording
  time. The thesis's placeholder table wants precision, consistency, speed and cost; the last two are
  already measurable from the row each extraction stores (`completed_at - created_at`,
  `prompt_config -> 'usage'`), and the first two need the corpus subset and the rubric.

## The order that cannot be inverted

**Rubric → corpus subset → instrument → experts.** The URL is already shareable, and inviting the six
experts first is how a judgment ends up with six incomparable datasets. The corpus work can start
today; the rubric is the blocking piece and it is not a repository's to invent.

## The boundary of what this repository does

The **academic validity** — which metrics, on what scale, with what analysis, and what the thesis
argues — belongs to the author and his director. The **engineering** — a reproducible protocol, the
corpus loader with its encoding defences and its compatibility report, the sample draw, the instrument
and its evidence — is what this repository can carry, and it should be versioned here rather than in a
document nobody can audit. The vault is a personal knowledge base owned by a separate session: this
record names its notes and never writes to them.

## Open, with its owner

| Item | Owner |
| --- | --- |
| The **rubric** for TCR / TAS / IFI: what each scores, on what scale | the owner and his director — nothing else can proceed without it |
| The corpus **subset** and what to do with the 43% the app refuses | the owner — synthesizing a benefit clause would be inventing corpus content |
| The instrument's **form and channel** | the owner, in another session (parked deliberately) |
| The vault note's open questions: judgment vs Delphi or V-de-Aiken, 6 vs 8 experts, who they are, whether manual and automatic use the same panel | the owner and his director |
| The **model tension** between the thesis text and the repository | the owner and his director |
| Two cloud keys, and Ollama with a model installed | the owner |
| The corpus loader, the compatibility report, the sample draw, the protocol | this repository, once the rows above exist |
