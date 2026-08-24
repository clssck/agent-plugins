-- =============================================================================
-- PROVIDER TELEMETRY DASHBOARD — SOURCE SQL
-- Schema: SNOWFLAKE.DATA_SHARING_USAGE
-- All queries support a configurable lookback window (7 / 30 / 90 days).
-- Replace -90 with -7 or -30 as needed.
-- =============================================================================


-- =============================================================================
-- 1. LISTING_CONSUMPTION_DAILY
-- Powers: Overview tab (Active Consumers, Total Jobs, User Sessions KPIs,
--         Daily Jobs bar chart, period-over-period deltas),
--         Consumption tab (Daily Jobs & Active Users dual-axis chart,
--         Consumption by Listing horizontal bar, Consumption Heatmap),
--         Consumers tab (all charts and KPIs)
-- =============================================================================

-- Daily active consumer accounts + total jobs across all listings
SELECT
    EVENT_DATE,
    COUNT(DISTINCT CONSUMER_ACCOUNT_NAME) AS ACTIVE_CONSUMERS,
    COUNT(DISTINCT LISTING_DISPLAY_NAME)  AS LISTINGS_WITH_ACTIVITY,
    SUM(JOBS)                             AS TOTAL_JOBS
FROM SNOWFLAKE.DATA_SHARING_USAGE.LISTING_CONSUMPTION_DAILY
WHERE EVENT_DATE >= DATEADD('day', -90, CURRENT_DATE())
GROUP BY EVENT_DATE
ORDER BY EVENT_DATE;

-- Per listing: UNIQUE_USERS_1D is safe to use here because
-- each row is already scoped to one listing + one consumer account,
-- so MAX gives the per-account user count for that listing-day.
SELECT
    EVENT_DATE,
    LISTING_DISPLAY_NAME,
    COUNT(DISTINCT CONSUMER_ACCOUNT_NAME)  AS ACTIVE_CONSUMERS,
    SUM(JOBS)                              AS TOTAL_JOBS,
    SUM(UNIQUE_USERS_1D)                   AS TOTAL_USER_SESSIONS
    -- ^ Note: this sums across consumer accounts for the SAME listing,
    --   so it approximates total user-sessions, not distinct users
FROM SNOWFLAKE.DATA_SHARING_USAGE.LISTING_CONSUMPTION_DAILY
WHERE EVENT_DATE >= DATEADD('day', -90, CURRENT_DATE())
GROUP BY EVENT_DATE, LISTING_DISPLAY_NAME
ORDER BY EVENT_DATE, LISTING_DISPLAY_NAME;

-- Period-over-period comparison (fetches 2x the window, then splits in Python)
SELECT
    EVENT_DATE,
    CONSUMER_ACCOUNT_NAME,
    LISTING_DISPLAY_NAME,
    SNOWFLAKE_REGION,
    SUM(JOBS)            AS JOBS,
    SUM(UNIQUE_USERS_1D) AS UNIQUE_USERS_1D
FROM SNOWFLAKE.DATA_SHARING_USAGE.LISTING_CONSUMPTION_DAILY
WHERE EVENT_DATE >= DATEADD('day', -180, CURRENT_DATE())
  AND EVENT_DATE <  DATEADD('day', -90,  CURRENT_DATE())
GROUP BY ALL
ORDER BY EVENT_DATE;

-- Consumers tab — top consumers ranked by total jobs
SELECT
    CONSUMER_ACCOUNT_NAME,
    SUM(JOBS)                       AS TOTAL_JOBS,
    SUM(UNIQUE_USERS_1D)            AS TOTAL_USERS,
    COUNT(DISTINCT LISTING_DISPLAY_NAME) AS LISTINGS_USED,
    COUNT(DISTINCT EVENT_DATE)      AS DAYS_ACTIVE
