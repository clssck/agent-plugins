-- Fast path: pre-computed Policy Recommendations from SNOWFLAKE.POLICY_RECOMMENDATIONS.
-- workflows/policy-recommendations.md (Step 0 / Step 2) covers interpretation, freshness,
-- capability, and fallback. Any error or empty result -> fall back to the live scan.

-- 1. Probe availability (errors if the feature is not enabled / not authorized).
SHOW PROCEDURES IN SCHEMA SNOWFLAKE.POLICY_RECOMMENDATIONS;

-- 2. Per-category summary; LAST_REFRESHED_AT is the freshness signal (empty = no run yet).
CALL SNOWFLAKE.POLICY_RECOMMENDATIONS.GET_POLICY_RECOMMENDATION_SUMMARY();

-- 3. Ranked recommendations: NULL for all, or an OBJECT_CONSTRUCT filter
--    (keys: database_name, category, min_impact, sensitivity, limit, offset).
--    To scope to a data object, filter by database_name; narrow to schema/table/column
--    from the returned rows (the procedure filters only at the database level).
CALL SNOWFLAKE.POLICY_RECOMMENDATIONS.GET_POLICY_RECOMMENDATIONS(NULL);
CALL SNOWFLAKE.POLICY_RECOMMENDATIONS.GET_POLICY_RECOMMENDATIONS(
    OBJECT_CONSTRUCT('database_name', 'MY_DB', 'limit', 200)
);
