-- Optional example lab for the sv-ingest skill (portable; not environment-specific).
-- Creates a small "messy" Semantic View estate with intentional conflicts — homonyms,
-- formula drift, a derived metric, and a multi-table SV — plus a few governed-column
-- bindings so the drift resolution ladder has lineage to follow.
--
-- To run, replace SV_INGEST_DB with any database you can create objects in, then use
-- your own connection (its default role and warehouse are sufficient):
--   snow sql -c <YOUR_CONNECTION> -f seed_messy_sv_estate.sql
--
-- Tables are created fresh (CREATE OR REPLACE) in a dedicated lab schema, so the
-- INSERTs below only populate lab data.

CREATE SCHEMA IF NOT EXISTS SV_INGEST_DB.SV_INGEST_LAB
  COMMENT = 'Intentional SV conflicts for ontology sv-ingest validation';

CREATE OR REPLACE TABLE SV_INGEST_DB.SV_INGEST_LAB.REVENUE_DAILY (
  revenue_date DATE,
  region VARCHAR,
  customer_segment VARCHAR,
  gross_revenue_amount NUMBER(18,2),
  discount_amount NUMBER(18,2),
  refund_amount NUMBER(18,2)
);

CREATE OR REPLACE TABLE SV_INGEST_DB.SV_INGEST_LAB.BOOKINGS_DAILY (
  booking_date DATE,
  region VARCHAR,
  bookings_amount NUMBER(18,2),
  credits_amount NUMBER(18,2)
);

INSERT INTO SV_INGEST_DB.SV_INGEST_LAB.REVENUE_DAILY
SELECT * FROM VALUES
  ('2024-07-01'::DATE, 'AMER', 'ENTERPRISE', 1000, 50, 10),
  ('2024-07-01'::DATE, 'EMEA', 'SMB', 800, 40, 5),
  ('2024-10-01'::DATE, 'AMER', 'ENTERPRISE', 1200, 60, 20)
  AS t(revenue_date, region, customer_segment, gross_revenue_amount, discount_amount, refund_amount);

INSERT INTO SV_INGEST_DB.SV_INGEST_LAB.BOOKINGS_DAILY
SELECT * FROM VALUES
  ('2024-07-01'::DATE, 'AMER', 5000, 200),
  ('2024-10-01'::DATE, 'EMEA', 3000, 150)
  AS t(booking_date, region, bookings_amount, credits_amount);

-- Finance canonical: net_revenue = gross - discount - refund
CREATE OR REPLACE SEMANTIC VIEW SV_INGEST_DB.SV_INGEST_LAB.FINANCE_METRICS_SV
  TABLES (
    revenue_daily AS SV_INGEST_DB.SV_INGEST_LAB.REVENUE_DAILY
      PRIMARY KEY (revenue_date, region, customer_segment)
  )
  DIMENSIONS (
    revenue_daily.region AS region COMMENT = 'Sales region',
    revenue_daily.customer_segment AS customer_segment
  )
  METRICS (
    revenue_daily.gross_revenue AS SUM(gross_revenue_amount) COMMENT = 'Gross revenue before adjustments',
    revenue_daily.net_revenue AS
      SUM(gross_revenue_amount) - SUM(discount_amount) - SUM(refund_amount)
      COMMENT = 'Net Revenue — finance definition (post discount and refund)',
    -- New derived metric: no matching ontology node, but built on the governed
    -- GROSS_REVENUE_AMOUNT column → should surface as DERIVES_FROM_GOVERNED_COLUMN.
    revenue_daily.adjusted_gross AS SUM(gross_revenue_amount) * 0.9
      COMMENT = 'Adjusted gross (90% haircut) — derived lab metric'
  )
  COMMENT = 'Finance domain SV for ontology sv-ingest lab';

-- Sales: SAME metric name, DIFFERENT formula (CROSS_SV_CONFLICT)
CREATE OR REPLACE SEMANTIC VIEW SV_INGEST_DB.SV_INGEST_LAB.SALES_METRICS_SV
  TABLES (
    bookings_daily AS SV_INGEST_DB.SV_INGEST_LAB.BOOKINGS_DAILY
      PRIMARY KEY (booking_date, region)
  )
  DIMENSIONS (
    bookings_daily.region AS region
  )
  METRICS (
    bookings_daily.net_revenue AS SUM(bookings_amount) - SUM(credits_amount)
      COMMENT = 'Net Revenue — sales definition (bookings minus credits)'
  )
  COMMENT = 'Sales domain SV — homonym metric net_revenue';

