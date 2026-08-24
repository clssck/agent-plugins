-- ============================================================
-- GRANT DISCOVERY: apply-policy privileges for current role
-- ============================================================
-- Run this at the start of a session to determine what policy
-- apply actions the current role can perform directly.
--
-- Results drive CAPABILITY_LEVEL:
--   FULL_APPLY   -- global APPLY <KIND> POLICY ON ACCOUNT, or ACCOUNTADMIN/SYSADMIN
--   POLICY_OWNER -- OWNERSHIP on ≥1 policy, but no global apply
--   ANALYST      -- ACCOUNT_USAGE access only; no apply grants, no policy ownership
-- ============================================================

-- ── Part 1: Implicit full-apply via privileged roles ─────────────────────────
SELECT
    IS_ROLE_IN_SESSION('ACCOUNTADMIN')  AS IS_ACCOUNTADMIN,
    IS_ROLE_IN_SESSION('SYSADMIN')      AS IS_SYSADMIN;

-- ── Part 2: Explicit apply-policy and policy-ownership grants ─────────────────
-- Checks GRANTS_TO_ROLES for the current role.
-- NOTE: This reflects direct grants only, not the full inherited role hierarchy.
-- If a parent role holds global apply, use IS_ROLE_IN_SESSION on that parent role
-- as a supplementary check.
SELECT
    PRIVILEGE,
    GRANTED_ON,
    NAME            AS OBJECT_NAME,
    TABLE_CATALOG   AS OBJECT_DATABASE,
    TABLE_SCHEMA    AS OBJECT_SCHEMA
FROM SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_ROLES
WHERE GRANTEE_NAME = CURRENT_ROLE()
  AND (
        -- Global or object-scoped apply privileges
        (
          PRIVILEGE IN (
            'APPLY MASKING POLICY',
            'APPLY ROW ACCESS POLICY',
            'APPLY PROJECTION POLICY',
            'APPLY AGGREGATION POLICY',
            'APPLY JOIN POLICY'
          )
          AND GRANTED_ON IN ('ACCOUNT', 'TABLE', 'TAG')
        )
        OR
        -- Ownership on policies (can apply owned policy where table privilege exists)
        (
          PRIVILEGE   = 'OWNERSHIP'
          AND GRANTED_ON IN (
            'MASKING POLICY',
            'ROW ACCESS POLICY',
            'PROJECTION POLICY',
            'AGGREGATION POLICY',
            'JOIN POLICY'
          )
        )
      )
ORDER BY PRIVILEGE, GRANTED_ON, OBJECT_NAME;

-- ── Interpreting results ──────────────────────────────────────────────────────
-- FULL_APPLY:   IS_ACCOUNTADMIN = TRUE, OR IS_SYSADMIN = TRUE, OR Part 2 has any row
--               with PRIVILEGE = 'APPLY * POLICY' AND GRANTED_ON = 'ACCOUNT'
--
-- POLICY_OWNER: No FULL_APPLY condition is met, AND Part 2 has ≥1 row with
--               PRIVILEGE = 'OWNERSHIP' AND GRANTED_ON LIKE '%POLICY%'
--               Record OBJECT_NAME values as OWNED_POLICY_NAMES for use in Step 1.
--
-- ANALYST:      Neither condition above is met.
--               User can read governance data but cannot apply policies broadly.
--               NOTE: APPLY * POLICY grants scoped to specific objects (GRANTED_ON IN
--               ('TABLE','TAG')) also fall here — treat as ANALYST for capability messaging,
--               but record those OBJECT_NAME targets: the user CAN apply on those specific
--               tables/tags, so surface that when a recommendation targets one of them.
