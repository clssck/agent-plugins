---
name: ref-spcs-service-functions
description: "Service function SQL syntax and request/response protocol for SPCS in Native Apps."
parent_skill: native-app-provider
---

# SPCS Service Functions Reference

## Service Functions

Service functions expose a service endpoint as a callable SQL function. Consumers call the function like any UDF; Snowflake routes the request to the running service container.

**Critical ordering:** Service functions reference a service that must already exist. Place `CREATE FUNCTION` statements **after** `CREATE SERVICE` in the setup script.

**Syntax:**
```sql
CREATE FUNCTION IF NOT EXISTS <schema>.<function_name>(<args>)
  RETURNS VARCHAR
  SERVICE = <service_schema>.<service_name>
  ENDPOINT = '<endpoint_name>'
  AS '/<path>';
```

**No-argument example** (simple GET/POST to root path):
```sql
-- After CREATE SERVICE in setup script:
CREATE FUNCTION IF NOT EXISTS <schema>.hello()
  RETURNS VARCHAR
  SERVICE = <service_schema>.<service_name>
  ENDPOINT = '<endpoint_name>'
  AS '/';
GRANT USAGE ON FUNCTION <schema>.hello() TO APPLICATION ROLE app_user;
```

**With-argument example** (passes arguments as JSON body):
```sql
-- After CREATE SERVICE in setup script:
CREATE FUNCTION IF NOT EXISTS <schema>.predict(input VARCHAR)
  RETURNS VARCHAR
  SERVICE = <service_schema>.<service_name>
  ENDPOINT = '<endpoint_name>'
  AS '/predict';
GRANT USAGE ON FUNCTION <schema>.predict(VARCHAR) TO APPLICATION ROLE app_user;
```

**Key rules:**
- `SERVICE` references the fully-qualified service name (schema-qualified within the app)
- `ENDPOINT` must match an endpoint name from the service spec YAML
- `AS '/<path>'` is the HTTP path on the container the request is routed to
- Service functions can live in any schema (versioned or non-versioned), but must be **created after the service exists** in the setup script
- Use `CREATE FUNCTION IF NOT EXISTS` (not `CREATE OR REPLACE`) to be idempotent
- The service must be RUNNING for the function to return results — calls to a suspended service will fail
- **Do NOT use** `SYSTEM$SEND_SNOWFLAKE_SERVICE_REQUEST` for service functions — use the `CREATE FUNCTION ... SERVICE = ... ENDPOINT = ...` syntax shown above

## Service Function Request/Response Protocol

When Snowflake invokes a service function, it sends a **POST** request with a JSON body containing the input rows. The container must return a JSON response in the same tabular format, echoing the row index as the first element of each result row.

**Request format** (sent by Snowflake to the container):
```json
{
  "data": [
    [0, arg1_row0, arg2_row0],
    [1, arg1_row1, arg2_row1]
  ]
}
```
- `data[i][0]` is the **row index** (integer)
- `data[i][1..]` are the function arguments for that row

For a **no-argument** function (e.g., `hello()`), each row has only the index: `[0]`.

**Response format** (must be returned by the container):
```json
{
  "data": [
    [0, "result_for_row_0"],
    [1, "result_for_row_1"]
  ]
}
```
- `data[i][0]` **must echo the row index** from the request
- `data[i][1]` is the return value for that row

**Python/Flask example** handling service function requests:
```python
@app.route('/', methods=['POST'])
def hello():
    request_body = request.json
    # Echo row index + return value for each input row
    return jsonify({
        "data": [[row[0], "Hello from SPCS Native App!"] for row in request_body["data"]]
    })
```

**Common mistake:** Returning `{"data": [["result"]]}` without the row index causes: `Error parsing JSON response for external function — index 0 contains 1 elements, but 2 elements are expected`.

## Connecting to Snowflake from Inside a Container

Snowflake automatically provisions OAuth credentials into every SPCS container. This is a general SPCS mechanism — not native-app-specific. For the full details including auto-injected environment variables (`SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_HOST`, `SNOWFLAKE_DATABASE`, `SNOWFLAKE_SCHEMA`), the OAuth token at `/snowflake/session/token`, and connection code patterns, see:

https://docs.snowflake.com/en/developer-guide/snowpark-container-services/spcs-execute-sql
