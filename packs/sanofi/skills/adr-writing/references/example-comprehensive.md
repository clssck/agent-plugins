# Adopt Step Functions for Order Processing Orchestration

* Status: accepted
* Deciders: Dana Park, Eric Holm, Fatima Al-Rashid
* Date: 2025-09-18

Technical Story: [ORDERS-1042](https://sanofi.atlassian.net/browse/ORDERS-1042)

## Context and Problem Statement

How should we orchestrate the 7-step order processing pipeline (validate, reserve
inventory, charge payment, fulfill, notify, update analytics, emit events) given
our requirements for per-step retry, at-least-once delivery, and auditability of
every state transition?

## Decision Outcome

Chosen option: "AWS Step Functions (Standard)", because it provides built-in
per-step retry with exponential backoff, a visual execution audit trail, and
native integration with the Lambda functions we already use for each step.

Option B (custom SQS choreography) was not selected because it requires building
retry, dead-letter routing, and execution tracing from scratch — estimated at
6 weeks of engineering effort for parity with Step Functions' built-in features.

Option C (MWAA/Airflow) was ruled out — see Options Ruled Out.

### Positive Consequences

* Per-step retry and error handling are declarative, not custom code
* Execution history provides full audit trail without additional instrumentation
* New steps can be added by editing the state machine definition — no plumbing changes

### Negative Consequences

* Standard StateTransition throughput is a soft per-account, per-Region quota (5,000/s in Ireland); peak load must stay below it or a quota increase must be requested
* Team needs to learn Amazon States Language (ASL) — estimated 1-week ramp-up
* Vendor lock-in: migrating away from Step Functions would require rewriting orchestration logic

## Decision Drivers

| Driver                | Description                                                    |
| --------------------- | -------------------------------------------------------------- |
| Per-step retry        | Each step must independently retry with configurable backoff   |
| Auditability          | Regulators require a full trace of every order state change    |
| Operational overhead  | Small team (3 engineers) cannot maintain custom infrastructure |
| Time to market        | MVP must ship in 4 weeks                                       |

## Considered Options

* AWS Step Functions (Standard)
* Custom SQS-based choreography

### AWS Step Functions (Standard)

Managed orchestration service using state machine definitions (ASL) to
coordinate Lambda functions with built-in retry, parallel execution, and
execution history.

* **Pros**
  * Good, because per-step retry with exponential backoff is declarative (no custom code)
  * Good, because execution history provides audit trail for compliance (SOX)
  * Good, because native Lambda integration eliminates glue code
  * Good, because visual workflow editor accelerates debugging
* **Cons**
  * Bad, because Standard workflow cost is $0.025 per 1,000 state transitions — at 500K orders/month (est. 3.5M transitions) this is ~$87.50/month
  * Bad, because StateTransition throughput is throttled per account and Region (5,000/s in Ireland, 800/s in most other Regions); the assumed peak of 100 orders/s × 7 transitions = 700/s fits, but other state machines in the account share the bucket
  * Bad, because Amazon States Language has a learning curve for the team

### Custom SQS-Based Choreography

Event-driven architecture using SQS queues between Lambda functions, with
manual retry logic and dead-letter queues for failure handling.

* **Pros**
  * Good, because SQS is inexpensive at our volume (~$4.20/month: 3.5M messages × 3 billable requests each — send, receive, delete — at $0.40/1M, before free tier and batching)
  * Good, because no vendor-specific orchestration language — standard Lambda code
* **Cons**
  * Bad, because per-step retry requires custom code in each Lambda (estimated 2 weeks to build)
  * Bad, because audit trail requires custom instrumentation across 7 queues (estimated 2 weeks)
  * Bad, because debugging failed orders requires correlating logs across 7 independent functions
  * Bad, because adding a new step requires updating queue subscriptions, retry logic, and DLQ configuration

## Architecture Manifesto Alignment

| # | Principle              | Alignment | Notes                                                                        |
| - | ---------------------- | --------- | ---------------------------------------------------------------------------- |
| 2 | Simplicity             | Aligned   | Declarative orchestration replaces ~2,000 lines of custom retry/routing code |
| 4 | Quality by Design      | Aligned   | Built-in retry and audit trail satisfy SOX compliance from day one           |
| 6 | Decoupling             | Aligned   | Each step is an independent Lambda; orchestration logic is external          |
| 8 | Performance            | Partial   | Assumed 700 transitions/s peak fits the 5,000/s Ireland quota; 10x growth needs a quota increase |
| 9 | Automation             | Aligned   | State machine definition is IaC-compatible (CDK/CloudFormation)              |
| 10 | Frugality             | Tension   | ~$87.50/month vs ~$4.20/month for SQS — accepted because the SQS option needs ~$60K of build effort |

## Options Ruled Out

### MWAA (Managed Apache Airflow)

Not viable because each order must start processing as soon as it arrives, at an assumed
peak of 100 orders/s. Airflow runs are created and queued by the scheduler, so one DAG run
per order adds scheduler and worker queueing latency to every order and puts high-frequency
run creation on a component designed for batch workflows
([Airflow scheduler](https://airflow.apache.org/docs/apache-airflow/stable/administration-and-deployment/scheduler.html)).

The SQS queue MWAA provisions per environment is its internal task queue
([MWAA FAQs](https://docs.aws.amazon.com/mwaa/latest/userguide/mwaa-faqs.html)). It does not
stop DAGs from using our own business queues (for example the Amazon provider's `SqsSensor`
and `SqsPublishOperator`), so queue integration was not the blocker.

## Cost Annex

### Component Pricing

| Component              | Rate                           | Source                                                                 |
| ---------------------- | ------------------------------ | ---------------------------------------------------------------------- |
| Step Functions Standard | $0.025 / 1,000 transitions    | [AWS pricing](https://aws.amazon.com/step-functions/pricing/)          |
| SQS Standard           | $0.40 / 1M requests (send, receive, delete each billed) | [AWS pricing](https://aws.amazon.com/sqs/pricing/) |
| Lambda invocations     | $0.20 / 1M requests           | [AWS pricing](https://aws.amazon.com/lambda/pricing/)                  |

### Scenario Comparison

Lambda invocation cost is the same in both options (7 invocations per order) and is excluded.
SQS assumes 3 requests per message, no batching, no retries, and ignores the free tier.

| Scenario               | Step Functions    | Custom SQS       |
| ---------------------- | ----------------- | ----------------- |
| 500K orders/month      | $87.50/month      | ~$4.20/month      |
| 2M orders/month        | $350/month        | ~$16.80/month     |
| Engineering build cost | 0 weeks (built-in) | 6 weeks (~$60K)  |
| Months of run-cost savings to repay SQS build cost | — | ~720 at 500K/month (~$83/month saved); ~180 at 2M/month |

## Links

* [ORDERS-1042](https://sanofi.atlassian.net/browse/ORDERS-1042) — Epic: Order Processing Pipeline
* [ADR-008-use-lambda-for-compute.md](ADR-008-use-lambda-for-compute.md) — Prior decision on Lambda adoption
* [Step Functions service quotas](https://docs.aws.amazon.com/step-functions/latest/dg/service-quotas.html)
