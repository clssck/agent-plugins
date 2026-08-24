# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_byom_prerequisites_do_not_precheck_role_grants():
    prerequisites = (ROOT / "byom" / "prerequisites.md").read_text()

    assert "Do **not** run `SHOW GRANTS TO ROLE`" in prerequisites
    assert "execute-first posture" in prerequisites
    assert "SHOW GRANTS TO ROLE <current_role_from_previous_query>" not in prerequisites
    assert "SHOW GRANTS TO ROLE IDENTIFIER(CURRENT_ROLE())" not in prerequisites


def test_byom_session_setup_sets_only_required_parameter_directly():
    prerequisites = (ROOT / "byom" / "prerequisites.md").read_text()
    skill = (ROOT / "byom" / "SKILL.md").read_text()

    required_parameter = "ENABLE_SPCS_SERVICE_FUNCTIONS_IN_AISQL"
    bundled_parameters = [
        "SPCS_SERVICE_FUNCTION_IN_AISQL_RESOURCE_KEYWORD",
        "SPCS_MODEL_INFERENCE_PROXY_CONTAINER_URL",
    ]

    assert "Do **not** precheck whether this session parameter exists" in prerequisites
    assert "Do not precheck whether this session parameter is available" in skill
    assert "contact their account admin" in prerequisites
    assert "contact their account admin" in skill
    assert f"ALTER SESSION SET {required_parameter}" in prerequisites
    assert f"ALTER SESSION SET {required_parameter}" in skill
    for parameter in bundled_parameters:
        assert f"ALTER SESSION SET {parameter}" not in prerequisites
        assert f"ALTER SESSION SET {parameter}" not in skill


# Section header that lists verified BYOM models under "See all models",
# alongside the Cortex-hosted families (there is no single gateway option).
BYOM_SEE_ALL_SECTION = (
    "Bring your own Model — Hugging Face / open source (research preview)"
)
# The retired single-gateway label must not reappear in any picker.
RETIRED_BYOM_GATEWAY = (
    "[research preview] Bring your own Model (Hugging Face / open source)"
)


def test_model_selection_lists_byom_models_without_a_gateway():
    """Verified BYOM/HF models are listed under "See all models" as their own
    section next to the hosted families — not behind a single gateway option —
    and the old "stealth" posture is gone.
    """  # noqa: D205
    text = (ROOT / "references" / "model_selection.md").read_text()

    assert "See all models" in text
    assert BYOM_SEE_ALL_SECTION in text
    assert "byom/model_catalog.md" in text

    assert RETIRED_BYOM_GATEWAY not in text
    assert "stealth" not in text.lower()


def test_create_and_optimize_reach_byom_without_a_gateway():
    """Create and Optimize reach BYOM via "See all models" / an explicit ask,
    not a single gateway picker option.
    """  # noqa: D205
    create = (ROOT / "create" / "SKILL.md").read_text()
    optimize = (ROOT / "optimize" / "SKILL.md").read_text()

    for text in (create, optimize):
        assert "See all models" in text
        assert "byom/SKILL.md" in text
        assert "stealth" not in text.lower()
        assert RETIRED_BYOM_GATEWAY not in text


def test_byom_import_token_dialog_offers_create_secret_and_keeps_raw_token_rule():
    """Step 4's import token choice is a three-option dialog that includes a
    self-service "create a new secret" path, while the no-raw-token-in-chat
    security rules remain intact.
    """  # noqa: D205
    skill = (ROOT / "byom" / "SKILL.md").read_text()

    assert "three-option dialog" in skill
    assert "two-option dialog" not in skill

    # All three token choices are present.
    assert "Yes, I already have an HF token secret in Snowflake" in skill
    assert "Create a new secret from my Hugging Face token" in skill
    assert "Proceed without an HF token" in skill

    # Security rules preserved.
    assert "Do not ask for secrets in chat" in skill
    assert "Do not collect raw Hugging Face token values in chat" in skill


def test_byom_step4_autodetects_secret_and_offers_one_step_egress_setup():
    """Step 4 auto-detects an existing huggingface_token secret (so the prompt
    can be skipped) and the create-secret path offers HF egress (EAI / network
    rule) setup in the same guided step.
    """  # noqa: D205
    skill = (ROOT / "byom" / "SKILL.md").read_text()

    # Auto-detect an existing token secret before prompting.
    assert "auto-detect an existing token secret" in skill
    assert "SHOW SECRETS LIKE 'huggingface_token'" in skill

    # Offer auth + egress in one guided step.
    assert "One-step setup" in skill
    assert "auth + egress" in skill
