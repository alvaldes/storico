# extraction-versioning Specification

> **Change**: `extraction-versioning-prompt`

## ADDED Requirements

### Requirement: The Snapshot Carries the Few-Shot Examples With Their Text

Every extraction row's snapshot MUST include a `few_shots` entry listing each few-shot example
the run actually used, carrying the example's **text** (its story text and task summary) together
with the model that produced it and its similarity score — a point id in the vector store does
not say what the model saw. The entry MUST record what was passed to the render, and MUST agree
with the few-shot section of the stored rendered prompt.

#### Scenario: A completed run's few-shots are readable with their text

- **GIVEN** a run whose search returned two similar extractions and whose prompt was rendered
  with both
- **WHEN** the completed row's snapshot is read
- **THEN** `few_shots` lists both examples, each with its story text and task summary
- **AND** each entry's text matches what the stored rendered prompt shows in its few-shot section

#### Scenario: A failed run keeps its few-shots

- **GIVEN** a run whose prompt rendered with few-shot examples but whose provider call failed
- **WHEN** the failed row's snapshot is read
- **THEN** `few_shots` is present and complete
- **AND** the only legitimately missing snapshot key is the provider's token usage

### Requirement: The Snapshot Carries the Project Context and the Story Text Exactly as Sent

Every extraction row's snapshot MUST include a `project_context` entry describing what was
composed and injected for the run — the project's name and description as they were, the other
stories' text and the existing tasks — and a `story_text` entry holding the story's text exactly
as it was sent. Editing the story afterwards MUST NOT change a stored version's `story_text`.
The snapshot MUST NOT duplicate facts the row already stores elsewhere: the system prompt stays
`prompt_config.system_prompt`, and provider, model, temperature and the rendered prompt stay in
their own columns.

#### Scenario: The project context agrees with the rendered prompt

- **GIVEN** a run whose prompt was rendered with the project's context
- **WHEN** the completed row's snapshot is read
- **THEN** `project_context` records the project name, the description, the other stories and
  the existing tasks that were injected
- **AND** its content matches what the stored rendered prompt shows in its context block

#### Scenario: The story text is frozen as sent

- **GIVEN** a completed version whose `story_text` reads "As a user, I want to log in so that I
  can access my account"
- **WHEN** the story's text is edited afterwards
- **THEN** the version's stored `story_text` is unchanged
- **AND** a subsequent run stores the new text as its own `story_text`

#### Scenario: Nothing is stored twice

- **GIVEN** a completed run
- **WHEN** the row's snapshot is inspected
- **THEN** the system prompt appears only as `prompt_config.system_prompt`
- **AND** provider, model, temperature and the rendered prompt appear only in their own columns,
  not restated as new snapshot keys

### Requirement: The Snapshot Records the Omitted Negative-Example Count

Every extraction row's snapshot MUST include `negative_examples_omitted` as an integer count of
the marks the negative-example block cut — `0` when nothing was cut. The count MUST reflect the
composition of this run's block, so a snapshot with a non-zero count belongs to a prompt whose
negative-example block announced the omission.

#### Scenario: A run with fewer marks than the cap records zero

- **GIVEN** a story with 5 marks across its previous versions
- **WHEN** the next run's snapshot is read
- **THEN** `negative_examples_omitted` is 0

#### Scenario: A run over the cap records the omitted count

- **GIVEN** a story with 21 distinct marks across its previous versions
- **WHEN** the next run's snapshot is read
- **THEN** `negative_examples_omitted` is 1
- **AND** the stored rendered prompt's block announces that 1 older mark was omitted

### Requirement: Token Usage Is Stored Only When the Provider Returned It

When the provider answers with token usage, the run's snapshot MUST record that usage verbatim —
the provider's own mapping, written after the provider answers — so entered and generated tokens
can be separated per run. When a provider returns no usage, the key MUST be absent and the
absence MUST be recorded in the change's verification notes — never zero-filled, never
estimated. The provider's field name MUST be confirmed against a real response of each provider
before its adapter is wired; naming the field is not a requirement of this specification.

#### Scenario: A provider that returns usage has it stored verbatim

- **GIVEN** a provider whose response carries its own usage mapping
- **WHEN** the run completes
- **THEN** the snapshot's `usage` holds that mapping as the provider returned it
- **AND** it was written after the provider answered, in the same snapshot

#### Scenario: A provider that returns no usage leaves the key absent

