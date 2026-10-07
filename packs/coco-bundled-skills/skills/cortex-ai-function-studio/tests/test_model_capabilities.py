# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Unit tests for model capabilities scripts (fetch + diff).

Run:
    uv run --group test pytest tests/test_model_capabilities.py -v
"""

from __future__ import annotations

from dev.models.diff_capabilities import diff_capabilities, format_slack, format_text
from dev.models.fetch_capabilities import (
    _extract_model_configs_section,
    _match_family,
    enrich_capabilities,
    parse_corvo_config,
)

# =============================================================================
# Fixtures
# =============================================================================

MINIMAL_CORVO_YAML = """\
text_completion:
  model_configs:
    - model_details:
        name: claude-sonnet-4-6
      max_output_tokens: 8192
      max_input_images: 20
      max_input_documents: 5
      model_capabilities:
        image_input: true
    - model_details:
        name: llama3.1-70b
      max_output_tokens: 4096
    - model_details:
        name: pixtral-large
      max_input_images: 8
      max_output_tokens: 4096
    - model_details:
        name: gemini-2.5-flash
      max_input_images: 20
      max_input_documents: 20
"""

CORVO_WITH_GO_TEMPLATES = """\
text_completion:
  model_configs:
    - model_details:
        name: claude-sonnet-4-6
      max_input_images: 20
      max_input_documents: 5
<<<- if .IsPreprod >>>
    - model_details:
        name: preprod-only-model
      max_input_images: 5
<<<- end >>>
    - model_details:
        name: pixtral-large
      max_input_images: 8
"""


# =============================================================================
# parse_corvo_config tests
# =============================================================================


class TestParseCorvoConfig:
    def test_extracts_multimodal_models(self):
        result = parse_corvo_config(MINIMAL_CORVO_YAML)
        # claude-sonnet-4-6: images + docs
        assert "claude-sonnet-4-6" in result
        assert result["claude-sonnet-4-6"]["max_input_images"] == 20
        assert result["claude-sonnet-4-6"]["max_input_documents"] == 5

        # pixtral-large: images only
        assert "pixtral-large" in result
        assert result["pixtral-large"]["max_input_images"] == 8
        assert "max_input_documents" not in result["pixtral-large"]

        # gemini-2.5-flash: images + docs
        assert "gemini-2.5-flash" in result
        assert result["gemini-2.5-flash"]["max_input_images"] == 20
        assert result["gemini-2.5-flash"]["max_input_documents"] == 20

    def test_excludes_text_only_models(self):
        result = parse_corvo_config(MINIMAL_CORVO_YAML)
        assert "llama3.1-70b" not in result

    def test_handles_go_templates(self):
        result = parse_corvo_config(CORVO_WITH_GO_TEMPLATES)
        # Both prod and preprod models are extracted (filtering happens later)
        assert "claude-sonnet-4-6" in result
        assert "pixtral-large" in result
        # Preprod model also appears (since we just strip directives)
        assert "preprod-only-model" in result

    def test_only_emits_nonzero_fields(self):
        result = parse_corvo_config(MINIMAL_CORVO_YAML)
        # pixtral-large has no document support
        assert "max_input_documents" not in result["pixtral-large"]
        # claude has both
        assert "max_input_images" in result["claude-sonnet-4-6"]
        assert "max_input_documents" in result["claude-sonnet-4-6"]


# =============================================================================
# _extract_model_configs_section tests
# =============================================================================


class TestExtractModelConfigsSection:
    def test_extracts_section(self):
        section = _extract_model_configs_section(MINIMAL_CORVO_YAML)
        assert section.startswith("model_configs:")
        assert "claude-sonnet-4-6" in section
        assert "pixtral-large" in section

    def test_returns_empty_for_missing_section(self):
        yaml_without_models = "embedding:\n  models:\n    - name: foo\n"
        section = _extract_model_configs_section(yaml_without_models)
        assert section == ""

    def test_stops_at_sibling_key(self):
        yaml_with_sibling = """\
text_completion:
  model_configs:
    - model_details:
        name: model-a
      max_input_images: 5
  guard_configs:
    - name: some-guard
