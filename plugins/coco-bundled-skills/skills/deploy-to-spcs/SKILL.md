---
name: deploy-to-spcs
description: "Deploy containerized apps to Snowpark Container Services. Use when: deploying Docker apps, creating SPCS services, pushing images to Snowflake registry, granting role access to SPCS service endpoints. Triggers: SPCS, Snowpark Container Services, deploy to Snowflake, container deployment, grant access to service, grant role access, service role, consumer access, SPCS service, service endpoints."
---

# Deploy to Snowpark Container Services (SPCS)

Deploy any containerized application to Snowflake using Snowpark Container Services. Works with any Docker-based app (Next.js, Python, Go, etc.).

## When to Use
- User has a containerized app (Docker) ready to deploy
- User wants to host an app on Snowflake infrastructure
- User mentions SPCS, Snowpark Container Services, or deploying to Snowflake

## Tools Used
- `bash` - Run docker commands, snow CLI
- `snowflake_sql_execute` - Create compute pools, repos, services
- `cortex browser` - Verify deployed apps

## Stopping Points
- ⚠️ Step 1: Confirm app builds successfully
- ⚠️ Step 2: Confirm SPCS prerequisites exist
- ⚠️ Step 5: Confirm deployment success
- ⚠️ Step 6: Confirm consumer role access

---

## Workflow

### Step 1: Verify App Readiness

**Goal:** Ensure the app is containerized and builds correctly.

**Actions:**

1. Confirm app has a working `Dockerfile`
2. Confirm app builds locally:
   ```bash
   docker build --platform linux/amd64 -t <image-name>:latest .
   ```
3. Confirm app exposes a port (default: 8080)

**Output:** Successful local Docker build.

**⚠️ MANDATORY STOPPING POINT:** Do NOT proceed until app builds successfully.

---

### Step 2: Verify SPCS Prerequisites

**Goal:** Ensure compute pool and image repository exist.

**Actions:**

1. Check current role:
   ```sql
   SELECT CURRENT_ROLE(), CURRENT_USER();
   ```

2. Check/create compute pool:
   ```sql
   SHOW COMPUTE POOLS;
   
   -- If no accessible pool exists:
   CREATE COMPUTE POOL <pool_name>
     MIN_NODES = 1
     MAX_NODES = 1
     INSTANCE_FAMILY = CPU_X64_XS;
   ```

3. Check/create image repository:
   ```sql
   SHOW IMAGE REPOSITORIES;
   
   -- If needed:
   CREATE IMAGE REPOSITORY <db>.<schema>.<repo_name>;
   ```

4. Login to registry:
   ```bash
   snow spcs image-registry login --connection <conn>
   ```

**Output:** Compute pool and image repository ready.

**⚠️ MANDATORY STOPPING POINT:** Do NOT proceed until prerequisites exist.

---

### Step 3: Create Service Specification

**Goal:** Define the service configuration.

**Actions:**

1. Create `service-spec.yaml` with the following template:
   ```yaml
   spec:
     containers:
     - name: <app-name>
       image: /<db>/<schema>/<repo>/<image>:latest
       env:
         HOSTNAME: "0.0.0.0"
         PORT: "8080"
         NODE_ENV: production
       resources:
         requests:
           memory: 1Gi
           cpu: 500m
         limits:
           memory: 2Gi
           cpu: 1000m
       readinessProbe:
         port: 8080
         path: /
     endpoints:
     - name: <endpoint-name>
       port: 8080
       public: true
   ```

2. Adjust `resources`, `port`, and `env` based on app requirements.

**Output:** `service-spec.yaml` file ready for deployment.

**Next:** Proceed to Step 4.

---

### Step 4: Build and Push Image

**Goal:** Push the container image to Snowflake registry.

**Actions:**

1. Build, tag, and push:
   ```bash
   docker build --platform linux/amd64 -t <image-name>:latest .
   docker tag <image-name>:latest <registry-url>/<db>/<schema>/<repo>/<image-name>:latest
   docker push <registry-url>/<db>/<schema>/<repo>/<image-name>:latest
   ```

   Registry URL format: `<account>.registry.snowflakecomputing.com`