FROM SNOWFLAKE.DATA_SHARING_USAGE.LISTING_CONSUMPTION_DAILY
WHERE EVENT_DATE >= DATEADD('day', -90, CURRENT_DATE())
GROUP BY CONSUMER_ACCOUNT_NAME
ORDER BY TOTAL_JOBS DESC;

-- Consumers tab — jobs and unique consumers grouped by Snowflake region
SELECT
    SNOWFLAKE_REGION,
    SUM(JOBS)                            AS JOBS,
    COUNT(DISTINCT CONSUMER_ACCOUNT_NAME) AS CONSUMERS
FROM SNOWFLAKE.DATA_SHARING_USAGE.LISTING_CONSUMPTION_DAILY
WHERE EVENT_DATE >= DATEADD('day', -90, CURRENT_DATE())
GROUP BY SNOWFLAKE_REGION
ORDER BY JOBS DESC;

-- Consumption tab — heatmap: jobs aggregated by listing and day-of-week
SELECT
    LISTING_DISPLAY_NAME,
    DAYNAME(EVENT_DATE) AS DAY_OF_WEEK,
    SUM(JOBS)           AS JOBS
FROM SNOWFLAKE.DATA_SHARING_USAGE.LISTING_CONSUMPTION_DAILY
WHERE EVENT_DATE >= DATEADD('day', -90, CURRENT_DATE())
GROUP BY LISTING_DISPLAY_NAME, DAY_OF_WEEK
ORDER BY LISTING_DISPLAY_NAME,
  CASE DAYNAME(EVENT_DATE)
    WHEN 'Mon' THEN 1 WHEN 'Tue' THEN 2 WHEN 'Wed' THEN 3
    WHEN 'Thu' THEN 4 WHEN 'Fri' THEN 5 WHEN 'Sat' THEN 6
    WHEN 'Sun' THEN 7
  END;


-- =============================================================================
-- 2. LISTING_EVENTS_DAILY
-- Powers: Overview tab (GETs KPI, Click-to-GET conversion rate),
--         Events & Funnel tab (all charts, conversion funnel, recent events table)
-- Event types: GET, REQUEST, TRIAL, PURCHASE
-- =============================================================================

SELECT
    EVENT_DATE,
    EVENT_TYPE,
    LISTING_NAME,
    CONSUMER_ACCOUNT_NAME,
    CONSUMER_ORGANIZATION
FROM SNOWFLAKE.DATA_SHARING_USAGE.LISTING_EVENTS_DAILY
WHERE EVENT_DATE >= DATEADD('day', -90, CURRENT_DATE())
ORDER BY EVENT_DATE;

-- Events & Funnel tab — event counts by type (funnel + KPI metrics)
SELECT
    EVENT_TYPE,
    COUNT(*) AS EVENT_COUNT
FROM SNOWFLAKE.DATA_SHARING_USAGE.LISTING_EVENTS_DAILY
WHERE EVENT_DATE >= DATEADD('day', -90, CURRENT_DATE())
GROUP BY EVENT_TYPE
ORDER BY EVENT_COUNT DESC;

-- Events & Funnel tab — daily event volume stacked by type
SELECT
    EVENT_DATE,
    EVENT_TYPE,
    COUNT(*) AS EVENT_COUNT
FROM SNOWFLAKE.DATA_SHARING_USAGE.LISTING_EVENTS_DAILY
WHERE EVENT_DATE >= DATEADD('day', -90, CURRENT_DATE())
GROUP BY EVENT_DATE, EVENT_TYPE
ORDER BY EVENT_DATE;

-- Overview tab — conversion rate (Click-to-GET)
-- Numerator: total GETs from LISTING_EVENTS_DAILY
-- Denominator: total EVENT_COUNT from LISTING_TELEMETRY_DAILY (see query 3)
SELECT COUNT(*) AS TOTAL_GETS
FROM SNOWFLAKE.DATA_SHARING_USAGE.LISTING_EVENTS_DAILY
WHERE EVENT_TYPE = 'GET'
  AND EVENT_DATE >= DATEADD('day', -90, CURRENT_DATE());


