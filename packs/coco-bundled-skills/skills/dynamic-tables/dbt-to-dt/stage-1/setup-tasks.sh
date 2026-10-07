#!/bin/bash
# Register team + task with 5 steps for Stage 1.
set -e

cortex ctx team create team-dbt-dt-stage1

T_OUT=$(cortex ctx task add "Stage 1: CTAS → FULL DT")
T=$(echo "$T_OUT" | grep -o 'task-[a-z0-9]*')
cortex ctx task start "$T"

cortex ctx step add -t "$T" \
  "[SETUP]    1/5 Test strategy + environment" \
  "[ANALYSIS] 2/5 Model inventory" \
  "[ANALYSIS] 3/5 Conversion audit" \
  "[EXECUTE]  4/5 Convert + validate (per model)" \
  "[REPORT]   5/5 Migration summary"

echo "TASK=$T"
