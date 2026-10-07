#!/bin/bash
# Register team + task with 7 steps for Stage 2 (one layer).
set -e

cortex ctx team create team-dbt-dt-stage2

T_OUT=$(cortex ctx task add "Stage 2: FULL → INC Upgrade (Layer N)")
T=$(echo "$T_OUT" | grep -o 'task-[a-z0-9]*')
cortex ctx task start "$T"

cortex ctx step add -t "$T" \
  "[SETUP]    1/7 Test strategy" \
  "[ANALYSIS] 2/7 Pipeline inventory + layer detection" \
  "[ANALYSIS] 3/7 Candidate assessment (operators + CT)" \
  "[VALIDATE] 4/7 Validation (transient INC DT check)" \
  "[REPORT]   5/7 Report + user review" \
  "[PROMOTE]  6/7 Shadow promotion (persistent _inc_shadow)" \
  "[CLEANUP]  7/7 Cleanup + next steps"

echo "TASK=$T"