-- Legacy duplicate finance SV (deprecation / drift tests)
CREATE OR REPLACE SEMANTIC VIEW SV_INGEST_DB.SV_INGEST_LAB.LEGACY_FINANCE_SV
  TABLES (
    revenue_daily AS SV_INGEST_DB.SV_INGEST_LAB.REVENUE_DAILY
      PRIMARY KEY (revenue_date, region, customer_segment)
  )
  METRICS (
    revenue_daily.net_revenue AS SUM(gross_revenue_amount) - SUM(discount_amount)
      COMMENT = 'Legacy Net Revenue — omits refunds (drift vs FINANCE_METRICS_SV)'
  )
  COMMENT = 'Deprecated finance SV for drift lab';

-- Multi-table consolidated
CREATE OR REPLACE SEMANTIC VIEW SV_INGEST_DB.SV_INGEST_LAB.ENTERPRISE_CONSOLIDATED_SV
  TABLES (
    revenue_daily AS SV_INGEST_DB.SV_INGEST_LAB.REVENUE_DAILY
      PRIMARY KEY (revenue_date, region, customer_segment),
    bookings_daily AS SV_INGEST_DB.SV_INGEST_LAB.BOOKINGS_DAILY
      PRIMARY KEY (booking_date, region)
  )
  RELATIONSHIPS (
    rev_to_book AS revenue_daily (revenue_date, region) REFERENCES bookings_daily (booking_date, region)
  )
  DIMENSIONS (
    revenue_daily.region AS region
  )
  METRICS (
    revenue_daily.net_revenue AS
      SUM(gross_revenue_amount) - SUM(discount_amount) - SUM(refund_amount),
    bookings_daily.total_bookings AS SUM(bookings_amount)
  )
  COMMENT = 'Enterprise consolidated SV — multi-table lab';

-- ─────────────────────────────────────────────────────────────────────────
-- Governed lineage: bind existing ontology nodes to LAB base columns/table.
-- These make the drift resolution ladder resolve domain from lineage (not SV
-- name), and reassign the Enterprise SV's finance fields to their term domain.
-- Safe to re-run; duplicate drafts are ignored/errored per asset.
-- ─────────────────────────────────────────────────────────────────────────

-- Gross Revenue → governed column (enables same-name bind + Enterprise reassignment)
CALL SYSTEM$DRAFT_GLOSSARY_ASSET('Gross Revenue',
  '{"refType":"COLUMN","fqn":"SV_INGEST_DB.SV_INGEST_LAB.REVENUE_DAILY.GROSS_REVENUE_AMOUNT"}','DESCRIBES');
CALL SYSTEM$APPROVE_GLOSSARY_ASSET('Gross Revenue',
  '{"refType":"COLUMN","fqn":"SV_INGEST_DB.SV_INGEST_LAB.REVENUE_DAILY.GROSS_REVENUE_AMOUNT"}');

-- Region → governed column
CALL SYSTEM$DRAFT_GLOSSARY_ASSET('Region',
  '{"refType":"COLUMN","fqn":"SV_INGEST_DB.SV_INGEST_LAB.REVENUE_DAILY.REGION"}','DESCRIBES');
CALL SYSTEM$APPROVE_GLOSSARY_ASSET('Region',
  '{"refType":"COLUMN","fqn":"SV_INGEST_DB.SV_INGEST_LAB.REVENUE_DAILY.REGION"}');

-- Customer Segment → governed column
CALL SYSTEM$DRAFT_GLOSSARY_ASSET('Customer Segment',
  '{"refType":"COLUMN","fqn":"SV_INGEST_DB.SV_INGEST_LAB.REVENUE_DAILY.CUSTOMER_SEGMENT"}','DESCRIBES');
CALL SYSTEM$APPROVE_GLOSSARY_ASSET('Customer Segment',
  '{"refType":"COLUMN","fqn":"SV_INGEST_DB.SV_INGEST_LAB.REVENUE_DAILY.CUSTOMER_SEGMENT"}');

-- Net Revenue → governed base TABLE (LINEAGE_TABLE fallback demo)
CALL SYSTEM$DRAFT_GLOSSARY_ASSET('Net Revenue',
  '{"refType":"TABLE","fqn":"SV_INGEST_DB.SV_INGEST_LAB.REVENUE_DAILY"}','DESCRIBES');
CALL SYSTEM$APPROVE_GLOSSARY_ASSET('Net Revenue',
  '{"refType":"TABLE","fqn":"SV_INGEST_DB.SV_INGEST_LAB.REVENUE_DAILY"}');

SELECT 'SV_INGEST_LAB seeded + lineage bound' AS status;
