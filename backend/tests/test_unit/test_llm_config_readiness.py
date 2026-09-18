"""Unit tests for the workspace LLM configuration completeness rule.

The rule is pure data plus a membership test, so these tests exercise it without a
database session, a settings object, or a provider SDK. What matters is that the
missing fields are named exactly, in a stable order, and that the vocabulary the API
reports is the one the frontend mirrors.
"""

from __future__ import annotations

import pytest

from storico.domain.services.llm_config_readiness import (
    CUSTOM_PROVIDER_REQUIRED_FIELDS,
    LLM_CONFIG_INCOMPLETE_CODE,
    READINESS_FIELDS,
    REQUIRED_FIELDS_BY_PROVIDER,
    llm_config_is_complete,
    missing_llm_config_fields,
    normalize_optional,
    required_fields_for,
)


class TestRequiredFields:
    """Which fields each provider family cannot be called without."""

    @pytest.mark.unit
    @pytest.mark.parametrize("provider", ["ollama", "openai", "anthropic", "gemini"])
    def test_every_known_provider_declares_its_requirements(self, provider: str) -> None:
        """A known provider's requirements come from the table, never from the fallback."""
        assert required_fields_for(provider) == REQUIRED_FIELDS_BY_PROVIDER[provider]

    @pytest.mark.unit
    def test_ollama_needs_only_a_model(self) -> None:
        """Ollama's host falls back to the configured default, so no base URL is required."""
        assert required_fields_for("ollama") == ("model",)

    @pytest.mark.unit
    @pytest.mark.parametrize("provider", ["openai", "anthropic", "gemini"])
    def test_cloud_providers_need_a_model_and_a_key(self, provider: str) -> None:
        """A cloud provider with no workspace credential must never borrow an ambient one."""
        assert required_fields_for(provider) == ("model", "api_key")

    @pytest.mark.unit
    @pytest.mark.parametrize("provider", ["deepseek", "My Gateway v2", "", "OLLAMA"])
    def test_anything_unknown_is_a_custom_provider(self, provider: str) -> None:
        """Routing sends every unrecognised name to the OpenAI-compatible adapter.

        The empty name and the mis-cased built-in are in the list on purpose: this
        function answers, it never raises, and it must not quietly treat a name that
        only *looks* like a built-in as one — routing compares exactly.
        """
        assert required_fields_for(provider) == CUSTOM_PROVIDER_REQUIRED_FIELDS

    @pytest.mark.unit
    def test_custom_providers_need_an_endpoint_not_a_key(self) -> None:
        """A self-hosted gateway commonly accepts unauthenticated requests."""
        assert required_fields_for("deepseek") == ("model", "base_url")


class TestMissingFields:
    """Which required fields a concrete configuration is missing."""

    @pytest.mark.unit
    def test_a_complete_ollama_configuration_has_no_gaps(self) -> None:
        """The model is the whole requirement."""
        assert missing_llm_config_fields("ollama", model="llama3.2") == ()

    @pytest.mark.unit
    def test_a_missing_model_is_reported_alone(self) -> None:
        """An unset model is the only gap when everything else is present."""
        assert missing_llm_config_fields("openai", api_key="sk-test") == ("model",)

    @pytest.mark.unit
    def test_both_gaps_are_reported_in_vocabulary_order(self) -> None:
        """Order is stable and follows READINESS_FIELDS, not the provider's table row."""
        assert missing_llm_config_fields("anthropic") == ("model", "api_key")

    @pytest.mark.unit
    def test_a_missing_key_is_reported_for_each_cloud_provider(self) -> None:
        """The same gap is named the same way whichever cloud provider is selected."""
        for provider in ("openai", "anthropic", "gemini"):
            assert missing_llm_config_fields(provider, model="some-model") == ("api_key",)

    @pytest.mark.unit
    def test_a_custom_provider_without_an_endpoint_is_incomplete(self) -> None:
        """The base URL is what a custom provider is unusable without."""
        assert missing_llm_config_fields("deepseek", model="deepseek-chat") == ("base_url",)

    @pytest.mark.unit
    def test_a_custom_provider_without_a_key_is_complete(self) -> None:
        """The key stays optional for a custom provider, so it is never reported."""
        assert (
            missing_llm_config_fields(
                "deepseek", model="deepseek-chat", base_url="https://api.deepseek.com/v1"
            )
            == ()
        )

    @pytest.mark.unit
    @pytest.mark.parametrize("blank", ["", "   ", "\t\n"])
    def test_a_blank_value_counts_as_unset(self, blank: str) -> None:
        """The form can leave an empty string where None would otherwise be stored."""
        assert missing_llm_config_fields("openai", model=blank, api_key=blank) == (
            "model",
            "api_key",
        )

    @pytest.mark.unit
    def test_a_padded_value_still_counts_as_set(self) -> None:
        """Only an all-whitespace value is unset; padding around a real value is not."""
        assert missing_llm_config_fields("ollama", model="  llama3.2  ") == ()

    @pytest.mark.unit
    def test_an_unconfigured_workspace_reports_its_own_provider_gaps(self) -> None:
        """No row at all resolves to Ollama, so the single gap is the model."""
        assert missing_llm_config_fields("ollama") == ("model",)

    @pytest.mark.unit
    def test_is_complete_agrees_with_the_missing_list(self) -> None:
        """The boolean is a projection of the list, never a second rule."""
        cases = [
            ("ollama", {"model": "llama3.2"}),
            ("ollama", {}),
            ("openai", {"model": "gpt-4o-mini", "api_key": "sk-test"}),
            ("openai", {"model": "gpt-4o-mini"}),
            ("gemini", {"api_key": "AIza-test"}),
            ("deepseek", {"model": "deepseek-chat", "base_url": "https://x.example/v1"}),
            ("deepseek", {"model": "deepseek-chat"}),
        ]
        for provider, values in cases:
            assert llm_config_is_complete(provider, **values) is (
                missing_llm_config_fields(provider, **values) == ()
            )


