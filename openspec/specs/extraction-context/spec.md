# extraction-context Specification

## Requirements

### Requirement: The Prompt Carries the Project's Name and Description As They Are at Render Time

The rendered prompt of an extraction run MUST contain the project's name and the project's
description exactly as they are at the moment the prompt is rendered, so the provider decomposes
the story knowing which project it belongs to. A description edited after a run MUST NOT alter
what that run's prompt contained.

#### Scenario: Name and description appear in the rendered prompt

- **GIVEN** a project named "Billing Platform" whose description is "Invoicing for small businesses"
- **WHEN** an extraction run renders its prompt for a story of that project
- **THEN** the rendered prompt contains "Billing Platform" and "Invoicing for small businesses"

#### Scenario: A later description edit does not rewrite an earlier prompt

- **GIVEN** a completed run rendered while the project description read "Invoicing for small businesses"
- **WHEN** the project description is edited and a second run renders its prompt for the same story
- **THEN** the second prompt contains the new description
- **AND** the first version's stored prompt still contains the description as it was at its render time

### Requirement: The Prompt Carries the Project's Other Stories and Existing Tasks

The rendered prompt MUST contain the text of the project's **other** user stories and the
project's existing tasks — each task's title and the story it belongs to — so the
provider sees what the project already says and has already produced.

> **[Amended 2026-10-07 by owner decision]** This sentence also demanded each task's **status**,
> which the default template never rendered (`grep -c status task_generation.j2` → 0). The change's
> own task list never asked for it: task 1.6 builds the block without naming it, and task 1.7's RED
> case pins "each existing task's title *with its owning story*". The code therefore matches what
> was specified, implemented and tested, and the requirement was promising more. It is trimmed to
> what the change specified. Consequence, recorded rather than implied: **this one block is no
> longer byte-identical to the archived delta of slice (c)**, deliberately.

#### Scenario: The other stories' text appears

- **GIVEN** a project with three stories and the run is extracting the third
- **WHEN** the prompt is rendered
- **THEN** the rendered prompt contains the raw text of the first and second stories

#### Scenario: The existing tasks appear with their owning story

- **GIVEN** a project where another story's completed run produced the tasks "Set up database
  schema" (done) and "Implement listing API" (in progress)
- **WHEN** the prompt is rendered for a different story of that project
- **THEN** the rendered prompt contains both task titles, each associated with its owning story

### Requirement: The Story Being Extracted Never Appears as Its Own Context

The rendered prompt MUST NOT contain the story being extracted in the existing-tasks block in
**any** of its versions, and MUST NOT contain that story's own text among the other stories'
context — if the story entered as its own context, the model would see an answer before
responding.

#### Scenario: The story's previous versions' tasks are absent from the existing-tasks block

- **GIVEN** a story whose completed v1 produced the task "Implement login retry"
- **WHEN** a new run renders its prompt for that story
- **THEN** "Implement login retry" does not appear in the existing-tasks block of the rendered
  prompt, although it is a task of the project

#### Scenario: The story's own text is absent from the other-stories context

- **GIVEN** a story whose raw text reads "As a user, I want to log in so that I can access my account"
- **WHEN** the prompt is rendered for that story
- **THEN** the other-stories context of the rendered prompt does not contain that text
- **AND** the story text appears only once, as the story to decompose

#### Scenario: Other stories' tasks still appear

- **GIVEN** the same project as the previous scenario, where a **different** story holds the task
  "Set up database schema"
- **WHEN** the prompt is rendered for the story being extracted
- **THEN** "Set up database schema" does appear in the existing-tasks block

### Requirement: No Invalid Task Appears as Positive Context

A task carrying an active invalid mark anywhere in the project MUST NOT appear anywhere in the
rendered prompt as positive context — not among the existing tasks, not inside any story's
context. An invalid task reaches the prompt only through the negative-example block.

#### Scenario: A marked task of another story is absent from positive context

- **GIVEN** a task of another story in the project with an active invalid mark
- **WHEN** the prompt is rendered
- **THEN** that task's title does not appear in the existing-tasks block or in any story's context
- **AND** it appears, if anywhere, only in the negative-examples block with its reason

#### Scenario: Revoking the mark lets the task return as positive context

- **GIVEN** the same task whose mark was revoked while its version was still current
- **WHEN** a later run renders its prompt
- **THEN** the task's title appears in the existing-tasks block again
- **AND** it no longer appears in the negative-examples block

### Requirement: The Negative Examples Are the Marks of All Previous Versions of That Story

The prompt of version `n+1` MUST present, as explicit negative examples, every task marked
invalid in **all** previous versions of the story being extracted, each with its mark's reason.
A mark recorded on another story MUST NOT appear in this story's negative-example block, and an
invalid task MUST NOT appear as positive context anywhere else in the prompt.

