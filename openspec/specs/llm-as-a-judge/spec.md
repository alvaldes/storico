# llm-as-a-judge Specification

## Requirements

### Requirement: Opt-In Per Run

The LLM-as-a-Judge validation MUST be requested explicitly per run: the
extraction request carries `run_validation`, the API default is `false`
(`backend/src/storico/api/schemas/extraction.py`), and nothing turns the judge
on implicitly — no workspace setting, no scheduler, no fallback path enables
it. The judge costs one extra LLM call per run when it is on, which is why it
is a deliberate per-run choice and not a default. The UI MUST expose the
switch per run in the story detail panel (`StoryDetail.tsx`), and the switch
MUST start off again on every opening: opening the panel is a NEW run, so a
previous run's choice MUST NOT leak into the next one.

#### Scenario: A run without the switch does not judge

- **GIVEN** a workspace with a complete LLM configuration
- **WHEN** an extraction is started without `run_validation` (or with it absent,
  which is the same request)
- **THEN** the run completes without any judge LLM call
- **AND** the persisted `judge_result` is null and `confidence_score` stays null

#### Scenario: The UI switch starts off on every opening

- **GIVEN** a user who enabled the judge switch on a previous run
- **WHEN** the story detail panel is opened again
- **THEN** the switch renders off
- **AND** the next extraction only judges if the user turns it on again for that run

### Requirement: The Rubric

The judge scores the experimental design's rubric (S1): seven criteria, each
on a 1-7 scale anchored at 1, 4 and 7 — `coherence`, `completeness`,
`feasibility`, `clarity`, `granularity`, `dependencies` and `usefulness`. The
anchors are the design's: 1 is "most tasks out of scope" for coherence and its
peers, 4 is "some tasks need correction", 7 is "all tasks belong / nothing is
missing / usable in a sprint as is". The total and the approval MUST be
computed by the server, never taken from the model: `total_score` is the sum
of the seven criteria (7-49 across the run's maximum `max_total = 49`), and
`approved` is `total_score >= ceil(0.7 × 49) = 35`.

#### Scenario: A full verdict carries all seven criteria and a computed total

- **GIVEN** a judged run whose judge response scores every criterion
- **WHEN** the verdict is persisted
- **THEN** `judge_result.criteria` holds exactly the seven named criteria, each
  with a `score` coerced into [1, 7] and its `justification`
- **AND** `total_score` is the sum of the seven scores and `max_total` is 49
- **AND** `approved` is true exactly when `total_score >= 35`, computed on the server

#### Scenario: The server does not trust a model-declared total

- **GIVEN** a judge response whose declared total disagrees with the sum of its
  criteria, or whose scores need clamping into [1, 7]
- **WHEN** the verdict is built
- **THEN** `total_score` and `approved` are recomputed from the coerced criteria
- **AND** no value the model claimed about the total or the approval survives

### Requirement: TAS and IFI Are Derived Server-Side

The indices MUST be computed from the criteria by the server and never taken
from the model: `tas = (coherence + feasibility) / 2` and
`ifi = (clarity + granularity + dependencies) / 3`. `completeness` and
`usefulness` stand alone — completeness is the human counterpart of the
automatic TCR, and no index consumes it. The frontend MUST render the
persisted `tas`/`ifi` values and MUST NOT recompute them.

#### Scenario: The indices come from the criteria

- **GIVEN** a judged run with `coherence` 7, `feasibility` 5, `clarity` 3,
  `granularity` 2 and `dependencies` 4
- **WHEN** the verdict is persisted
- **THEN** `tas` is `(7 + 5) / 2 = 6` and `ifi` is `(3 + 2 + 4) / 3 = 3`
- **AND** neither value appears in the judge prompt nor in anything the model returned

#### Scenario: Completeness and usefulness stand alone

- **GIVEN** any judged run
- **WHEN** the indices are computed
- **THEN** neither `tas` nor `ifi` consumes `completeness` or `usefulness`
- **AND** both criteria still appear with their scores in `judge_result.criteria`

### Requirement: The Judge Is Blind

The judge prompt (`single_judge.j2`) MUST receive the user story and the
generated tasks and nothing about who generated them: it MUST NOT receive the
provider or the model name, so the judge is blind by construction and cannot
score its own or another model's work differently for knowing it.

#### Scenario: The prompt carries the story and the tasks only

- **GIVEN** a judged run by any provider and model
- **WHEN** the judge prompt is rendered
- **THEN** it contains the story text and the parsed tasks
- **AND** it contains neither the provider name nor the model name

### Requirement: The Judge Connection

The judge is a second, independent LLM configuration. `workspace_llm_configs`
carries `judge_provider` (50), `judge_model` (100), `judge_api_key` (500) and
`judge_base_url` (500) — migration `0034` adds the model, `0035` the other three
— all nullable and all falling back **independently** to the workspace's
extraction configuration. The workspace counts as having a separate judge when
any of the four is set. The persisted verdict MUST record the connection it used:
`judge_result.provider`, `judge_result.model` and `judge_result.model_source`
(`"workspace"` for any separately configured judge, `"extraction"` only when none
of the four is set), on both the ok and the failed records, so a failed judgement
still names who was asked.

`judge_api_key` is encrypted by the workspace configuration repository — the only
place a credential is encrypted on the way in and decrypted on the way out.

#### Scenario: Another model on the extraction provider and credential

- **GIVEN** a workspace with `judge_model` set and no other judge field
- **WHEN** the run judges
- **THEN** the judge call uses that model on the extraction provider, credential and endpoint
- **AND** the verdict carries `model_source` = `"workspace"` and the provider that was used

#### Scenario: Another provider, another credential and another model

- **GIVEN** a workspace with `judge_provider`, `judge_api_key`, `judge_base_url` and `judge_model` set
- **WHEN** the run judges
- **THEN** the judge call is built for that provider with that credential and that endpoint
- **AND** the extraction port is not used for judging
- **AND** the verdict records the judge provider, the judge model and `model_source` = `"workspace"`

#### Scenario: A credential never crosses providers

- **GIVEN** a workspace whose extraction provider is A and whose `judge_provider` is B, with no `judge_api_key`
- **WHEN** a run with `run_validation` on completes
- **THEN** no request is made to B with A's credential
- **AND** the judge does not run and the verdict is `state: "failed"` naming the missing field and the provider
- **AND** the extraction itself completes normally

#### Scenario: Nothing configured falls back entirely

- **GIVEN** a workspace with none of the four judge fields set and `run_validation` on
- **WHEN** the run judges
- **THEN** the judge uses the same provider, credential, endpoint and model the extraction used
- **AND** the verdict carries `model_source` = `"extraction"`

### Requirement: The Record and Its Three States

The run's verdict is persisted as `extractions.judge_result` (JSON, migration
`0033`), written once in the same terminal UPDATE as `confidence_score`. The
persisted data MUST distinguish THREE states, not two: `judge_result` null
with `prompt_config.validate == false` is **not requested**; `state: "ok"` is
**ran**, carrying `criteria`, `total_score`, `max_total`, `approved`, `tas`,
`ifi`, `model` and `model_source`; `state: "failed"` is **requested and
failed**, carrying `error` and `error_type` beside `model`/`model_source`. A
failed judgement MUST NOT change the run's own status: the run is `completed`
with whatever tasks it produced, and only the judge record says the judgement
did not happen. A FOURTH reading exists and is not a state of its own: a run
asked to judge (`prompt_config.validate == true`) whose own extraction failed
never reaches the judge, so it also carries `judge_result` null. `judge_result`
says nothing about a run that never completed — the three states are only
meaningful when the run itself reached a terminal status — and an analysis
MUST filter on the run's `status`, never on `prompt_config.validate` alone.

