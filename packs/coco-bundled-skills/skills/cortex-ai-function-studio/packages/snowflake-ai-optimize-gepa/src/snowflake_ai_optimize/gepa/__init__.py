# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""GEPA optimization package for Snowflake AI functions.

Importing this package registers the production optimize modes
("prompt" and "body") into the core mode registry.
"""

from snowflake_ai_optimize.gepa._registry import register_all

register_all()
