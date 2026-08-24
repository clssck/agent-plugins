# Fine-Tuning arctic-extract

Train a custom arctic-extract model to improve AI_EXTRACT accuracy on your document types.

```
╔═══════════════════════════════════════════════════════════════════════════════╗
║                        FINE-TUNING arctic-extract                             ║
║                 Improve AI_EXTRACT for domain-specific documents              ║
╚═══════════════════════════════════════════════════════════════════════════════╝
```

---

## When to Use

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 SHOULD YOU FINE-TUNE?
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

   AI_EXTRACT accuracy
   still poor after
   scale_factor 4.0?
         │
         ▼
   ┌─────────────┐    No    ┌─────────────────────────────┐
   │  Systematic │─────────▶│  Keep tuning scale_factor   │
   │  failures?  │          │  or refine responseFormat   │
   └──────┬──────┘          └─────────────────────────────┘
          │ Yes
          ▼
   ┌─────────────┐    No    ┌─────────────────────────────┐
   │  20+ labeled│─────────▶│  Gather more labeled        │
   │  examples?  │          │  document examples first    │
   └──────┬──────┘          └─────────────────────────────┘
          │ Yes
          ▼
   ┌─────────────┐
   │  Fine-tune! │
   └─────────────┘
```

---

## Full Workflow

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 STEP 1: PREPARE TRAINING DATA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

   For each document, provide:

   ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐
   │      File        │   │     Prompt       │   │    Response      │
   │                  │   │                  │   │                  │
   │ @stage/doc.pdf   │   │ {"field":        │   │ {"field":        │
   │                  │   │  "question?"}    │   │  "answer"}       │
   └──────────────────┘   └──────────────────┘   └──────────────────┘
            │                      │                      │
            └──────────────────────┴──────────────────────┘
                                   │
                                   ▼
                        ┌─────────────────────┐
                        │  Snowflake Dataset  │
                        │  snow://dataset/... │
                        └─────────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 STEP 2: SUBMIT FINE-TUNING JOB
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

   SNOWFLAKE.CORTEX.FINETUNE('CREATE', 'db.schema.model', 'arctic-extract', dataset)
                                   │
                    ┌──────────────▼──────────────┐
                    │     Job ID returned          │
                    │  ft_6556e15c-8f12-...        │
                    └─────────────────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 STEP 3: MONITOR JOB
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

   SNOWFLAKE.CORTEX.FINETUNE('DESCRIBE', '<job_id>')

   ┌─────────┐      ┌─────────┐      ┌─────────┐      ┌─────────┐
   │ PENDING │─────▶│ RUNNING │─────▶│ SUCCESS │      │ FAILED  │
   └─────────┘      └─────────┘      └────┬────┘      └────┬────┘
                                          │                │
                                          ▼                ▼
                                    Fine-tuned        Troubleshoot
                                    model ready       (see job-management.md)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 STEP 4: INFERENCE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

   AI_EXTRACT(model => 'db.schema.my_tuned_model', file => TO_FILE(...))
                                   │
                    ┌──────────────▼──────────────┐
                    │  Test single file first      │
                    │  Compare vs. base model      │
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │  Batch process / Pipeline    │
                    └─────────────────────────────┘
```

---

## Reference Files

| File | Purpose |
|------|---------|
| `references/overview.md` | Decision guide, prerequisites, limits |
| `references/training-data.md` | Dataset schema, creation workflow, validation |
| `references/job-management.md` | FINETUNE CREATE / DESCRIBE / SHOW / CANCEL |
| `references/inference.md` | AI_EXTRACT with fine-tuned model, batch, copy |
