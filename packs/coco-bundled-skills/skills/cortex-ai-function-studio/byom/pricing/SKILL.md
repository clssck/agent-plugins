---
name: cortex-ai-function-studio-byom-pricing
summary: "Estimate BYOM/SPCS model cost from measured throughput and SPCS credit consumption instead of Cortex-hosted token pricing."
description: "Use when estimating BYOM model cost, comparing BYOM against Cortex-hosted models, building Pareto frontiers involving SPCS services, or explaining BYOM/SPCS pricing after an AI function or service is created."
---
<!-- Copyright (c) 2026 Snowflake Inc. All rights reserved.
     Licensed under the Snowflake Skills License. See LICENSE file. -->

# Bring your own Model SPCS Pricing

Use this reference whenever Bring your own Model/SPCS model cost appears in model selection, optimization, evaluation, Pareto filtering, or post-deployment review.

## Core Rule

Bring your own Model services are hosted on Snowpark Container Services (SPCS), so do **not** price them with Cortex-hosted model token rates from `src/models.json`. Bring your own Model cost is based on SPCS compute consumption for the model service's compute pool and service runtime.

For Bring your own Model candidates, estimate cost from measured service throughput plus the SPCS credit rate for the service compute pool instance family.

## Inputs To Collect

- Fully qualified AI function name or direct `AI_COMPLETE('<service_name>', ...)` call path.
- Bring your own Model service/model identifier used in `AI_COMPLETE`.
- Compute pool name and instance family for the SPCS service.
- Service min/max instances and currently running instance count, if available.
- Representative sample table and input columns.
- Approximate output-token length or measured output text length.
- SPCS credit rate per hour for the compute pool instance family.

## Credit Rate Source

Do not invent SPCS credit rates. Use one of these sources, in order:

1. **Account usage history for the actual service/compute pool** when enough recent data exists. Query `SNOWFLAKE.ACCOUNT_USAGE.SNOWPARK_CONTAINER_SERVICES_HISTORY` or service/notebook container runtime history views to find recent `CREDITS` by hour for the target service or compute pool.
2. **Snowflake consumption table / pricing calculator for the instance family** when usage history is not available yet. Use Glean or official Snowflake docs to locate the current consumption table, then cite the exact instance family and credit/hour rate in the user-facing estimate.
3. **Ask the user/admin for the approved internal credit/hour rate** if neither usage history nor a current consumption table is available.

If no credible credit/hour rate is available, present throughput metrics and say cost cannot be converted to credits yet.

## Measurement Procedure

After the Bring your own Model function/service is created and callable, run a small benchmark before presenting Bring your own Model cost:

1. Select about **20 representative samples** from the user's eval/test/training table.
2. Run the function or `AI_COMPLETE` service call on those samples.
3. Measure wall-clock time from immediately before the first call to after the final result returns.
4. Record:
   - `sample_count`
   - elapsed seconds
   - requests per second: `rps = sample_count / elapsed_seconds`
   - approximate input tokens
   - approximate output tokens
   - approximate total tokens processed
5. Estimate throughput:
   - `tokens_per_second = total_tokens_processed / elapsed_seconds`
   - `tokens_per_hour = tokens_per_second * 3600`
6. Add **5 minutes of warm-up overhead** to the cost estimate:
   - `billable_hours = (elapsed_seconds + 300) / 3600` for one-shot benchmark cost
   - For steady-state per-hour estimates, present warm-up separately as `5 minutes × credit_rate_per_hour`.
7. Convert to credits:
   - `benchmark_credits = credit_rate_per_hour * running_instance_count * billable_hours`
   - `credits_per_1k_requests = benchmark_credits / sample_count * 1000`
   - `credits_per_1M_tokens = credit_rate_per_hour * running_instance_count / (tokens_per_hour / 1_000_000)`

If service autoscaling is enabled and running instances vary, use the measured or expected average running instance count. If unknown, estimate with `min_instances` and clearly label it as conservative/approximate.

## Token Estimation

Use exact token counts if available from logs or model metadata. If not available, use an approximation and label it:

- `input_tokens ≈ input_characters / 4`
- `output_tokens ≈ output_characters / 4`

Do not claim token counts are exact unless they were measured by the service/model.

## User-Facing Output

Present Bring your own Model cost as measured/estimated SPCS compute economics, not Cortex token pricing:

- Service/model name
- Compute pool and instance family
- Credit/hour source used
- Sample count and elapsed time
- RPS
- Estimated tokens/hour
- 5-minute warm-up credit overhead
- Estimated credits per 1K requests and/or per 1M tokens
- Caveats: warm-up, autoscaling, batch size, input/output length, and whether token counts are approximate

Use wording like:

> Bring your own Model is hosted on SPCS, so the cost estimate is based on measured throughput and the compute pool's credit/hour rate, not Cortex model token pricing.

## Pareto / Optimize Integration

When comparing Bring your own Model against Cortex-hosted models:

- Keep Cortex-hosted model costs from `src/models.json`.
- Replace Bring your own Model `src/models.json` token-cost assumptions with measured SPCS throughput economics from this reference.
- If Bring your own Model throughput has not been measured yet, mark Bring your own Model cost as `needs measurement` and do not rank it as cheaper/more expensive solely from token list prices.
- Always include the current Bring your own Model candidate in the optimization result comparison if the function uses Bring your own Model, unless the user explicitly excluded it.
