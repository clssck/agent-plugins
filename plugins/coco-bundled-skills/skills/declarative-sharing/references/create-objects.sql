-- ============================================
-- CREATING OBJECTS FOR DECLARATIVE SHARING
-- ============================================
-- Reference for creating views, semantic views, agents, notebooks, UDFs, and procedures.
-- Create all objects FIRST, then write the manifest, then create & release the package.

-- ============================================
-- VIEWS — MUST BE SECURE
-- ============================================
-- WRONG: CREATE VIEW ...
-- CORRECT:
CREATE OR REPLACE SECURE VIEW <DB>.<SCHEMA>.<VIEW_NAME> AS
SELECT * FROM <SOURCE_TABLE>;

-- Do NOT use REFERENCE_USAGE grants — the manifest handles access automatically.

-- ============================================
-- SEMANTIC VIEWS
-- ============================================
-- Semantic view DDL is unique — do NOT guess from memory. Use this template:
--
-- WORKING TEMPLATE:
CREATE OR REPLACE SEMANTIC VIEW <DB>.<SCHEMA>.<SV_NAME>
  TABLES (
    <TABLE_ALIAS> AS <DB>.<SCHEMA>.<TABLE_NAME> UNIQUE (<PK_COLUMN>)
  )
  DIMENSIONS (
    <TABLE_ALIAS>.<DIM_NAME> AS <COLUMN_NAME>
  )
  METRICS (
    <TABLE_ALIAS>.<METRIC_NAME> AS SUM(<COLUMN_NAME>)
  )
  COMMENT = '<description>';
--
-- KEY SYNTAX RULES:
-- - Use UNIQUE (<col>) NOT PRIMARY KEY — PRIMARY KEY is invalid
-- - Each dimension: TABLE_ALIAS.DIMENSION_NAME AS column_or_expression
-- - Each metric: TABLE_ALIAS.METRIC_NAME AS AGGREGATE(column)
-- - NO commas between entries within DIMENSIONS/METRICS/TABLES sections
-- - Supported aggregates: SUM, AVG, COUNT, MIN, MAX
-- - For multi-table: add RELATIONSHIPS section (see docs)
--
-- GOTCHA — verified_queries must NOT use fully qualified names:
--
-- BAD - causes INTERNAL_ERROR 370001:
--   verified_queries:
--     - sql: SELECT * FROM MY_DB.MY_SCHEMA.COMPANIES
--
-- GOOD - table alias only:
--   verified_queries:
--     - sql: SELECT * FROM COMPANIES
--
-- Note: Semantic views with verified_queries are not yet supported in declarative sharing.
-- Avoid using AI Optimization when creating semantic views for sharing.

-- ============================================
-- CORTEX SEARCH SERVICE
-- ============================================
-- Do NOT guess the syntax. Run:
--   cortex search docs "CREATE CORTEX SEARCH SERVICE"
--
-- Key parameters: ON <search_column>, ATTRIBUTES, WAREHOUSE, TARGET_LAG, AS (SELECT ...)
-- Note: Cortex Search has limited support in declarative shares.

-- ============================================
-- UDFs
-- ============================================
-- For complex UDF patterns, run:
--   cortex search docs "CREATE FUNCTION Snowflake SQL UDF"
--
-- MANIFEST GOTCHA: Functions MUST include their signature in manifest.yml:
--   WRONG: - my_function:
--   CORRECT: - my_function(VARCHAR):
--   CORRECT: - my_function(NUMBER, VARCHAR):
--
-- SCHEMA SEPARATION: Functions/procedures MUST be in a SEPARATE schema from
--   data objects (tables, views, semantic_views). Use e.g. LOGIC_SCHEMA for functions,
--   DATA_SCHEMA for tables/views.
--
-- ██████████████████████████████████████████████████████████████████████████████
-- ██  UDF/PROCEDURE BODY: NEVER use FQN (DB.SCHEMA.TABLE) inside the body!  ██
-- ██  Use SCHEMA.TABLE only. The provider DB doesn't exist on the consumer.  ██
-- ██████████████████████████████████████████████████████████████████████████████
-- When a consumer installs the app, the DATABASE is the APPLICATION name.
-- Any FQN reference to the provider's DB (e.g. MY_DB.MY_SCHEMA.MY_TABLE)
-- will fail with "object does not exist" on the consumer side.
--
-- CORRECT (relative — works on consumer):
--   SELECT * FROM DATA_SCHEMA.MY_TABLE
--
-- WRONG (FQN — breaks on consumer):
--   SELECT * FROM MY_SOURCE_DB.DATA_SCHEMA.MY_TABLE
--
-- Basic template:
CREATE OR REPLACE FUNCTION <DB>.<SCHEMA>.<FUNC_NAME>(<PARAM> <TYPE>)
RETURNS VARCHAR
LANGUAGE SQL
AS $$
  SELECT col FROM DATA_SCHEMA.MY_TABLE WHERE id = PARAM