#### Scenario: Not requested is distinguishable from failed

- **GIVEN** two completed runs, one started without `run_validation` and one
  started with it whose judge call failed
- **WHEN** their rows are read
- **THEN** the first has `judge_result` null and `prompt_config.validate` false
- **AND** the second has `judge_result.state == "failed"` with a non-null
  `error`, so the two states cannot be confused

#### Scenario: A failed judgement does not fail the run

- **GIVEN** a run with `run_validation` on whose judge call raises
- **WHEN** the run terminates
- **THEN** the run's `status` is `completed` and its tasks persist normally
- **AND** `judge_result.state` is `"failed"` with `error` and `error_type`,
  and `confidence_score` stays null

#### Scenario: A failed run that was asked to judge also carries a null verdict

- **GIVEN** a run started with `run_validation` on whose extraction itself
  failed before reaching the judge
- **WHEN** its row is read
- **THEN** `judge_result` is null even though `prompt_config.validate` is true
- **AND** a reader that filters on `validate` instead of the run's `status`
  would mistake this for "the judge ran and failed silently", which is not
  what happened

### Requirement: Judge Output Validation

An unusable judge payload is a classified failure, not a swallowed one. A
score that cannot be coerced into a number, a non-finite score, a missing
criterion, or a criterion entry that is not an object MUST raise
`JudgeOutputError` — a subclass of `LLMError` naming the criterion and the
offending value — so the call site's existing `except LLMError` catches it and
MUST NOT retry it as a transient error. The classification lives in
`JudgeResult.from_model_output`, the one place every caller builds a verdict
through, so no caller can bypass it.

#### Scenario: An uncoercible score is a classified failure without retry

- **GIVEN** a judge response whose `coherence` score is a word, `null`, a list
  or `NaN`
- **WHEN** the payload is validated
- **THEN** `JudgeOutputError` (an `LLMError`) is raised naming the criterion
  and the offending value
- **AND** the failure is recorded once as `judge_result.state == "failed"`
  with that message, and no retry with exponential backoff runs for it

#### Scenario: A missing criterion or a non-object entry fails the same way

- **GIVEN** a judge response missing a criterion, or whose criterion entry is
  not an object
- **WHEN** the payload is validated
- **THEN** `JudgeOutputError` is raised naming the criterion
- **AND** the run completes with `judge_result.state == "failed"` and unchanged tasks

### Requirement: Legacy Records

Rows written before the rubric change carry five criteria on a 0-10 scale,
with the retired wire name `format` where `clarity` now stands. Those records
MUST NOT be rescaled or backfilled: they were produced by a different rubric,
and rewriting them would fabricate agreement data that was never measured. The
UI MUST render them as they are, in the retired wire name's stable position,
and MUST NOT show TAS/IFI for them — those indices are defined only on the
seven-criterion rubric.

#### Scenario: A pre-rubric record survives as written

- **GIVEN** an extraction row whose `judge_result` predates the seven-criterion
  rubric, with five criteria on 0-10 including `format`
- **WHEN** the record is read by the API or the UI
- **THEN** its criteria, scores and scale are exactly as persisted — no
  rescaling to 1-7, no renaming to `clarity`, no backfill of missing fields
- **AND** the judge panel shows the five criteria without TAS/IFI
