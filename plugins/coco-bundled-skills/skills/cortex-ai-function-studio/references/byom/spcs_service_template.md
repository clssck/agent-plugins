<!-- Copyright (c) 2026 Snowflake Inc. All rights reserved.
     Licensed under the Snowflake Skills License. See LICENSE file. -->

# Bring your own Model SPCS Service Template

Use this as a pattern only. Replace every placeholder with verified account/model values before execution.

## Service Pattern

```sql
CREATE SERVICE {database}.{schema}.{service_name}
IN COMPUTE POOL {compute_pool_name}
MIN_INSTANCES = {min_instances}
MAX_INSTANCES = {max_instances}
{external_access_clause}
FROM SPECIFICATION $$
spec:
  containers:
  - name: "model-inference"
    image: "{vllm_image}"
    sha256: "{vllm_image_sha256}"
    args:
    - "--tensor-parallel-size={tensor_parallel_size}"
    - "--gpu-memory-utilization={gpu_memory_utilization}"
    - "--max-model-len={max_model_len}"
    - "--model={model_path}"
    - "--served-model-name={served_model_name}"
    - "--host=0.0.0.0"
    - "--port=8000"
    env:
      VLLM_LOGGING_LEVEL: "INFO"
      SHARED_VOLUME_DIR: "/shared"
      HF_HUB_OFFLINE: "1"
    readinessProbe:
      port: 5000
      path: "/health"
    resources:
      limits:
        memory: "{model_memory_limit}"
        cpu: "{model_cpu_limit}"
        nvidia.com/gpu: "{gpu_count}"
      requests:
        memory: "{model_memory_request}"
        cpu: "{model_cpu_request}"
        nvidia.com/gpu: "{gpu_count}"
    volumeMounts:
    - name: "shared-vol"
      mountPath: "/shared"
  - name: "proxy"
    image: "{proxy_image}"
    sha256: "{proxy_image_sha256}"
    env:
      {proxy_env_key}: "{proxy_env_value}"
    resources:
      limits:
        memory: "{proxy_memory_limit}"
        cpu: "{proxy_cpu_limit}"
      requests:
        memory: "100Mi"
        cpu: "50m"
  volumes:
  - name: "shared-vol"
    source: "local"
  endpoints:
  - name: "inference"
    port: 5000
    public: true
  logExporters:
    eventTableConfig:
      logLevel: "INFO"
  snowhouseConfig:
    enableFiles: true
  platformMonitor:
    metricConfig:
      groups:
      - "system"
      - "status"
      - "network"
  resourceManagement:
    autoScalingPolicies:
      scaleUp:
        anyCondition:
        - metricCondition:
            metricName: "snow.model_serving.queue.fill_ratio"
            aggregationType: "avg"
            labels:
              snow.service.container.name: "proxy"
            stabilizationPeriodSecs: 60
            targetScaling:
              targetValue: {scale_up_queue_fill_ratio}
        - metricCondition:
            metricName: "container.gpu.utilization"
            aggregationType: "avg"
            labels:
              snow.service.container.name: "model-inference"
            stabilizationPeriodSecs: 60
            targetScaling:
              targetValue: {scale_up_gpu_utilization}
      scaleDown:
        allConditions:
        - metricCondition:
            metricName: "snow.model_serving.queue.fill_ratio"
            aggregationType: "avg"
            labels:
              snow.service.container.name: "proxy"
            stabilizationPeriodSecs: 180
            targetScaling:
              targetValue: {scale_down_queue_fill_ratio}
  serviceRoles:
  - name: "INFERENCE_SERVICE_FUNCTION_USAGE"
$$;
```

## Smoke Test Pattern

```sql
ALTER SESSION SET ENABLE_SPCS_SERVICE_FUNCTIONS_IN_AISQL = TRUE;

SELECT AI_COMPLETE(
  '{database}.{schema}.{service_name}',
  'Say hello in one short sentence.'
) AS response;
```

## Validation Checklist

- Model image and proxy image are approved and digest-pinned.
- Compute pool has enough GPU memory for `max_model_len`, tensor parallel size, and concurrency target.
- External access integration and secrets are configured without exposing tokens in chat.
- Service role grants allow the caller to invoke the service function.
- Smoke test passes before CAIFS evaluate/optimize uses the service.