$$;

-- ============================================
-- STORED PROCEDURES
-- ============================================
-- For complex procedure patterns, run:
--   cortex search docs "CREATE PROCEDURE Snowflake SQL"
--
-- Same MANIFEST, SCHEMA SEPARATION, and RELATIVE REFERENCE rules as UDFs above:
--   - Include signature in manifest: - my_procedure():  or  - my_procedure(VARCHAR, NUMBER):
--   - Must be in a logic-only schema (no tables/views/semantic_views)
--   - Body MUST use SCHEMA.TABLE (relative), NEVER DB.SCHEMA.TABLE (FQN)
--
-- Basic template:
CREATE OR REPLACE PROCEDURE <DB>.<SCHEMA>.<PROC_NAME>(
    <PARAM1> <TYPE1>,
    <PARAM2> <TYPE2>
)
RETURNS VARCHAR
LANGUAGE SQL
AS $$
BEGIN
    LET result VARCHAR := (SELECT col FROM DATA_SCHEMA.MY_TABLE WHERE id = :PARAM1);
    RETURN result;
END
$$;

-- ============================================
-- CORTEX AGENTS
-- ============================================
-- ██████████████████████████████████████████████████████████████████
-- ██  CORRECT:  CREATE AGENT        (or CREATE OR REPLACE AGENT) ██
-- ██  WRONG:    CREATE CORTEX AGENT (does NOT exist!)            ██
-- ██████████████████████████████████████████████████████████████████
-- "CREATE CORTEX AGENT" is NOT a valid Snowflake command. It will error.
-- Do NOT analogize from CREATE CORTEX SEARCH SERVICE — agents are different.

-- CRITICAL CONSTRAINTS
-- 1. ALL TOOLS MUST BE IN THE SAME DATABASE as the agent (different schemas OK)
-- 2. execution_environment with warehouse: "" (empty string) is REQUIRED for ALL tool types
--    EXCEPT Cortex Search. This applies equally to Analyst, UDF, and Procedure tools.
--    Without it: generic tools (UDF/procedure) FAIL HARD, Analyst tools silently return no results.
--    Cortex Search uses max_results instead (NO execution_environment).
-- 3. The empty string resolves to the consumer's default warehouse at install time.
--    Provider-side invocation will fail — this is expected. Test in consumer account.
-- 4. NEVER reference objects in a DIFFERENT database — keep all dependencies in the same DB
--
-- IDENTIFIER FORMAT IN tool_resources:
--   - UDFs/Procedures: ALWAYS use RELATIVE names: SCHEMA.OBJECT (NEVER FQN with database!)
--   - Semantic views/Search services: Use FQN with provider source DB: SOURCE_DB.SCHEMA.OBJECT
--     (Snowflake auto-rewrites the DB portion to the app name when installed)
--
-- CORRECT:
--   identifier: "AGENT_SCHEMA.MY_FUNCTION"                  CORRECT: Relative for UDFs/procedures
--   identifier: "AGENT_SCHEMA.MY_PROCEDURE"                 CORRECT: Relative for UDFs/procedures
--   semantic_view: "MY_SOURCE_DB.DATA_SCHEMA.MY_SV"         CORRECT: FQN for semantic views
--   search_service: "MY_SOURCE_DB.DATA_SCHEMA.MY_SEARCH"    CORRECT: FQN for search services
--
-- WRONG:
--   identifier: "MY_SOURCE_DB.AGENT_SCHEMA.MY_FUNCTION"     WRONG: FQN for UDFs — breaks!

