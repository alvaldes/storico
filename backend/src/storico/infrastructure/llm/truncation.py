"""Shared message for an answer the output budget cut short.

Every adapter that can observe its own truncation signal raises the classification
through ``LLMResponseError`` — an ``LLMError``, so ``run_background_extraction``
marks the run ``failed`` on the deterministic path and never retries it
(``odd/tasks/extraction-truncation.md``, S1/S3). One builder keeps the wording
identical across providers: this text is what ``error_info`` carries to the UI,
and the contract (S2) is that it names the budget (``max_tokens``) and says
raising it is the fix, whatever the provider called its own signal.
"""

from __future__ import annotations


def truncated_response_message(signal: str, max_tokens: int) -> str:
    """Compose the truncation failure message.

    ``signal`` is the provider's own report, spelled as it travels on the wire
    (``finish_reason: length``, ``done_reason: length``,
    ``finish_reason: MAX_TOKENS``, ``stop_reason: max_tokens``) so the reader
    can check the claim against the source.
    """
    return (
        "The provider stopped the answer at the output budget "
        f"({signal}, max_tokens: {max_tokens}): the task list was cut off. "
        "Raise max tokens in Workspace Settings and run the extraction again."
    )