class TestNormalizeOptional:
    """The one definition of "blank means absent".

    It exists because that comparison used to be made three times with three different
    meanings, and the disagreement is what let an endpoint of spaces reach a provider.
    """

    @pytest.mark.unit
    @pytest.mark.parametrize("blank", [None, "", "   ", "\t", "\n", " \t\n "])
    def test_a_blank_value_is_absent(self, blank: str | None) -> None:
        """Nothing, and anything made only of whitespace, means "not configured"."""
        assert normalize_optional(blank) is None

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("configured", "expected"),
        [
            ("llama3.2", "llama3.2"),
            ("  llama3.2  ", "llama3.2"),
            ("http://localhost:11434", "http://localhost:11434"),
            ("  https://api.example.com/v1  ", "https://api.example.com/v1"),
        ],
    )
    def test_a_configured_value_keeps_its_content(self, configured: str, expected: str) -> None:
        """A real value survives; only the surrounding whitespace goes."""
        assert normalize_optional(configured) == expected

    @pytest.mark.unit
    def test_internal_characters_are_not_touched(self) -> None:
        """A credential is returned as configured, spaces inside it included."""
        assert normalize_optional("  sk-a b c  ") == "sk-a b c"

    @pytest.mark.unit
    def test_the_rule_and_the_normalization_cannot_disagree(self) -> None:
        """``_is_set`` is a projection of this function, so the two cannot drift.

        Asserted through the public rule: a value the normalizer calls absent must be a
        value the completeness rule reports as missing.
        """
        for candidate in (None, "", "   ", "\t\n", "real-key"):
            absent = normalize_optional(candidate) is None
            missing = missing_llm_config_fields("openai", model="m", api_key=candidate)
            assert ("api_key" in missing) is absent


class TestVocabulary:
    """The codes the API reports and the frontend mirrors."""

    @pytest.mark.unit
    def test_the_vocabulary_is_exactly_the_three_fields(self) -> None:
        """A fourth field would otherwise appear in the API without a UI home for it."""
        assert READINESS_FIELDS == ("model", "api_key", "base_url")

    @pytest.mark.unit
    def test_every_declared_requirement_uses_the_vocabulary(self) -> None:
        """No provider may require a field the wire vocabulary does not carry."""
        declared = {
            *CUSTOM_PROVIDER_REQUIRED_FIELDS,
            *(field for fields in REQUIRED_FIELDS_BY_PROVIDER.values() for field in fields),
        }
        assert declared <= set(READINESS_FIELDS)

    @pytest.mark.unit
    def test_every_provider_family_requires_a_model(self) -> None:
        """``model`` is the one field no provider can be called without.

        The extraction route relies on this: it narrows the model away from
        ``str | None`` by checking the gap list, which is only sound while every
        family requires it.
        """
        assert all("model" in fields for fields in REQUIRED_FIELDS_BY_PROVIDER.values())
        assert "model" in CUSTOM_PROVIDER_REQUIRED_FIELDS

    @pytest.mark.unit
    def test_the_error_code_is_the_one_the_frontend_maps(self) -> None:
        """The spelling is wire vocabulary; the mirror guard pins the frontend's copy."""
        assert LLM_CONFIG_INCOMPLETE_CODE == "LLM_CONFIG_INCOMPLETE"