-- TOOL TYPE REFERENCE
-- | Tool Type           | tool_spec.type              | tool_resources Structure                    |
-- |---------------------|-----------------------------|--------------------------------------------|
-- | Cortex Analyst (SV) | cortex_analyst_text_to_sql  | semantic_view + execution_environment      |
-- | Cortex Search       | cortex_search               | search_service + max_results (NO exec env) |
-- | UDF (Function)      | generic                     | identifier + type:"function" + exec env    |
-- | Stored Procedure    | generic                     | identifier + type:"procedure" + exec env   |

-- COMPREHENSIVE AGENT EXAMPLE (ALL TOOL TYPES)
-- Agent and all tools in the same database (different schemas OK).

CREATE OR REPLACE AGENT <DB>.AGENT_SCHEMA.<AGENT_NAME>
  COMMENT = 'Agent with all tool types: Analyst, Search, UDF, Procedure'
  PROFILE = '{"display_name": "Agent Name", "color": "#4a90d9"}'
  FROM SPECIFICATION
  $$
orchestration:
  budget:
    seconds: 60
    tokens: 16000
instructions:
  system: |
    You are a helpful assistant with access to multiple tools.
    Use the appropriate tool based on the user's question.
tools:
  - tool_spec:
      type: "cortex_analyst_text_to_sql"
      name: "product_analytics"
      description: "Query product catalog data for inventory, pricing, and category analysis"
  - tool_spec:
      type: "cortex_search"
      name: "doc_search"
      description: "Search documentation for policies, support info, and help articles"
  - tool_spec:
      type: "generic"
      name: "store_info"
      description: "Get store information about hours, location, or return policy"
      input_schema:
        type: "object"
        properties:
          topic:
            type: "string"
            description: "Topic to lookup: hours, location, or returns"
        required:
          - topic
  - tool_spec:
      type: "generic"
      name: "discount_calculator"
      description: "Calculate discount amount and final price"
      input_schema:
        type: "object"
        properties:
          original_price:
            type: "number"
            description: "Original price in dollars"
          discount_percent:
            type: "number"
            description: "Discount percentage (e.g., 20 for 20%)"
        required:
          - original_price
          - discount_percent
tool_resources:
  product_analytics:
    semantic_view: "<SOURCE_DB>.DATA_SCHEMA.<SEMANTIC_VIEW>"
    execution_environment:
      type: "warehouse"
      warehouse: ""
  doc_search:
    search_service: "<SOURCE_DB>.DATA_SCHEMA.<SEARCH_SERVICE>"
    max_results: 5
  store_info:
    identifier: "AGENT_SCHEMA.<UDF_NAME>"
    type: "function"
    execution_environment:
      type: "warehouse"
      warehouse: ""
  discount_calculator:
    identifier: "AGENT_SCHEMA.<PROCEDURE_NAME>"
    type: "procedure"
    execution_environment:
      type: "warehouse"
      warehouse: ""
  $$;

-- AGENT MANAGEMENT
SHOW AGENTS IN SCHEMA <DB>.<SCHEMA>;
SHOW AGENTS IN DATABASE <DB>;
SHOW AGENTS IN ACCOUNT;
SHOW AGENTS IN APPLICATION PACKAGE <PKG>;

DESCRIBE AGENT <DB>.<SCHEMA>.<AGENT_NAME>;

DROP AGENT IF EXISTS <DB>.<SCHEMA>.<AGENT_NAME>;