"""
        section = _extract_model_configs_section(yaml_with_sibling)
        assert "model-a" in section
        assert "guard_configs" not in section
        assert "some-guard" not in section


# =============================================================================
# _match_family tests
# =============================================================================


class TestMatchFamily:
    def test_returns_first_match(self):
        mapping = {
            r"^gemini-3\.1-pro": 3000,
            r"^gemini": 1000,
        }
        assert _match_family("gemini-3.1-pro", mapping) == 3000
        assert _match_family("gemini-2.5-flash", mapping) == 1000

    def test_returns_none_for_unknown(self):
        mapping = {
            r"^claude": "claude-family",
            r"^gemini": "gemini-family",
        }
        assert _match_family("llama3.1-70b", mapping) is None

    def test_catchall_matches_anything(self):
        mapping = {
            r"^claude": "specific",
            r".*": "default",
        }
        assert _match_family("claude-sonnet-4-6", mapping) == "specific"
        assert _match_family("unknown-model", mapping) == "default"


# =============================================================================
# enrich_capabilities tests
# =============================================================================


class TestEnrichCapabilities:
    def test_filters_to_shipped_models(self):
        raw_caps = {
            "claude-sonnet-4-6": {"max_input_images": 20, "max_input_documents": 5},
            "not-shipped-model": {"max_input_images": 10},
        }
        shipped = {"claude-sonnet-4-6", "llama3.1-70b"}
        result = enrich_capabilities(raw_caps, shipped)
        assert "claude-sonnet-4-6" in result
        assert "not-shipped-model" not in result

    def test_adds_image_metadata(self):
        raw_caps = {"pixtral-large": {"max_input_images": 8}}
        shipped = {"pixtral-large"}
        result = enrich_capabilities(raw_caps, shipped)

        caps = result["pixtral-large"]
        assert caps["max_file_size_mb_images"] == 10.0
        assert "bmp" in caps["supported_image_formats"]

    def test_adds_document_metadata(self):
        raw_caps = {
            "claude-sonnet-4-6": {"max_input_images": 20, "max_input_documents": 5}
        }
        shipped = {"claude-sonnet-4-6"}
        result = enrich_capabilities(raw_caps, shipped)

        caps = result["claude-sonnet-4-6"]
        assert caps["max_file_size_mb_documents"] == 22.0
        assert caps["max_document_pages"] == 100
        assert "pdf" in caps["supported_document_formats"]
        assert "docx" in caps["supported_document_formats"]

    def test_image_only_model_has_no_document_fields(self):
        raw_caps = {"openai-gpt-5.2": {"max_input_images": 5}}
        shipped = {"openai-gpt-5.2"}
        result = enrich_capabilities(raw_caps, shipped)

        caps = result["openai-gpt-5.2"]
        assert "max_input_documents" not in caps
        assert "max_file_size_mb_documents" not in caps
        assert "max_document_pages" not in caps
        assert "supported_document_formats" not in caps


# =============================================================================
# diff_capabilities tests
# =============================================================================


class TestDiffCapabilities:
    def test_detects_added_models(self):
        old = {}
        new = {"new-model": {"max_input_images": 5}}
        result = diff_capabilities(old, new)
        assert "new-model" in result["added"]
        assert result["removed"] == {}
        assert result["changed"] == {}

    def test_detects_removed_models(self):
        old = {"old-model": {"max_input_images": 10}}
        new = {}
        result = diff_capabilities(old, new)
        assert "old-model" in result["removed"]
        assert result["added"] == {}

    def test_detects_changed_fields(self):
        old = {"model-a": {"max_input_images": 5, "max_input_documents": 3}}
        new = {"model-a": {"max_input_images": 10, "max_input_documents": 3}}
        result = diff_capabilities(old, new)
        assert "model-a" in result["changed"]
        assert result["changed"]["model-a"]["max_input_images"] == {"old": 5, "new": 10}
        assert "max_input_documents" not in result["changed"]["model-a"]

    def test_counts_unchanged(self):
        old = {"model-a": {"max_input_images": 5}}
        new = {"model-a": {"max_input_images": 5}}
        result = diff_capabilities(old, new)
        assert result["unchanged"] == 1
        assert result["added"] == {}
        assert result["removed"] == {}
        assert result["changed"] == {}

    def test_format_text_no_changes(self):
        result = diff_capabilities({"a": {"x": 1}}, {"a": {"x": 1}})
        text = format_text(result)
        assert "No changes detected" in text

    def test_format_slack_with_changes(self):
        old = {"model-a": {"max_input_images": 5}}
        new = {"model-a": {"max_input_images": 10}, "model-b": {"max_input_images": 3}}
        result = diff_capabilities(old, new)
        slack = format_slack(result)
        assert "`model-b`" in slack
        assert "`model-a`" in slack
        assert "→" in slack  # unicode arrow in change description
