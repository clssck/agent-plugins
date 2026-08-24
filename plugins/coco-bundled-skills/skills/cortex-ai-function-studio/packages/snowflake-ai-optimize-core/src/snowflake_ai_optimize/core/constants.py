# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Shared constants and type definitions for the snowflake_ai_optimize family."""

from __future__ import annotations

# Query tag key used by AI function logging infrastructure.
CUSTOM_AI_FUNCTION_TAG_PREFIX: str = "__CUSTOM_AI_FUNCTION_LOG_"

# Query tag key used to correlate Cortex Code sessions with AI function calls.
COCO_SESSION_TAG_PREFIX: str = "__CUSTOM_AI_FUNCTION_COCO_SESSION_ID_"

# Maximum retry attempts for temporary AI function creation.
TEMP_AI_FUNCTION_MAX_ATTEMPTS: int = 3

# Key prefix for per-row stage entries in the inputs dictionary.
STAGE_KEY_PREFIX: str = "__STAGE_"

# Prefix prepended to file-first PROMPT templates as an AI_COMPLETE workaround.
AI_COMPLETE_FILE_PROMPT_PREFIX: str = "file: "