-- ============================================
-- WORKSPACES (recommended for sharing files with consumers)
-- ============================================
-- Workspaces share directories of files that consumers get as read-only workspaces.
-- They support most file types: notebooks (.ipynb), Python files, images (.png, .jpeg),
-- markdown (.md), etc. .ipynb notebooks within shared workspaces are EXECUTABLE
-- (but not editable) by consumers.
--
-- BLOCKED FILE TYPES:
--   - .pdf files are explicitly blocked
--
-- Workspaces go in `application_content.workspaces` in the manifest (NOT shared_content).
-- No special JSON formatting rules — just put files in a directory and reference it.
--
-- MANIFEST FORMAT:
--   application_content:
--     workspaces:
--       - MY_WORKSPACE:
--           roles: [app_user, app_admin]
--           source: content/folder/
--           comment: "Description of workspace purpose"
--
-- Properties:
--   - source (REQUIRED): relative path to the directory containing workspace files
--       MUST end with / (trailing slash required)
--       MUST NOT start with / (no leading slash)
--       Directory MUST contain at least one file (validated at BUILD/RELEASE time)
--   - roles (optional): list of app roles that can access this workspace
--       Must be defined in the manifest's top-level roles: section
--   - comment (optional): description
--
-- VALIDATION ERRORS (fail at BUILD or RELEASE):
--   - Source does not end with /
--   - Source starts with /
--   - Source directory has no files
--   - Role referenced in workspace not defined in manifest's top-level roles:
--
-- UPLOAD: Files are uploaded to the package at the path matching `source`:
--   PUT file:///local/path/content/folder/notebook.ipynb snow://package/<PKG>/versions/LIVE/content/folder/ AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
--
-- CONSUMER ACCESS (read-only):
--   DESCRIBE WORKSPACE <APP>.APPLICATION_CONTENT.<WORKSPACE_NAME>;
--   LIST snow://workspace/<APP>.APPLICATION_CONTENT.<WORKSPACE_NAME>/versions/LIVE/;
--   GET 'snow://workspace/<APP>.APPLICATION_CONTENT.<WORKSPACE_NAME>/versions/LIVE/<file>' file:///tmp/;
--
-- CONSTRAINTS:
--   - Consumers CANNOT modify, commit, or upload files to shared workspaces
--   - .ipynb notebooks are executable (but not editable) by consumers
--   - .pdf files are blocked
--   - Workspace files can access data within the same application package
--
-- NOTEBOOKS IN SHARED WORKSPACES (Next-Generation Notebooks):
--   This is the standard way to share notebooks via declarative shares.
--   Notebooks within shared workspaces run in RESTRICTED CALLER'S RIGHTS (RCR):
--
--   - ONLY objects shared by the application to the consumer can be accessed
--     by the notebook — nothing else (no external databases, no consumer-owned tables)
--   - The APPLICATION is the default database for the notebook session
--   - Reference shared objects using SCHEMA.OBJECT format (NOT DB.SCHEMA.OBJECT)
--     e.g., SELECT * FROM DATA_SCHEMA.MY_TABLE (correct)
--          SELECT * FROM MY_APP.DATA_SCHEMA.MY_TABLE (wrong — redundant, app IS the DB)
--          SELECT * FROM SOME_OTHER_DB.SCHEMA.TABLE (wrong — blocked by RCR)
--   - This is the same relative reference pattern used for UDFs/procedures in declarative shares