-- =============================================================================
-- 3. LISTING_TELEMETRY_DAILY
-- Powers: Overview tab (Listing Clicks KPI, Daily Listing Activity stacked bar)
-- =============================================================================

SELECT
    EVENT_DATE,
    LISTING_NAME,
    LISTING_DISPLAY_NAME,
    EVENT_TYPE,
    ACTION,
    SUM(EVENT_COUNT)            AS EVENT_COUNT,
    SUM(CONSUMER_ACCOUNTS_DAILY) AS CONSUMER_ACCOUNTS_DAILY
FROM SNOWFLAKE.DATA_SHARING_USAGE.LISTING_TELEMETRY_DAILY
WHERE EVENT_DATE >= DATEADD('day', -90, CURRENT_DATE())
GROUP BY ALL
ORDER BY EVENT_DATE;

-- Overview tab — daily activity chart (stacked bar, grouped by EVENT_TYPE)
SELECT
    EVENT_DATE,
    EVENT_TYPE,
    SUM(EVENT_COUNT) AS COUNT
FROM SNOWFLAKE.DATA_SHARING_USAGE.LISTING_TELEMETRY_DAILY
WHERE EVENT_DATE >= DATEADD('day', -90, CURRENT_DATE())
GROUP BY EVENT_DATE, EVENT_TYPE
ORDER BY EVENT_DATE;


-- =============================================================================
-- 4. LISTING_ACCESS_HISTORY
-- Powers: Consumption tab (Query Volume line chart, Queries by Region bar chart)
-- =============================================================================

SELECT
    QUERY_DATE,
    QUERY_TOKEN,
    CONSUMER_ACCOUNT_LOCATOR,
    SNOWFLAKE_REGION,
    LISTING_GLOBAL_NAME
FROM SNOWFLAKE.DATA_SHARING_USAGE.LISTING_ACCESS_HISTORY
WHERE QUERY_DATE >= DATEADD('day', -90, CURRENT_DATE())
ORDER BY QUERY_DATE;

-- Consumption tab — daily query volume (line chart)
-- Fixed: daily query volume
SELECT 
    QUERY_DATE, 
    COUNT(*) AS QUERIES
FROM SNOWFLAKE.DATA_SHARING_USAGE.LISTING_ACCESS_HISTORY
WHERE QUERY_DATE >= DATEADD('day', -90, CURRENT_DATE())
GROUP BY QUERY_DATE 
ORDER BY QUERY_DATE;

-- Fixed: queries by region requires a join or alternative approach
-- Remove the region-by-region query from this view, or join to LISTING_CONSUMPTION_DAILY

-- Consumption tab — queries grouped by Snowflake region (bar chart)
SELECT
    SNOWFLAKE_REGION,
    COUNT(*) AS QUERIES
FROM SNOWFLAKE.DATA_SHARING_USAGE.LISTING_ACCESS_HISTORY
WHERE QUERY_DATE >= DATEADD('day', -90, CURRENT_DATE())
GROUP BY SNOWFLAKE_REGION
ORDER BY QUERIES DESC;


SELECT LISTING_TITLE, HOURS_SINCE_SUBMISSION, ADMIN_USERNAME,
       METADATA_REVIEW_STATUS, FUNCTIONAL_REVIEW_STATUS, COMPLIANCE_REVIEW_STATUS,
       SLA_TARGET, SLA_STATUS, PROVIDER_SALESFORCE_ACCOUNT_NAME,
       SUBMITTED_AT
FROM MARKETPLACE_ANALYTICS.SOHYUN_ANALYTICS.V_LISTING_APPROVAL_STATUS
WHERE STATUS = 'Pending'
  AND FUNCTIONAL_REVIEW_STATUS = 'Pending'
  AND (METADATA_REVIEW_STATUS IN ('Approved', 'Rejected')
       OR COMPLIANCE_REVIEW_STATUS IN ('Approved', 'Rejected'))
ORDER BY SUBMITTED_AT DESC;