#### Scenario: The prompt of v3 carries the marks of v1 and v2

- **GIVEN** a story where v1 has a task marked invalid with reason "Duplicates the auth task" and
  v2 has a task marked invalid with reason "Too coarse to implement"
- **WHEN** a run renders its prompt for that story
- **THEN** the negative-example block of the rendered prompt contains both task titles, each with
  its reason, presented as tasks not to produce

#### Scenario: A mark on one story never appears in another story's prompt

- **GIVEN** a marked task on story A and an extraction run on story B of the same project
- **WHEN** story B's prompt is rendered
- **THEN** the negative-example block of that prompt does not contain story A's mark
- **AND** the marked task does not appear as positive context in story B's prompt

### Requirement: The Negative-Example Block Is Capped at Twenty, Most Recent First, Deduplicated and Self-Announcing

The negative-example block MUST carry at most **20** examples, ordered most recent `marked_at`
first and deduplicated by normalized task title and reason. When it truncates, the block MUST
close with a sentence, in the template's English, that announces the omission and the count of
omitted older marks, and that count MUST be recorded in the run's snapshot. The cap of 20 MUST
be a constant of the feature: no workspace configuration MAY change it, and a workspace setting
that would is out of scope for 0.9.0.

#### Scenario: Twenty-one marks yield twenty examples and an announced omission

- **GIVEN** a story with 21 marks of distinct normalized title-and-reason pairs across its
  previous versions
- **WHEN** the next run renders its prompt
- **THEN** the negative-example block carries exactly 20 examples, most recent first
- **AND** the block announces that 1 older mark was omitted
- **AND** the run's snapshot records `negative_examples_omitted` equal to 1

#### Scenario: Identical title and reason deduplicate to one entry

- **GIVEN** two marks in previous versions whose normalized titles and reasons are identical
- **WHEN** the negative-example block is composed
- **THEN** the block contains one entry for that pair
- **AND** the most recent `marked_at` of the two is the one kept

#### Scenario: The most recent mark comes first

- **GIVEN** an older mark and a newer mark on two tasks of the story's previous versions
- **WHEN** the negative-example block is rendered
- **THEN** the newer mark's entry appears before the older one

#### Scenario: No workspace configuration can raise the cap

- **GIVEN** a workspace whose few-shot `limit` is configured above 20 and a story with 25 marks
  of distinct title-and-reason pairs
- **WHEN** the next run renders its prompt
- **THEN** the block still carries exactly 20 examples and announces the 5 omitted
- **AND** no workspace configuration field exists that changes the cap

### Requirement: The Context Is Read Unpaginated, With the Story Exclusion in the Query

The project context MUST be composed from exactly two unpaginated project-scoped reads — one for
the other stories' text, one for the existing tasks — whose statements carry the exclusion of the
story being extracted in their `WHERE` clause, never as a filter applied afterwards. The
API's standard page window (default 20, cap 100) MUST NOT bound either read, so a project larger
than one page is not silently truncated in the prompt.

#### Scenario: A project of 1000 stories is fully present in the prompt

- **GIVEN** a project with 1000 stories created through the CSV import
- **WHEN** an extraction run renders its prompt for one of them
- **THEN** the other-stories context contains all 999 remaining stories' text
- **AND** the number of stories in the block equals the project's story count minus one

#### Scenario: A project larger than the API page cap is not truncated

- **GIVEN** a project with 120 stories — more than the API's page cap of 100
- **WHEN** the prompt is rendered for one of them
- **THEN** all 119 other stories appear in the context
- **AND** no story is silently dropped

#### Scenario: The same project state composes the same context

- **GIVEN** a project whose stories, tasks and marks have not changed between two runs
- **WHEN** both runs render their prompts
- **THEN** the two context blocks are identical, in the same deterministic order

### Requirement: A Workspace-Authored Template Opts Out of the New Blocks

A workspace that overrides the instruction template with its own text that does not reference
the new context variables MUST get a rendered prompt **without** the project-context and
negative-example blocks — the workspace's own template is its own text, and the product does not
inject blocks a template does not ask for. Such a run MUST still succeed, its snapshot MUST
still record the context that was composed for it, and the stored rendered prompt MUST remain
the authority on what the provider actually received — so the divergence is readable in the
version's record, never silent.

#### Scenario: A custom template without the variables renders no context blocks

- **GIVEN** a workspace whose `instruction_template` carries its own text and references only the
  story variable
- **WHEN** a run renders its prompt for that workspace
- **THEN** the rendered prompt contains no project-context block and no negative-example block
- **AND** the run completes normally

#### Scenario: The divergence stays readable in the version's record

- **GIVEN** the same custom-template workspace and a completed run
- **WHEN** the version's snapshot is read
- **THEN** the snapshot records the project context and the negative examples that were composed
  for the run
- **AND** the stored rendered prompt shows the provider received neither block