- **GIVEN** a provider whose response carries no usage information
- **WHEN** the run completes
- **THEN** the snapshot carries no `usage` key
- **AND** nothing fabricates a zero or an estimate in its place
- **AND** the omission is annotated in the change's verification notes

#### Scenario: A failed run has no usage and that is complete honesty

- **GIVEN** a run whose prompt rendered but whose provider call failed
- **WHEN** the failed row's snapshot is read
- **THEN** the snapshot carries no `usage` key
- **AND** every other snapshot key is present

### Requirement: Measurement Derives From Stored Facts, With No New Instrument

A run's duration MUST be derivable as `completed_at - created_at` from the columns the row
already has, its prompt size MUST be measurable offline from the stored rendered prompt, and its
token usage MUST come from the snapshot's `usage` — no timing middleware, no metrics view and no
other new measurement instrument MUST be added.

#### Scenario: Duration and prompt size are derivable from the row alone

- **GIVEN** a completed extraction row
- **WHEN** the run is measured afterwards
- **THEN** the duration comes from the row's own `created_at` and `completed_at`
- **AND** the prompt size comes from the row's stored rendered prompt
- **AND** no middleware or metrics endpoint was added to obtain either

### Requirement: Reproducibility Is the Stored Prompt, Not a Re-Execution Promise

Two runs of the same story with identical provider, model and temperature MAY render **different**
prompts when the project changed in between, and each version MUST keep the text it actually
sent. Comparing two versions MUST be done over their stored prompts and snapshots — stored
facts — and no behaviour MAY promise that re-running a configuration reproduces an earlier
prompt.

#### Scenario: Identical configuration, changed project, different prompts

- **GIVEN** a first run of a story with provider, model and temperature P, and a project change
  — a new story, new tasks or an edited description — completed before a second run of the same
  story with the same P
- **WHEN** the two versions' stored prompts are compared
- **THEN** the prompts differ, because the project context they injected differs
- **AND** each version's stored prompt is exactly the text its own run sent

#### Scenario: The comparison never re-executes

- **GIVEN** two completed versions of the same story
- **WHEN** a reader wants to know why their outputs differ
- **THEN** the answer is read from the two versions' stored prompts and snapshots
- **AND** no step requires or assumes that re-running either configuration would reproduce the
  other's prompt

### Requirement: Both Bench Outcomes Are Honest and Both Are Recorded

The change's verification MUST run both bench obligations and record which outcome each landed
in: the **1 / 50 / 200**-story ladder against a Neon-like database — never the dev pooler —
measuring prompt size, duration and usage when present; and the mandatory **1000**-story project
built through the CSV import, proving the unpaginated context read does not truncate where the
API's page cap would. For either run, exactly two outcomes are legitimate: the measured size and
duration are recorded, **or** the provider rejects the prompt and that run consumes a version
number while producing nothing — recorded as a measured outcome, never retried until it passes.
1000 stories MUST be stated as a **floor**, because the CSV import cap is per uploaded file and
a second import crosses it. No input cap, truncation or input-side pagination MAY be introduced
to make either run pass.

#### Scenario: The ladder is recorded per project

- **GIVEN** three projects of 1, 50 and 200 stories on a Neon-like database
- **WHEN** the bench runs against each of them
- **THEN** the verification records, per project, the prompt size, the run duration and the
  token usage when the provider returned it
- **AND** no measurement was taken against the dev pooler

#### Scenario: The 1000-story bench runs and names its bound

- **GIVEN** a project with 1000 stories created through the CSV import
- **WHEN** the bench runs against it
- **THEN** the verification records the outcome — measured size and duration, or provider
  rejection
- **AND** the record states that 1000 stories came from one import and that a second import
  crosses the count, so 1000 is a floor, not a project maximum

#### Scenario: A provider rejection is a measured outcome, not a failure to retry

- **GIVEN** a project whose composed prompt exceeds the provider's context window
- **WHEN** the bench run attempts extraction on it
- **THEN** the run consumes a version number and produces no tasks
- **AND** the verification records that outcome with the real numbers as the annotated known
  limitation, rather than retrying the run until it passes

#### Scenario: Nothing was added to make a run pass

- **GIVEN** both benches completed
- **WHEN** the extraction path is inspected
- **THEN** no input token cap, no truncation and no input-side pagination were introduced
  anywhere between the story text and the provider call