-- ============================================
-- LEGACY NOTEBOOKS (DEPRECATED — use WORKSPACES for next-gen notebooks)
-- ============================================
-- Legacy notebooks are DEPRECATED. They still work today but will be removed in a
-- future release. Next-gen notebooks require a workspace.
--
-- DECISION TREE:
-- 1. Package does NOT already have legacy notebooks → Use next-gen notebooks in a
--    workspace. Do NOT offer the legacy path.
-- 2. Package already HAS legacy notebooks → Strongly encourage migration to workspaces.
--    Legacy notebook support will be withdrawn soon, and once withdrawn, consumers may
--    no longer be able to use legacy notebooks.
-- 3. Provider strictly refuses to migrate → Let them continue, but remind them that
--    support will be withdrawn and consumers may lose access to legacy notebooks.
--
-- If proceeding with legacy notebooks, follow ALL rules below exactly.
-- ============================================
--
-- CoCo CLI ONLY — do NOT create from CoCo Web.
-- ⚠️ The CoCo Web (Snowsight workspace) write tool corrupts notebook JSON,
-- producing unparseable files. ONLY create notebooks from CoCo CLI.
-- If the user is on CoCo Web and asks for a notebook, explain this limitation.
--
-- Notebooks are an interface for consumers to explore shared data interactively.
-- They complement agents — agents provide natural language, notebooks provide direct SQL.
--
-- Snowsight notebooks run inside Snowflake — NO connection setup needed.
-- The session is already active. Use SCHEMA.TABLE (no database prefix — the app name IS the database).
--
-- CONSTRAINT: Notebooks can ONLY access data within the same application package.
-- They cannot query external databases or the provider's source data directly.
-- Surface this constraint to users so they understand the data access scope.
--
-- UPLOAD METHOD: Write notebook to workspace via write tool, then COPY FILES to package.
-- See references/package-release.sql for the exact COPY FILES sequence.
--
-- CORRECT multi-line source (each line ends with \n JSON escape):
--   "source": [
--     "import pandas as pd\n",
--     "from snowflake.snowpark.context import get_active_session\n",
--     "\n",
--     "session = get_active_session()\n",
--     "df.describe()"
--   ]
--
-- WRONG — missing \n (lines concatenate: "import pandas as pdfrom snowflake..."):
--   "source": [
--     "import pandas as pd",
--     "from snowflake.snowpark.context import get_active_session"
--   ]
--
-- REQUIRED NOTEBOOK METADATA — see NOTEBOOK.ipynb for the exact top-level structure.
--   "nbformat": 4, "nbformat_minor": 4
--
-- REQUIRED CELL FIELDS:
--   "id": unique string (UUID recommended, e.g. "a1b2c3d4-0001-0000-0000-000000000000")
--   "metadata": { "name": "cell_name" } for markdown cells
--   "metadata": { "language": "sql", "name": "cell_name" } for SQL code cells
--   "metadata": { "language": "python", "name": "cell_name" } for Python code cells
--   "execution_count": null and "outputs": [] for all code cells

-- PARAMOUNT: NOTEBOOK CELL FORMAT
-- THIS IS THE #1 MOST COMMON FAILURE POINT FOR NOTEBOOKS.
-- If you get this wrong, SQL cells will be interpreted as Python and WILL NOT EXECUTE.
-- The consumer will see syntax errors and the notebook will be unusable.
--
-- EVERY code cell MUST have "metadata": { "language": "..." } set correctly.
-- There is NO exception. Missing this metadata = broken notebook.
--
-- CORRECT SQL cell:
--   {
--     "cell_type": "code",
--     "metadata": { "language": "sql" },
--     "source": ["SELECT * FROM MY_TABLE"],
--     "outputs": []
--   }
--
-- CORRECT Python cell:
--   {
--     "cell_type": "code",
--     "metadata": { "language": "python" },
--     "source": ["import pandas as pd"],
--     "outputs": []
--   }
--
-- ██████████████████████████████████████████████████████████████████████████████
-- ██  WRONG — %%sql magic in source (Workspace-only, breaks shared notebooks) ██
-- ██████████████████████████████████████████████████████████████████████████████
-- Workspace notebooks use %%sql -r dataframe_N as a Jupyter magic to mark SQL cells.
-- Shared app notebooks do NOT run in a Workspace kernel — they use legacy Snowsight.
-- If you include %%sql in the source, the consumer sees raw "%%sql -r dataframe_1"
-- text that does NOT execute. Language MUST be set via metadata, NOT cell magic.
--
-- WRONG — %%sql magic prefix (consumer sees this as broken text):
--   {
--     "cell_type": "code",
--     "metadata": { "language": "sql" },
--     "source": ["%%sql -r dataframe_1\n", "SELECT * FROM MY_TABLE"],
--     "outputs": []
--   }
--
-- WRONG — %%sql without metadata (doubly broken):
--   {
--     "cell_type": "code",
--     "metadata": {},
--     "source": ["%%sql\n", "SELECT * FROM MY_TABLE"],
--     "outputs": []
--   }
--
-- WRONG — missing language metadata (defaults to Python, SQL will break):
--   {
--     "cell_type": "code",
--     "metadata": {},
--     "source": ["SELECT * FROM MY_TABLE"],
--     "outputs": []
--   }
--
-- WRONG — no metadata key at all:
--   {
--     "cell_type": "code",
--     "source": ["SELECT * FROM MY_TABLE"],
--     "outputs": []
--   }
--
-- After creating ANY .ipynb file, verify EVERY code cell has "metadata": { "language": "sql" }
-- or "metadata": { "language": "python" }. See NOTEBOOK.ipynb for the template structure.

