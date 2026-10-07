-- Check Current Context
-- Run this first to understand the current session context

SELECT 
    CURRENT_USER() AS current_user,
    CURRENT_ROLE() AS current_role,
    CURRENT_DATABASE() AS current_database,
    CURRENT_SCHEMA() AS current_schema,
    CURRENT_WAREHOUSE() AS current_warehouse;