**Output:** Image pushed to Snowflake image repository.

**Next:** Proceed to Step 5.

---

### Step 5: Deploy Service

**Goal:** Create the SPCS service and verify it's running.

**Actions:**

1. Create the service:
   ```sql
   CREATE SERVICE <service_name>
     IN COMPUTE POOL <pool_name>
     FROM SPECIFICATION $$
     <contents of service-spec.yaml>
     $$
     MIN_INSTANCES = 1
     MAX_INSTANCES = 1;
   ```

2. Monitor status and get URL:
   ```sql
   SELECT SYSTEM$GET_SERVICE_STATUS('<service_name>');
   SHOW ENDPOINTS IN SERVICE <service_name>;
   ```

3. Extract `ingress_url` from SHOW ENDPOINTS and display to user.

4. Verify deployment:
   ```bash
   cortex browser open "https://<ingress_url>"
   cortex browser snapshot -i
   ```

**Output:** Service running with accessible URL.

**⚠️ MANDATORY STOPPING POINT:** Do NOT proceed until user confirms deployment success.

---

### Step 6: Grant Consumer Access

**Goal:** Configure access for the consuming role.

**Actions:**

1. **Ask user:** "What role will consume this service?"

2. Check the grants to the role 
   ```sql
   SHOW GRANTS TO ROLE <consumer_role>;
   ```

3. Grant ALL THREE of the following (all are required, do not skip any):
   ```sql
   -- 1. Database access (REQUIRED)
   GRANT USAGE ON DATABASE <db> TO ROLE <consumer_role>;
   -- 2. Schema access (REQUIRED)
   GRANT USAGE ON SCHEMA <db>.<schema> TO ROLE <consumer_role>;
   -- 3. Service endpoint access (REQUIRED) — note: GRANT SERVICE ROLE, not GRANT USAGE ON SERVICE
   GRANT SERVICE ROLE <service_name>!ALL_ENDPOINTS_USAGE TO ROLE <consumer_role>;
   ```

4. If the service is using a table in Snowflake, grant what the service needs:
   ```sql
   GRANT USAGE ON DATABASE <table_db> TO ROLE <consumer_role>;
   GRANT USAGE ON SCHEMA <table_db>.<table_schema> TO ROLE <consumer_role>;
   -- Grant privileges the service requires (SELECT, INSERT, UPDATE, DELETE, etc.)
   GRANT <privileges> ON TABLE <table_db>.<table_schema>.<table> TO ROLE <consumer_role>;
   ```


**Output:** Consumer role can access the service.

**⚠️ MANDATORY STOPPING POINT:** Do NOT proceed until user confirms consumer role access works.

---

## Updating a Service

**⚠️ CAUTION:** Always use `ALTER SERVICE` to update. Never drop and recreate—this changes the URL and breaks integrations.

```bash
docker build --platform linux/amd64 -t <image-name>:latest .
docker tag <image-name>:latest <registry-url>/<db>/<schema>/<repo>/<image-name>:latest
docker push <registry-url>/<db>/<schema>/<repo>/<image-name>:latest
```

```sql
ALTER SERVICE <service_name> FROM SPECIFICATION $$
<full yaml spec>
$$;
```

---

## Troubleshooting

**Get service logs:**
```sql
SELECT SYSTEM$GET_SERVICE_LOGS('<service_name>', 0, '<container_name>');
```

**Common issues:**

| Problem | Cause | Fix |
|---------|-------|-----|
| Image not found | Path mismatch | Use exact format: `/<db>/<schema>/<repo>/<image>:latest` (case-sensitive, leading slash required) |
| Service fails readiness | Port mismatch | Align three ports: `readinessProbe.port`, `PORT` env var, `endpoints.port` |
| Auth errors on push | Expired login | Re-run `snow spcs image-registry login --connection <conn>` |
| Permission errors | Missing grants | Grant required privileges to the service owner role |

---

## Output

- Deployed SPCS service URL
- Service status confirmation
- Consumer role access configured
