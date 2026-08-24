#!/usr/bin/env python3
# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Source the Customer 360 demo corpus and upload it to Snowflake.

Synthesizes a small B2B-SaaS customer base as SIX structured CSVs (customers, products,
transactions, daily telemetry, survey scores, campaigns) PLUS unstructured customer docs
(support tickets, chat / call transcripts, survey comments, error reports) as plain text.
The point of this demo is FUSION: structured facts and AI-extracted doc signals only reveal
risk when reconciled together, so the data is planted so the two sources agree, disagree, or
each carry signal the other misses.

Every customer is assigned a COHORT_STORY (healthy, steady_growth, vocal_churn, error_plagued,
billing_dispute, campaign_backlash, silent_risk) that shapes all of their rows: e.g. a
``silent_risk`` account has a cratering daily-active-user trend but never files a ticket, while
a ``vocal_churn`` account has clean telemetry but angry support docs. COHORT_STORY is written to
the customers table purely as a downstream guardrail + an "AI vs intent" check -- the pipeline
never classifies on it.

Why synthetic: real customer records are PII / contract-restricted. Synthesis is license-clean,
fully controllable (planted risk signals, a known cohort per customer), and reproducible from a
seed. Nothing is downloaded or redistributed by this skill.

Staging / load layout:
    <structured stage>/customers.csv, products.csv, transactions.csv,
                       telemetry_daily.csv, survey_scores.csv, campaigns.csv   (COPY'd into tables)
    <docs stage>/incoming/<customer_id>__<type>_<n>.txt   customer docs
    <docs stage>/incoming/JUNK-####__misc.txt             non-customer junk (proves the 'other' gate)

Prerequisite: run ``00_setup.sql`` first so the tables, stages, CSV format, file log, stream, and
suspended ingest task exist. On every run this script clears the stage, truncates the file log, and
recreates the stage stream to an empty baseline BEFORE re-staging, so the current corpus registers
as a clean set of inserts and a prior (even crashed) run can never replay stale rows or duplicate a
document.

Usage (run from the demos/scripts directory, after `uv sync --extra customer360`):
    uv run python data_sources/source_customer360.py \
        --connection MY_CONNECTION --database MY_DB --schema MY_SCHEMA
    # smaller / faster:
    uv run python data_sources/source_customer360.py ... --customers 20
    # rebuild the local corpus without uploading:
    uv run python data_sources/source_customer360.py --skip-upload
"""
from __future__ import annotations

import argparse
import csv
import random
import shutil
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from _snowflake_ids import check_db_schema

# Fixed demo object names -- must match 00_setup.sql / 10_pipeline.sql. Not CLI flags on purpose.
DOCS_STAGE = "DEMO_C360_DOCS_STAGE"
STRUCTURED_STAGE = "DEMO_C360_STRUCTURED_STAGE"
CSV_FMT = "DEMO_C360_CSV_FMT"
INGEST_TASK = "DEMO_C360_INGEST_TASK"
STAGE_STREAM = "DEMO_C360_STAGE_STREAM"
FILE_LOG = "DEMO_C360_FILE_LOG"

STRUCTURED_TABLES = {
    "customers": "DEMO_C360_CUSTOMERS",
    "products": "DEMO_C360_PRODUCTS",
    "transactions": "DEMO_C360_TRANSACTIONS",
    "telemetry_daily": "DEMO_C360_TELEMETRY_DAILY",
    "survey_scores": "DEMO_C360_SURVEY_SCORES",
    "campaigns": "DEMO_C360_CAMPAIGNS",
}

TELEMETRY_DAYS = 56          # first-14 vs last-14 window drives DAU_DECLINE_PCT in the pipeline
END_DATE = date(2026, 6, 30)

# =================================================================================================
# Product catalog. PRIMARY_PRODUCT (the product NAME) is the GROUP-BY axis of the health landscape.
# =================================================================================================
PRODUCTS = [
    ("flow", "Flow", "collaboration"),
    ("pulse", "Pulse", "analytics"),
    ("atlas", "Atlas", "data-platform"),
    ("ledger", "Ledger", "finance-ops"),
    ("signal", "Signal", "observability"),
]

SEGMENTS = ["Enterprise", "Mid-Market", "SMB"]
REGIONS = ["NA", "EMEA", "APAC", "LATAM"]
ACCOUNT_TIERS = ["Platinum", "Gold", "Silver"]

# =================================================================================================
# Cohorts. Each shapes telemetry, surveys, campaigns and which docs (+ tone) a customer gets, so
# the pipeline's RISK_TIER / ROUTE come out as intended. `weight` sets the cohort mix.
#   nps2      : (lo, hi) inclusive Q2 NPS range; None = did not respond (NULL)
#   err       : "low" (max < 0.03) | "high" (spikes > 0.05 -> escalate)
#   dau       : "up" | "flat" | "soft" (mild dip) | "down" (>15% decline -> high)
#   docs      : list of (doc_type, sentiment) customer docs to synthesize
#   campaign  : force an opened campaign (CAMPAIGN_EXPOSED = 1)
# =================================================================================================
@dataclass
class Cohort:
    weight: int
    nps2: tuple[int, int] | None
    err: str
    dau: str
    docs: list[tuple[str, str]]
    campaign: bool = False


COHORTS: dict[str, Cohort] = {
    "healthy":          Cohort(8, (9, 10), "low",  "flat", [("survey_comment", "pos")]),
    "steady_growth":    Cohort(3, (9, 10), "low",  "up",   []),
    "vocal_churn":      Cohort(5, (3, 6),  "low",  "soft", [("support_ticket", "neg"), ("chat_transcript", "neg")]),
    "error_plagued":    Cohort(4, (5, 7),  "high", "flat", [("error_report", "neg"), ("call_transcript", "neg")]),
    "billing_dispute":  Cohort(4, (6, 8),  "low",  "flat", [("support_ticket", "neg")]),
    "campaign_backlash": Cohort(3, (6, 8), "low",  "flat", [("survey_comment", "neg")], campaign=True),
    "silent_risk":      Cohort(4, None,    "low",  "down", []),
    # The pure fusion win: happy on every structured signal (NPS 9-10, clean telemetry) yet one
    # strongly negative doc -> medium risk that a structured-only dashboard would never surface.
    "hidden_detractor": Cohort(3, (9, 10), "low",  "flat", [("support_ticket", "incident")]),
}

# =================================================================================================
# Doc content banks. {name} = a contact name, {company} = the account, {product} = their product.
# Each entry is (subject, body). The wrapper (see render_doc) adds a type-specific header so
# AI_CLASSIFY can tell a ticket from a chat from a survey comment.
# =================================================================================================
DOC_BANK: dict[tuple[str, str], list[tuple[str, str]]] = {
    ("support_ticket", "neg"): [
        ("Repeated failures exporting reports",
         "For the third week running {product} fails when I export the weekly report -- it spins for "
         "a few minutes and then throws an error. My team at {company} has stopped trusting the numbers. "
         "This is blocking our Monday review and I need a real fix, not another 'we're looking into it'."),
        ("Considering cancellation",
         "I'll be blunt: unless this is resolved we are going to move off {product} at renewal. We have "
         "lost hours every week to workarounds and the support responses have been slow and generic. "
         "Please escalate -- {name}."),
        ("Billing charged us twice",
         "We were invoiced twice this cycle for {product} and the overage line makes no sense against our "
         "contracted seats. I've attached both invoices. This needs correcting before I approve any "
         "renewal conversation."),
    ],
    # "incident": a sharply negative, fresh operational complaint from an otherwise-engaged account
    # (the hidden_detractor -- happy on the survey, but this specific issue is a real problem).
    ("support_ticket", "incident"): [
        ("Regression in the latest release",
         "The latest {product} update introduced a regression that corrupted our saved views -- we lost a "
         "dashboard this morning and had to rebuild it by hand. We're generally happy with {product}, but "
         "this is a serious problem and needs a hotfix, not a backlog ticket. -- {name}"),
        ("Export totals no longer match after the upgrade",
         "Since the last {product} upgrade our exported totals no longer match what's shown on screen for "
         "{company}. It's undermining trust in the weekly numbers and my team is frustrated. Please "
         "investigate with priority."),
    ],
    ("chat_transcript", "neg"): [
        ("Live chat -- outage during launch",
         "[09:41] Customer: {product} is completely down for us right in the middle of our launch.\n"
         "[09:42] Agent: I'm sorry to hear that, can you confirm your account?\n"
         "[09:43] Customer: {company}. This is the second outage this month and it's costing us real money.\n"
         "[09:47] Agent: I've raised it with engineering.\n"
         "[09:49] Customer: 'Raised it' isn't good enough. We need a status page and an ETA. I'm furious."),
        ("Live chat -- cancellation threat",
         "[14:02] Customer: I want to understand the process to end our {product} contract.\n"
         "[14:03] Agent: I'd hate to see {company} go -- can I ask what's driving this?\n"
         "[14:05] Customer: Reliability. Every week something breaks and the value just isn't there anymore.\n"
         "[14:07] Agent: Let me loop in your account manager.\n"
         "[14:08] Customer: Please do, because right now I'm recommending we switch."),
    ],
    ("call_transcript", "neg"): [
        ("Call transcript -- renewal at risk",
         "Agent: Thanks for taking the call, {name}.\nCustomer: Honestly I almost didn't. {product} has been "
         "frustrating -- slow, and the last update broke our dashboards. My leadership is asking why we still "
         "pay for it.\nAgent: I understand. Let me get an engineer on this.\nCustomer: I've heard that before. "
         "If nothing changes by renewal we're leaving."),
    ],
    ("error_report", "neg"): [
        ("Automated incident -- elevated error rate",
         "SERVICE: {product}\nSEVERITY: high\nWINDOW: last 24h\nOBSERVED ERROR RATE: 8.4% (threshold 2%)\n"
         "IMPACT: {company} tenant -- failed API writes and dropped background jobs.\nSUMMARY: sustained 5xx "
         "responses from the ingest workers; retries exhausted. On-call paged twice. Customer-visible."),
        ("Automated incident -- repeated job failures",
         "SERVICE: {product}\nSEVERITY: high\nWINDOW: last 48h\nOBSERVED ERROR RATE: 11.2% (threshold 2%)\n"
         "IMPACT: {company} tenant -- scheduled exports failing.\nSUMMARY: worker crash loop after the latest "
         "deploy; error budget for the month exhausted. Escalated to engineering."),
    ],
    ("survey_comment", "neg"): [
        ("Quarterly NPS -- free response",
         "Score: 6/10. The product is fine but the constant marketing emails and the aggressive upsell "
         "campaign left a bad taste. I opened three 'exclusive' offers that all led to the same paywall. "
         "Stop selling and fix the onboarding."),
        ("Quarterly NPS -- free response",
         "Score: 5/10. We were promised the new tier would solve our reporting gap and the campaign made it "
         "sound ready. It isn't. Felt oversold."),
    ],
    ("survey_comment", "pos"): [
        ("Quarterly NPS -- free response",
         "Score: 9/10. {product} has become part of how {company} works day to day. Support has been "
         "responsive and the last few releases actually landed the features we asked for."),
        ("Quarterly NPS -- free response",
         "Score: 10/10. Rock solid this quarter. Onboarding the new team on {product} took an afternoon. "
         "Keep it up."),
    ],
}

# Non-customer junk (no customer id prefix) -- must classify as 'other' and drop out.
JUNK_DOCS = [
    ("internal_newsletter",
     "COMPANY ALL-HANDS RECAP\nThanks to everyone who joined the quarterly all-hands. Reminder: the office "
     "will be closed for the summer holiday, and the wellness stipend deadline is the end of the month. "
     "Congratulations to the sales team on a record quarter!"),
    ("vendor_invoice",
     "INVOICE -- Cloudscape Hosting\nInvoice #CS-99120. Services: managed Kubernetes, egress, object storage. "
     "Billing period: June 2026. Subtotal $4,210.00. Tax $357.85. Total due $4,567.85. Net 30."),
    ("meeting_agenda",
     "AGENDA -- Weekly Marketing Sync\n1. Campaign calendar review\n2. Webinar registrations\n3. Blog "
     "pipeline\n4. Swag reorder\n5. AOB. Notetaker: rotating. Please add topics before the call."),
    ("recruiting_email",
     "We're hiring! Join our platform team. We're looking for senior engineers who love distributed systems. "
     "Competitive comp, remote-friendly, great benefits. Refer a friend for a bonus."),
]

DOC_HEADERS = {
    "support_ticket": "SUPPORT TICKET #{tid}\nSubject: {subject}\nPriority: {prio}\nAccount: {company}\nContact: {name}\n\n{body}\n",
    "chat_transcript": "LIVE CHAT TRANSCRIPT\nAccount: {company}\nSession: {tid}\n\n{body}\n",
    "call_transcript": "CALL TRANSCRIPT (transcribed)\nAccount: {company}\nCall ID: {tid}\nDuration: {dur} min\n\n{body}\n",
    "survey_comment": "QUARTERLY NPS SURVEY -- FREE RESPONSE\nAccount: {company}\nRespondent: {name}\n\n{body}\n",
    "error_report": "AUTOMATED ERROR REPORT\nTicket: {tid}\n\n{body}\n",
}


# =================================================================================================
# Synthesis
# =================================================================================================

@dataclass
class Customer:
    customer_id: str
    company: str
    segment: str
    region: str
    account_tier: str
    signup_date: str
    product_name: str
    seats: int
    cohort: str


def weighted_cohort_sequence(n: int) -> list[str]:
    """Deterministic cohort assignment honoring the weights, cycling to fill n customers."""
    pool: list[str] = []
    for name, c in COHORTS.items():
        pool.extend([name] * c.weight)
    random.shuffle(pool)
    return [pool[i % len(pool)] for i in range(n)]


def dau_series(pattern: str, baseline: int) -> list[int]:
    days = TELEMETRY_DAYS
    out = []
    if pattern == "up":
        end_mult = random.uniform(1.15, 1.30)
    elif pattern == "flat":
        end_mult = random.uniform(0.98, 1.03)
    elif pattern == "soft":
        end_mult = random.uniform(0.90, 0.96)
    else:  # down -> triggers DAU_DECLINE_PCT <= -0.15
        end_mult = random.uniform(0.55, 0.70)
    for i in range(days):
        frac = i / (days - 1)
        level = baseline * (1 + (end_mult - 1) * frac)
        out.append(max(1, round(level * random.uniform(0.95, 1.05))))
    return out


def error_series(pattern: str) -> list[float]:
    days = TELEMETRY_DAYS
    if pattern == "high":
        base = [round(random.uniform(0.008, 0.02), 4) for _ in range(days)]
        for pos in random.sample(range(days), k=random.randint(3, 6)):
            base[pos] = round(random.uniform(0.06, 0.12), 4)   # spikes -> MAX_ERROR_RATE > 0.05
        return base
    return [round(random.uniform(0.001, 0.015), 4) for _ in range(days)]


def build_customers(n: int) -> list[Customer]:
    from faker import Faker

    fake = Faker()
    customers: list[Customer] = []
    for i, cohort in enumerate(weighted_cohort_sequence(n)):
        _, product_name, _ = random.choice(PRODUCTS)
        signup = END_DATE - timedelta(days=random.randint(120, 900))
        customers.append(Customer(
            customer_id=f"CUST-2026-{10001 + i}",
            company=fake.company(),
            segment=random.choice(SEGMENTS),
            region=random.choice(REGIONS),
            account_tier=random.choice(ACCOUNT_TIERS),
            signup_date=signup.isoformat(),
            product_name=product_name,
            seats=random.choice([5, 10, 25, 50, 100, 250]),
            cohort=cohort,
        ))
    return customers


def render_doc(doc_type: str, subject: str, body: str, cust: Customer, name: str, n: int) -> str:
    tid = f"{doc_type[:3].upper()}-{random.randint(100000, 999999)}"
    fmt = body.format(name=name, company=cust.company, product=cust.product_name)
    header = DOC_HEADERS[doc_type]
    return header.format(
        tid=tid, subject=subject, prio=random.choice(["High", "Urgent", "Normal"]),
        company=cust.company, name=name, dur=random.randint(6, 24), body=fmt,
    )


def build_corpus(out: Path, *, customers: int, junk: int, seed: int) -> dict:
    from faker import Faker

    random.seed(seed)
    Faker.seed(seed)
    fake = Faker()

    # Rebuild the local corpus from scratch each run so a smaller --customers can't leave stale
    # files from a previous larger run (which would then get PUT to the stage).
    if out.exists():
        shutil.rmtree(out)
    structured = out / "structured"
    incoming = out / "unstructured" / "incoming"
    structured.mkdir(parents=True, exist_ok=True)
    incoming.mkdir(parents=True, exist_ok=True)

    custs = build_customers(customers)

    # --- customers.csv (column order MUST match DEMO_C360_CUSTOMERS) ---
    with (structured / "customers.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["CUSTOMER_ID", "COMPANY_NAME", "SEGMENT", "REGION", "TIER",
                    "SIGNUP_DATE", "PRIMARY_PRODUCT", "SEATS", "COHORT_STORY"])
        for c in custs:
            w.writerow([c.customer_id, c.company, c.segment, c.region, c.account_tier,
                        c.signup_date, c.product_name, c.seats, c.cohort])

    # --- products.csv ---
    with (structured / "products.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["PRODUCT_SLUG", "PRODUCT_NAME", "CATEGORY"])
        for slug, name, cat in PRODUCTS:
            w.writerow([slug, name, cat])

    # --- transactions.csv ---
    with (structured / "transactions.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["TXN_ID", "CUSTOMER_ID", "PRODUCT", "AMOUNT", "CURRENCY", "TXN_DATE", "TXN_TYPE"])
        tx = 0
        for c in custs:
            annual = c.seats * random.choice([120, 180, 240]) / 12
            for m in range(random.randint(2, 5)):
                tx += 1
                d = END_DATE - timedelta(days=30 * m + random.randint(0, 10))
                w.writerow([f"TXN-{200000 + tx}", c.customer_id, c.product_name,
                            f"{round(annual * random.uniform(0.9, 1.1), 2)}", "USD",
                            d.isoformat(), "charge"])

    # --- telemetry_daily.csv ---
    with (structured / "telemetry_daily.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["CUSTOMER_ID", "PRODUCT", "DATE", "DAU", "SESSIONS",
                    "ERROR_RATE", "LATENCY_P95_MS", "FEATURE_ADOPTION_SCORE"])
        for c in custs:
            spec = COHORTS[c.cohort]
            baseline = max(2, round(c.seats * random.uniform(0.35, 0.7)))
            daus = dau_series(spec.dau, baseline)
            errs = error_series(spec.err)
            start = END_DATE - timedelta(days=TELEMETRY_DAYS - 1)
            for i in range(TELEMETRY_DAYS):
                d = start + timedelta(days=i)
                dau = daus[i]
                w.writerow([
                    c.customer_id, c.product_name, d.isoformat(), dau,
                    dau * random.randint(2, 5),
                    errs[i],
                    random.randint(120, 900),
                    round(random.uniform(0.3, 0.9), 2),
                ])

    # --- survey_scores.csv (Q1 + Q2) ---
    with (structured / "survey_scores.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["CUSTOMER_ID", "QUARTER", "NPS", "CSAT", "RESPONDED"])
        for c in custs:
            spec = COHORTS[c.cohort]
            # Q1 baseline (generally a touch healthier than Q2 for at-risk cohorts)
            q1 = random.randint(7, 10) if spec.nps2 is None else min(10, spec.nps2[1] + random.randint(0, 2))
            w.writerow([c.customer_id, "2026-Q1", q1, random.randint(3, 5), "true"])
            if spec.nps2 is None:
                w.writerow([c.customer_id, "2026-Q2", "", "", "false"])   # silent: no response -> NULL
            else:
                nps2 = random.randint(*spec.nps2)
                w.writerow([c.customer_id, "2026-Q2", nps2,
                            max(1, round(nps2 / 2)), "true"])

    # --- campaigns.csv ---
    with (structured / "campaigns.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["CUSTOMER_ID", "CAMPAIGN_ID", "CAMPAIGN_NAME", "CHANNEL",
                    "SENT_DATE", "OPENED", "CLICKED"])
        camp_names = ["Summer Upgrade", "Power-User Webinar", "New Tier Launch", "Renewal Nudge"]
        cnum = 0
        for c in custs:
            spec = COHORTS[c.cohort]
            n_camp = 1 if spec.campaign else random.randint(0, 2)
            for _ in range(n_camp):
                cnum += 1
                opened = True if spec.campaign else random.random() < 0.5
                d = END_DATE - timedelta(days=random.randint(5, 80))
                w.writerow([c.customer_id, f"CMP-{5000 + cnum}", random.choice(camp_names),
                            random.choice(["email", "in-app", "webinar"]), d.isoformat(),
                            "true" if opened else "false",
                            "true" if (opened and random.random() < 0.5) else "false"])

    # --- unstructured docs ---
    doc_count = 0
    for c in custs:
        spec = COHORTS[c.cohort]
        contact = fake.name()
        for n, (doc_type, tone) in enumerate(spec.docs, start=1):
            subject, body = random.choice(DOC_BANK[(doc_type, tone)])
            text = render_doc(doc_type, subject, body, c, contact, n)
            (incoming / f"{c.customer_id}__{doc_type}_{n}.txt").write_text(text)
            doc_count += 1

    for k in range(junk):
        kind, body = JUNK_DOCS[k % len(JUNK_DOCS)]
        (incoming / f"JUNK-{1001 + k}__{kind}.txt").write_text(body + "\n")

    cohort_mix: dict[str, int] = {}
    for c in custs:
        cohort_mix[c.cohort] = cohort_mix.get(c.cohort, 0) + 1
    print(f"Generated {len(custs)} customers across cohorts:")
    for name, cnt in sorted(cohort_mix.items(), key=lambda kv: -kv[1]):
        print(f"    {name:18} {cnt}")
    print(f"Generated {doc_count} customer docs + {junk} junk docs.\nCorpus: {out}")
    return {"customers": len(custs), "docs": doc_count, "junk": junk}


# =================================================================================================
# Upload: load structured CSVs, PUT docs, backfill the file log + CONTENT.
# =================================================================================================

def upload(out: Path, *, connection: str, database: str, schema: str) -> None:
    import snowflake.connector

    database, schema = check_db_schema(database, schema)
    structured = out / "structured"
    incoming = out / "unstructured" / "incoming"
    struct_stage = f"{database}.{schema}.{STRUCTURED_STAGE}"
    docs_stage = f"{database}.{schema}.{DOCS_STAGE}"
    conn = snowflake.connector.connect(connection_name=connection)
    try:
        cur = conn.cursor()
        cur.execute(f"USE SCHEMA {database}.{schema}")

        print(f"==> PUT structured CSVs -> @{struct_stage}/ and COPY into the tables")
        for stem, table in STRUCTURED_TABLES.items():
            csv_path = structured / f"{stem}.csv"
            cur.execute(
                f"PUT 'file://{csv_path}' @{struct_stage}/ AUTO_COMPRESS=FALSE OVERWRITE=TRUE"
            )
            cur.execute(f"TRUNCATE TABLE {table}")
            cur.execute(
                f"COPY INTO {table} FROM @{struct_stage}/{stem}.csv "
                f"FILE_FORMAT = (FORMAT_NAME = '{database}.{schema}.{CSV_FMT}') "
                "ON_ERROR = ABORT_STATEMENT"
            )

        # Rerun-safety: clear any docs from a previous run off the stage AND out of the file log,
        # then reset the stage stream to an EMPTY baseline. The stream reset matters even though we
        # truncate the file log: a prior run that crashed after PUT+REFRESH but before/while the
        # ingest task consumed the stream leaves unread INSERT rows behind. Because the filenames are
        # deterministic (same seed -> same paths), those stale inserts would replay alongside this
        # run's inserts and land duplicate RELATIVE_PATH rows, which then fan out through the
        # pipeline's RELATIVE_PATH join and inflate the doc/negative counts. REMOVE -> REFRESH ->
        # CREATE OR REPLACE STREAM rebaselines the stream against the now-empty stage.
        print(f"==> Clearing prior docs from @{docs_stage}/incoming/ + {FILE_LOG}, resetting the stream")
        cur.execute(f"REMOVE @{docs_stage}/incoming/")
        cur.execute(f"ALTER STAGE {docs_stage} REFRESH")
        cur.execute(f"TRUNCATE TABLE {FILE_LOG}")
        cur.execute(f"CREATE OR REPLACE STREAM {STAGE_STREAM} ON STAGE {docs_stage}")

        print(f"==> PUT customer docs -> @{docs_stage}/incoming/")
        cur.execute(
            f"PUT 'file://{incoming}/*.txt' @{docs_stage}/incoming/ "
            "AUTO_COMPRESS=FALSE OVERWRITE=TRUE PARALLEL=8"
        )

        print("==> ALTER STAGE ... REFRESH (register the new files as stream inserts)")
        cur.execute(f"ALTER STAGE {docs_stage} REFRESH")

        print(f"==> Backfilling {FILE_LOG} rows (runs the suspended ingest task once)")
        cur.execute(f"EXECUTE TASK {database}.{schema}.{INGEST_TASK}")

        # EXECUTE TASK is asynchronous: the CONTENT backfill UPDATEs the rows the task inserts, so
        # every doc's row must be present first. Poll as a HARD GATE -- fail fast rather than proceed
        # with a partial OR duplicated file log. The gate checks EXACT + UNIQUE coverage
        # (COUNT(*) == COUNT(DISTINCT path) == expected): a shortfall means the task is still landing
        # rows (or stalled), an overshoot means duplicate paths (which would fan out through the
        # RELATIVE_PATH join) -- either way, do not build the pipeline on it.
        local_docs = sorted(incoming.glob("*.txt"))
        expected = len(local_docs)
        print(f"==> Waiting for the ingest task to land exactly {expected} file-log rows")
        landed = distinct = 0
        deadline = time.time() + 180
        while time.time() < deadline:
            cur.execute(
                f"SELECT COUNT(*), COUNT(DISTINCT RELATIVE_PATH) FROM {FILE_LOG} "
                "WHERE RELATIVE_PATH ILIKE 'incoming/%'"
            )
            landed, distinct = cur.fetchone()
            if landed >= expected:
                break
            time.sleep(3)
        if landed != expected or distinct != expected:
            raise RuntimeError(
                f"ingest task landed {landed} rows ({distinct} distinct) vs {expected} expected "
                f"after 180s -- aborting before the CONTENT backfill. A shortfall is a partial "
                f"corpus; a duplicate (rows > distinct) means stale stream inserts replayed. Re-run "
                f"this script (it resets the stage, file log, and stream first); do not build the "
                f"pipeline on it."
            )

        print(f"==> Backfilling {FILE_LOG}.CONTENT from the local doc text")
        rows = [(p.read_text(), f"incoming/{p.name}") for p in local_docs]
        cur.executemany(
            f"UPDATE {FILE_LOG} SET CONTENT = %s WHERE RELATIVE_PATH = %s",
            rows,
        )
        cur.execute(
            f"SELECT COUNT(*), COUNT(DISTINCT RELATIVE_PATH) FROM {FILE_LOG} WHERE CONTENT IS NOT NULL"
        )
        with_content, distinct_content = cur.fetchone()
        if with_content != expected or distinct_content != expected:
            raise RuntimeError(
                f"CONTENT backfill covered {with_content} rows ({distinct_content} distinct) vs "
                f"{expected} expected -- aborting. The pipeline's sentiment + search steps need "
                "exactly one CONTENT-bearing row per doc; do not proceed on partial/duplicated data."
            )

        cur.execute(
            "SELECT 'customers' AS t, COUNT(*) AS n FROM DEMO_C360_CUSTOMERS "
            "UNION ALL SELECT 'telemetry', COUNT(*) FROM DEMO_C360_TELEMETRY_DAILY "
            "UNION ALL SELECT 'file_log', COUNT(*) FROM DEMO_C360_FILE_LOG "
            "UNION ALL SELECT 'file_log_with_content', COUNT(*) FROM DEMO_C360_FILE_LOG WHERE CONTENT IS NOT NULL"
        )
        print("==> Row counts:")
        for t, n in cur.fetchall():
            print(f"    {t:22} {n}")
    finally:
        conn.close()

    print("\nNext: run 10_pipeline.sql to create the dynamic tables (zero-spend scaffold),")
    print("then 20_insights.sql section A to run the AI (cost-gated).")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="corpus/customer360", help="local corpus dir")
    ap.add_argument("--customers", type=int, default=40, help="number of customers to synthesize")
    ap.add_argument("--junk", type=int, default=4, help="number of non-customer junk docs")
    ap.add_argument("--seed", type=int, default=42, help="reproducible synthesis seed")
    ap.add_argument("--skip-upload", action="store_true", help="build the local corpus, don't upload")
    ap.add_argument("--connection", help="Snowflake connection name (required unless --skip-upload)")
    ap.add_argument("--database", help="target database (required unless --skip-upload)")
    ap.add_argument("--schema", help="target schema (required unless --skip-upload)")
    args = ap.parse_args()

    out = Path(args.out)
    build_corpus(out, customers=args.customers, junk=args.junk, seed=args.seed)

    if args.skip_upload:
        print(f"\nLocal corpus ready at {out} (upload skipped).")
        return 0
    if not (args.connection and args.database and args.schema):
        ap.error("--connection, --database, and --schema are required unless --skip-upload")

    upload(out, connection=args.connection, database=args.database, schema=args.schema)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
