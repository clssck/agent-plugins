---
name: automl
description: "Automated end-to-end machine learning workflow — quality gates, feature engineering, AutoGluon model search and tuning, experiment tracking, and final report. Load when the user explicitly asks for automl ('automl', 'auto ml', 'auto-ml', 'automated machine learning', 'run automl') OR signals they want a search across models ('best model', 'find the best model', 'best possible model', 'highest score', 'highest accuracy', 'top model', 'top performing model', 'automated model selection'). Do NOT auto-load for generic ML requests like 'predict X', 'train a specific model', or 'help me improve this model' — these are directed and go to ml-development."
---

# AutoML

Automated machine learning — from data to trained model through automated feature engineering, model experimentation, and tuning.

**Outputs:**
- **Snowsight:** Working notebook (`<experiment_name>.ipynb`) — code + EDA + journal in markdown cells.
- **CLI:** A working directory `<experiment_name>/` containing `eda.py`, `fe.py` (baseline FE shared by trials), `trial_<N>_<short_label>.py` (FE delta and model fit), `helpers.py` (cross-trial plumbing — `ExperimentLogger` lives here, trials import from it), and `journal.md`.
- **Both:** Experiment tracking (metrics, params, artifacts, model) + `<experiment_name>_manifest.json`.

## When to Load

**⚠️ Load this skill when the user explicitly asks for automl** (e.g., "run automl", "use auto-ml") **OR signals they want a model search** (e.g., "find the best model", "highest score", "top model"). Covers classification, regression, time-series forecasting, and clustering.

**User-specified model:** If the user requests a specific model (e.g., "train an XGBoost model") and this skill is already loaded, scope the modeling to their choice but still run feature engineering and HPO for tuning.

---

## Workflow

**Communication:** At the start, outline the full workflow so the user knows what to expect. Announce each step as you enter it.

**Checkpoints:**
- **⚠️ STOP** — pause and wait for user input before continuing.
- **📋 REPORT** — summarize progress, insights, decisions, and thought process to the user in the chat, then continue.

**Output destinations:**
- **Chat** — all REPORT content. The user reads the chat, not the working file.
- **Working file** — code, EDA, experiment journal. Snowsight: notebook with markdown cells. CLI: a `<experiment_name>/` directory with `.py` snapshots (`eda.py`, `fe.py`, `trial_<N>_<label>.py`) plus `journal.md`.
- **Experiment tracking** — metrics, params, artifacts, model.

If something belongs in the chat, it MUST appear in the chat even if it's also in the working file.

### Step 1: Understand & Configure

Accept the user's natural language problem statement — that's the only required input. Infer what you can from the data, then ask follow-up questions for anything missing. Check for an existing `<experiment_name>_manifest.json` — if prior work exists, review what was tried and build on those results.

**Semantic type detection:** Auto-detect column types — dates/timestamps, categoricals, free text, numerics, IDs/constants. Flag ambiguous columns (e.g., numeric codes that are actually categories).

**Minimum input:** Data source + what to predict or analyze. The agent infers task type, target column, evaluation metric, and modeling budget from context — the user validates these at the STOP point. For forecasting, also confirm: time column, entity column (if multiple series), forecast horizon, and frequency.

**Compute detection:** Detect available CPUs, GPUs, memory, and instance type. After exploring the data (rows, columns, types), assess whether the current compute is sufficient. If not, scale up via Snowflake compute. For multi-node workloads, load `../distributed-training/SKILL.md`. Do not silently downsample.

**Data size assessment:** Check row/column counts to inform compute, trial plan, and feature engineering decisions in Steps 2–3.

**Output:** Confirmed task configuration.

**⚠️ STOP — present and confirm all of these before proceeding:**
- [ ] Task type, target column, ID columns, evaluation metric
- [ ] Forecasting: time column, entity column, horizon, frequency
- [ ] Ask user for time budget (suggest ~30 min end-to-end as starting point — e.g., 1 AutoGluon trial at time_limit=600 plus FE and evaluation)
- [ ] Proposed trial plan sized to that budget — how many trials, what to try, how long each should train

The plan can adapt based on what you learn — adjust trial count, time_limit, or approach, but do not exceed the total budget. If a trial runs longer than expected, cut subsequent trials or reduce their time_limit to compensate.

**After user confirms:**

Create `<experiment_name>_manifest.json` in the working directory with the confirmed configuration (task type, target column, evaluation metric, trial plan, time budget, data source, and forecasting settings if applicable). Record `start_time` (`time.time()`) in the manifest to track elapsed time against the budget.

**Dependencies:** Install only the components required by the confirmed plan. Do **not** `pip install autogluon` — the umbrella package pulls in `autogluon.multimodal`, which pins to an older Ray and conflicts with newer Ray-based runtimes. Install AutoGluon as components instead, and only include `autogluon.multimodal` when the task actually needs it.

| Component | When to install | Spec |
|---|---|---|
| `autogluon.tabular[all]` | Always (classification, regression, forecasting all depend on it) | `autogluon.tabular[all]==1.5.1b20260415` |
| `autogluon.core` | Always | `autogluon.core==1.5.1b20260415` |
| `autogluon.features` | Always | `autogluon.features==1.5.1b20260415` |
| `autogluon.timeseries` | Forecasting only | `autogluon.timeseries==1.5.1b20260415` |
| `autogluon.multimodal` | **Only if the task involves text or image features that need AutoGluon's multimodal models** — otherwise skip it. If you install it, verify it doesn't downgrade Ray on the current runtime. | `autogluon.multimodal==1.5.1b20260415` |

All AutoGluon components must pin to the same version. `1.5.1b20260415` is the version validated against this workflow.

**OpenFE:**
- Bundled in **Snowflake ML Runtime ≥ 2.6.0** — no install needed. Verify with `import openfe; print(openfe.__version__)`.
- On older runtimes, install `openfe>=0.0.12`.

Only install what the plan requires. If an install fails, do not silently continue without the packages — surface the error and adjust the plan.

If AutoGluon can't be installed (usually a missing PyPI EAI or restricted artifactory), ask the user to check permissions first; if still blocked, keep the trial/KEEP-REVERT/manifest framework with whatever ML library is available.

### Step 2: Quality Gates

**Not optional. Do not skip any.**

Before writing any model code, complete all of these:
1. **Leakage detection** — drop columns that are proxies for the target or wouldn't exist at prediction time. Ask: "would this column be available when the model runs in production?" Verify that the data grain and target definition lead to an actionable outcome — flag if the unit of analysis is wrong, the target is a proxy, or the time window is ambiguous.
2. **ID/constant exclusion** — drop columns with no predictive signal (unique IDs, near-constants, free-text identifiers)
3. **Evaluation setup** — train/test split (stratified for imbalanced classification, temporal for forecasting). AutoGluon's bagged k-fold creates internal **validation folds — these val scores select the champion** (`predictor.model_best`). The held-out **test set is used once for the final reported score**, never for selection or re-ranking. For small datasets (<1K rows), consider repeated CV. For grouped/hierarchical data (e.g., multiple records per customer), use grouped splits to prevent leakage across entities. Never evaluate on training data.
4. **Naive baseline** — report a trivial baseline (majority class, predict mean, etc.) **scored on the same eval_metric you confirmed in Step 1** — not just accuracy. All model performance is relative to this. If the final model can't meaningfully beat the naive baseline, say so.
5. **Data quality** — deduplicate, check label quality, flag inconsistencies. Assess missing data patterns — systematic missingness (e.g., a field only populated for one segment) is signal the model should know about. For forecasting: convert to long format (item_id, timestamp, target), detect and fill timestamp gaps based on frequency.
6. **Fairness** — identify sensitive groups and document for downstream monitoring
7. **Imbalanced data detection** (classification) — check class distribution. If class ratio >10:1, flag for handling in Step 3 (class weights, balanced metric, SMOTE if needed). SMOTE must be applied to training data only — never to validation or test sets. Never use accuracy alone — use F1, AUC-ROC, or AUC-PR.
8. **Outlier assessment** — identify outliers and decide per column: clip, transform, or leave. Document the decision. The strategy depends on the model and whether outliers are noise or real signal.

**High-dimensional data (>100 features):** Run feature selection before modeling to reduce noise and training time. Use mutual information, variance threshold, or correlation filtering to reduce to a manageable feature set. For >500 features this is critical.

**Data size guardrails:**
- <100K rows — single node, full data
- 100K–10M rows — full data, set time_limit carefully, check memory with `psutil` before and after training
- \>10M rows — sample for feature exploration, full data for final AutoGluon training, or load `../distributed-training/SKILL.md` for distributed training

Write EDA visualizations to the working file (notebook cells in Snowsight; working directory in CLI) for the quality gate findings — target distribution, feature distributions, correlation matrix, class balance, outlier patterns, and any other plots relevant to the dataset. For high-dimensional data (>50 features), focus on the top features by variance or correlation with the target.

**Output:** Clean dataset, evaluation split, baseline score, any flags.

**⚠️ Do not write Step 3 code until Step 2 has been run.**

**📋 REPORT:** EDA findings, flags from quality gates, how they influence the modeling approach (e.g., "High missingness in X suggests...", "Class imbalance of 10:1 means I'll use..."). Then write and run Step 3.

### Step 3: Build

Run autonomously — show your code, reasoning, and decisions as you go. If the user provides feedback mid-experiment, incorporate their guidance into the next iteration rather than restarting. The current best model is always a valid checkpoint to resume from. Between two approaches with similar performance, prefer the one that is easier to debug, retrain, and serve.

**Experiment tracking:** Log to Snowflake Experiment Tracking **incrementally — per trial, as each trial finishes**. Do NOT batch logging until the end of Step 3.

See `../experiment-tracking/SKILL.md` → Common Pitfalls for ExperimentTracking class basics.

- **Setup (once, before Trial 1):** Import with `from snowflake.ml.experiment import ExperimentTracking`. Initialize with `exp = ExperimentTracking(session=session)`, then call `exp.set_experiment('<experiment_name>')` to create or resume the experiment. Do this *before* the first trial runs.
- **Per trial (mandatory order):**
  1. Run the trial (AutoGluon `fit()` or clustering algo).
  2. **As soon as that trial's training finishes**, immediately log every leaderboard row as its own run with `exp.start_run(...)` → `log_params` → `log_metrics` → `log_artifact` (see code in the task-specific sections below).
  3. Capture the experiment URL printed when the first run ends — it looks like `🧪 View experiment at: https://app.snowflake.com/...`. Save it so you can include it in the chat REPORT.
  4. Open the `t{N}_summary` run. Inside the context manager, log the always-write items first (leaderboard, headline metric, experiment URL), *then* attempt feature importance / SHAP / diagnostic plots wrapped in `try/except` (see cost gate below).
  5. **Update `<experiment_name>_manifest.json`** with the trial's elapsed time and the ET run URL so it points to the artifacts.
  6. Post the per-trial REPORT in chat (URL + leaderboard + best-vs-baseline + ⏱ + insight). **Do not start the next trial until the current trial is logged, manifest is updated, and the REPORT is posted.**

If a trial logs zero runs to experiment tracking, treat that as a bug — stop and fix before proceeding.

**Experiment journal:** Append running notes to the journal as you work. Natural prose, chronological. The chat REPORT is the canonical narrative; the journal is a durable scratchpad — link to the trial files (`trial_3_relational.py`) when relevant. Not a contract; no required template. Example entry:

```
## Trial 3: Relational features from orders table (`trial_3_relational.py`)
Hypothesis was that customer order history (recency, frequency, monetary) would
improve churn prediction. Result: +0.04 F1 (0.81 → 0.85) → KEEP. Recency was
the strongest signal — 90+ day non-orderers churn at 3x the base rate.
```

**⏱ Time tracking — enforce at every decision point.**
Record `elapsed = time.time() - start_time` before and after every trial and FE phase. Before starting a new trial, compute remaining budget: `remaining = budget - elapsed`. If the next trial's estimated duration exceeds the remaining budget, skip it and go directly to Step 4 (Deliver). If the planned trials finished and `remaining` still fits another meaningful trial (e.g., longer `time_limit`, stronger preset, OpenFE retry, HPO mode, or a different feature set), **add a new trial** rather than ending early. Stop adding trials once two in a row fail to improve, or `remaining` is too small to matter. Report elapsed and remaining time in every REPORT. The budget is a commitment to the user, not a suggestion.

**Minimum-trial guard:** If you reach Step 3 and `remaining < 180s` (e.g., Step 2 / FE consumed most of the budget), still run **at least one** short trial: `time_limit=120, presets='medium_quality'`. Never skip from Step 2 to Step 4 with no model — Step 4 needs a champion. If the budget is genuinely exhausted, post a REPORT explaining the overrun and ask the user before continuing.

#### Feature Engineering

Applies to all task types. This must be real and substantive — not just "impute + encode." Transform the feature space to give the model better inputs.

- Feature selection: drop low-signal features (variance threshold, mutual information, correlation filtering).
- Outlier handling: clip, transform, or remove based on EDA findings (Step 2)
- Interaction features: ratios, differences, products with business meaning
- Temporal features: recency, frequency, time-since-event, rolling aggregations, lag features from date/sequence columns
- Domain-specific features: relational aggregations (join in SQL, not pandas), text features via Cortex AI — run in SQL: `SNOWFLAKE.CORTEX.SENTIMENT()`, `SNOWFLAKE.CORTEX.CLASSIFY_TEXT()`, `SNOWFLAKE.CORTEX.EMBED_TEXT_768()`
- Check the Feature Store for existing managed features before generating from scratch
- Also consider: RFM, geographic features, high-cardinality encoding, skew correction

**Task-specific guidance:**
- **Clustering:** No model handles FE — scaling and dimensionality reduction are critical because clustering is distance-based.
- **Forecasting:** TimeSeriesPredictor handles lags, trend, and seasonality internally. Focus agent FE on known covariates (calendar features with cyclical encoding, holiday flags, external signals) and static features (entity metadata).
- **Classification & Regression:** AutoGluon handles missing values, categorical encoding, model selection, HPO, stacking. Focus agent FE on what AutoGluon won't do on its own. After agent FE, run OpenFE to search for pairwise interactions (see config below).

  **OpenFE configuration:**

  Required guards:
  - Fill NaN in object columns with a sentinel string — NaN hangs GroupBy operators.
  - Cast pandas nullable dtypes (`Int64`, `Float64`, `boolean`) to numpy `float64` with a fillna sentinel — NAType crashes multiproc workers.
  - Use a PID-suffixed `tmp_save_path` and unlink any stale file before fit — leftover feather files race across workers.
  - After applying discovered features via `tree_to_formula()`, replace ±inf with NaN before AutoGluon fit — sklearn refuses inf.

  ```python
  cat_cols = X_train.select_dtypes(include='object').columns
  X_train[cat_cols] = X_train[cat_cols].fillna('_MISSING_')
  X_test[cat_cols]  = X_test[cat_cols].fillna('_MISSING_')

  for c in X_train.columns:
      if str(X_train[c].dtype) in ('Int64', 'Float64', 'boolean'):
          X_train[c] = X_train[c].astype('float64').fillna(-1)
          X_test[c]  = X_test[c].astype('float64').fillna(-1)

  import os
  tmp_path = f'/tmp/openfe_data_{os.getpid()}.feather'
  if os.path.exists(tmp_path):
      os.unlink(tmp_path)

  ofe = OpenFE()
  features = ofe.fit(
      data=X_train,
      label=y_train,
      n_jobs=1,              # tune n_jobs and feature count to instance memory and data size
      tmp_save_path=tmp_path,
      verbose=True,
      n_data_blocks=8,
  )
  # Returned list is sorted by importance. Do NOT access `f.score` — it does not exist.

  # After applying discovered features via `tree_to_formula()`:
  import numpy as np
  X_train = X_train.replace([np.inf, -np.inf], np.nan)
  X_test  = X_test.replace([np.inf, -np.inf], np.nan)
  ```

  Pre-filter to ≤30 features for the initial run — OpenFE scales quadratically with feature count.
  If raw feature count > 30, rank by mutual information with the target (or variance, for unsupervised) and keep the top 30. Expand if the data warrants it and the instance can support it.

  Time reference (CPU_X64_S, 5K rows):
    5 features → 8s | 20 features → 57s | 50 features → 4.3 min | 100 features → 18 min
  Row count also matters: 76K rows × 30 features → ~70s on HIGHMEM_X64_M. Scaling is not linear.

  ⚠️ `ofe.fit()` writes internal temp files to CWD beyond `tmp_save_path`. If CWD is read-only (e.g., Snowflake Notebooks), `os.chdir('/tmp')` before calling `fit()` and use absolute paths for subsequent file operations.

  ⚠️ During FE, **do not call `ofe.transform()`**. Fit OpenFE on training data only, then extract formulas with `tree_to_formula()` and apply them manually to both train/test.

**Post-FE check:** Review the full feature set — original, agent-engineered, and OpenFE. Drop redundant or highly correlated features. If OpenFE features overlap with manual features, pick the stronger one. Decide on the final set: is it good enough to train on, or are there clear opportunities to improve before spending the training budget? If not, iterate before committing to training.

**📋 REPORT:** Final feature count and summary. Highlight which engineered features you expect to matter most and what was dropped. State whether you're confident in the set or flag concerns. Report ⏱ elapsed time / remaining budget — if FE consumed a significant portion of the budget, reduce the number of planned trials or shorten `time_limit` to stay within budget. Outline the adjusted training plan.

#### Training

##### Clustering

No AutoGluon path — agent-driven. Quality of clusters depends entirely on feature preparation (see FE section above).

```
1. Clustering algorithms
   - KMeans, HDBSCAN, Gaussian Mixture — try multiple, they find different structure
   - ⚠️ Log each algorithm/k combination as a separate experiment run IMMEDIATELY
     after that fit/score finishes — do not batch logging until the trial ends.
     Wrap each fit in `with exp.start_run(f"t{trial_num}_{algo}_k{k}"):`.

2. Evaluate and profile
   - k selection: elbow method + silhouette score (unless user specified k)
   - Metrics: silhouette, calinski-harabasz, cluster sizes
   - Cluster profiling: describe each cluster by feature distributions relative
     to the population. Name each cluster by its dominant trait. Flag outlier members.
   - Save cluster profile plots as artifacts: `exp.log_artifact('/tmp/plot.png', artifact_path='plots')`
```

##### Forecasting

Use **AutoGluon TimeSeriesPredictor** (not TabularPredictor).

```
1. AutoGluon TimeSeriesPredictor — model experimentation and tuning
   - Models: AutoARIMA, AutoETS, DeepAR, TFT, Chronos, Prophet, LightGBM
   - Temporal cross-validation via num_val_windows (2-5 typical, proportional to data length)
   - Set time_limit per the trial plan from Step 1 (default 10 min per trial)
   - Multi-series: if some series fail to train (too short, constant, degenerate),
     log which series failed and continue with the rest. Report partial model coverage.

2. Evaluate on temporal holdout
   - Plot forecast components (trend, seasonality, holidays) for the winning model.
     AutoGluon exposes the underlying model — for Prophet, use model.plot_components();
     for statistical models, plot trend and seasonal decomposition separately.
   - For Prophet-family models, overlay detected changepoints on the forecast plot
     to identify regime shifts in the data.
   - Prediction intervals, worst-series analysis, accuracy by horizon.
   - Save forecast component and changepoint plots as artifacts: `exp.log_artifact('/tmp/plot.png', artifact_path='plots')`

3. Log forecasting results to experiment tracking
   ⚠️ Run this block IMMEDIATELY after THIS trial's predictor.fit() returns —
   before starting any subsequent trial. Logging is per-trial, not end-of-Step-3.

   `TimeSeriesPredictor` does not expose a fit-level callback hook (no `callbacks=`
   kwarg, no `AbstractCallback` analog). Forecasting logs runs post-hoc by iterating
   `predictor.leaderboard()` after `fit()` returns — same shape as Tabular's per-model
   runs + summary, just in a burst at the end instead of streaming live.

   Log each model from this trial's leaderboard as a separate run.
   Log diagnostic plots as artifacts on the best model's run.
     # Use `safe_run_name` from `references/autogluon-callback.md` — sanitizes
     # forecasting model names like "ChronosWithRegressor[bolt_small]" for
     # Snowflake unquoted identifiers.
     leaderboard = predictor.leaderboard(test_data, extra_metrics=[...])
     best_model_name = leaderboard.iloc[0]['model']
     for _, row in leaderboard.iterrows():
         run_name = f"t{trial_num}_{safe_run_name(row['model'])}"
         with exp.start_run(run_name):
             hp = predictor.info().get('model_info', {}).get(row['model'], {}).get('hyperparameters', {})
             exp.log_params(hp)
             exp.log_metrics({col: float(row[col]) for col in leaderboard.columns if col not in ['model', 'can_infer', 'fit_order'] and isinstance(row[col], (int, float))})
             if row['model'] == best_model_name:
                 exp.log_artifact('/tmp/plot_name.png', artifact_path='plots')
```

##### Classification & Regression

Use **AutoGluon** for model experimentation and tuning.

```
1. AutoGluon TabularPredictor — model experimentation and tuning
   - Set time_limit per the trial plan from Step 1 (default 10 min per trial)
   - Presets: medium_quality (fast, single-layer stacking — good for exploration),
     best_quality (full stacking + repeated bagging — use for final model with
     longer time_limit). Match preset to the trial's time_limit.
   - For imbalanced classification: set `sample_weight='balance_weight'` or use a class-balanced eval_metric.
     Consider SMOTE if class weights alone are insufficient.

2. Explainability
   - Feature importance: predictor.feature_importance(test_data) for permutation-based importance.
     ⚠️ **Cost gate — required before calling `feature_importance` on a `best_quality` predictor.**
     On stacked best_quality predictors (stack_levels > 1, ~37 models), default
     FI runs 5 sets × 25 features × 37 models and can take 40+ minutes — enough
     to blow the budget at the very end of a run. Before the call:
       - Compute estimated cost; compare to remaining budget.
       - If predictor has `stack_levels > 1` (or just always for best_quality),
         pass conservative caps: `subsample_size=5000, num_shuffle_sets=1,
         features=<top 10 by leaderboard model contributions>`.
       - If estimated cost > remaining budget, **skip FI entirely** and note it
         in the REPORT — never overrun the budget for FI.
   - SHAP: try on the trained model — impute nulls with mode before passing to SHAP,
     sample background (100 rows) and explanation data (100 rows). If SHAP fails
     (incompatible model, serialization), fall back to .feature_importance().
   - Diagnostic plots: confusion matrix, per-class precision/recall, ROC/PR curves
     (classification), residual plots and error distribution (regression), SHAP summary.
     Save all as artifacts.

3. Log to experiment tracking — per-model via callback, per-trial via summary
   Use AutoGluon's `AbstractCallback` so each model logs as it finishes training (live in Snowsight).
   After `predictor.fit()` returns, open a per-trial summary run with the test leaderboard + artifacts.

   See `references/autogluon-callback.md` for the full `ExperimentLogger` class, trial-number lookup,
   `predictor.fit(callbacks=[...])` call, and summary-run snippet.

```

**Output:** Trained model, experiment log with all trial metrics and artifacts, leaderboard.

**📋 REPORT (in chat after each trial — post BEFORE starting the next trial):**

Report the trial results in chat. Highlight the leading model across all trials so far and why.

**⚠️ The experiment tracking URL is mandatory in every per-trial REPORT.** It is the user's primary way to inspect runs. If you don't have one yet, you logged late or skipped logging — go back and fix Step 3 before reporting. The URL stays the same for every trial in a session; reuse the captured URL.

**REPORT contents — include every item below in the chat message. Use the checklist for your task type:**

*If task type is classification, regression, or forecasting:*
- [ ] **Experiment tracking URL** (paste the `https://app.snowflake.com/...` link) + this trial's summary run URL (`.../runs/t<N>_summary`)
- [ ] AutoGluon leaderboard (as table)
- [ ] Best model from this trial vs. baseline, and vs. current champion (if one exists)
- [ ] Overfitting check — train/val/test side-by-side (as table)
- [ ] ⏱ Elapsed time / remaining budget — if over budget, say so and skip to Step 4
- [ ] What worked, what didn't, plan for next trial (if continuing)

*If task type is clustering:*
- [ ] **Experiment tracking URL** (paste the `https://app.snowflake.com/...` link) + this trial's summary run URL (`.../runs/t<N>_summary`)
- [ ] Best configuration per algorithm tried, with scores (as table)
- [ ] Best configuration from this trial vs. baseline, and vs. current champion (if one exists)
- [ ] Cluster profiles for the best configuration — describe each cluster, name by dominant trait
- [ ] ⏱ Elapsed time / remaining budget — if over budget, say so and skip to Step 4
- [ ] What worked, what didn't, plan for next trial (if continuing)

### Step 4: Deliver

**⚠️ The last trial MUST get both its per-trial REPORT (from Step 3) AND the FINAL REPORT below. Do not skip the per-trial REPORT for the last trial.**

**Champion selection:** `predictor.model_best` (AutoGluon's val-based pick) is the champion. The test set is the holdout — used once for reporting, never for selection or re-ranking. Log both val and test scores to ET so val/test gaps are visible across runs. Caveats: with `dynamic_stacking=True` (best_quality preset), `model_best` reflects the main fit's val score, not the sub-fit probe; `WeightedEnsemble_*` carries slight val optimism vs single models within ~0.001; `refit_full=True` inherits the bagged model's val score.

**📋 FINAL REPORT (in chat):**

Summarize the full experiment in chat.

**FINAL REPORT contents — include every item below in the chat message. Use the checklist for your task type:**

*If task type is classification, regression, or forecasting:*
- [ ] **Experiment tracking URL** (reuse the URL captured in Step 3 — required) + best-trial summary run URL
- [ ] Cross-trial leaderboard from experiment tracking — all models across all trials, all metrics for the task type (as table)
- [ ] Champion model — why it won, full metric set vs. baseline
- [ ] Top 5 features by importance
- [ ] Key findings — what drove performance, surprising patterns, data insights
- [ ] Flags — data quality, fairness, or imbalance issues
- [ ] ⏱ Total elapsed time vs. budget
- [ ] All artifacts — working file path(s)

*If task type is clustering:*
- [ ] **Experiment tracking URL** (reuse the URL captured in Step 3 — required) + best-trial summary run URL
- [ ] Cross-trial comparison — best configuration per algorithm across all trials, with scores (as table)
- [ ] Champion configuration — why it won, description of the segments, vs. baseline
- [ ] Key findings — what separates the clusters, actionable insights
- [ ] Flags — data quality issues, unstable clusters, outlier segments
- [ ] ⏱ Total elapsed time vs. budget
- [ ] All artifacts — working file path(s)

1. **Update `<experiment_name>_manifest.json`** — add total elapsed time, champion model registry reference (if registered), and Snowflake objects created (experiment name, training table, working file paths).

2. **Write a final summary in the journal:**
   - Summary — best model, key result, what drove performance
   - What else could be tried — feature engineering ideas, model families not explored, data improvements

3. **Suggest next steps:**
   - **Register model** — present registration candidates from the leaderboard and let the user choose how to register.

     **Pick candidates to show:**
     - Always show the leaderboard's top model.
     - If the top model is an ensemble (e.g., `WeightedEnsemble_L2`), also show the best standalone (non-ensemble) model and report the score gap.
     - For forecasting and clustering, only Option B applies.

     **Option A — Native sklearn pipeline** (classification/regression, standalone winner only)

     See [`references/native_sklearn_extraction.py`](references/native_sklearn_extraction.py) for the working extraction (LightGBM verified; XGBoost / CatBoost branches outlined). The native estimator is wrapped in `sklearn.pipeline.Pipeline`: step 1 is a fresh `ColumnTransformer` (median-impute numerics, most-frequent + `OneHotEncoder` for categoricals, with categorical levels reused from AG's `CategoryFeatureGenerator.category_map` for unseen-value parity); step 2 is the refit native estimator. Register with `framework=scikit-learn`, raw features as sample input, and `conda_dependencies` matching the native model's module (e.g., `lightgbm`, `xgboost`).

     **Before calling `log_model`, read [`../debug-inference/SKILL.md`](../debug-inference/SKILL.md) and apply the explicit `signatures=` + `nullable=False` pattern.** Warehouse inference on these extracted pipelines hits nullable dtypes by default (the embedded `SimpleImputer` raises on `pd.NA`); registering with the canonical signature up front avoids a guaranteed crash on first `mv.run`.

     **Option B — CustomModel wrapping the full AutoGluon predictor** (required for ensembles, forecasting, or whenever you want the leaderboard's top score preserved as-is)

     1. Wrap the predictor in a `CustomModel` subclass per `../model-registry/SKILL.md`. AG-specific: load with `TabularPredictor.load(path)` / `TimeSeriesPredictor.load(path)` in `__init__`; `predict` returns a `pd.DataFrame` with a `prediction` column.
     2. Pin AutoGluon in `pip_requirements` (all components resolved to the same version): `autogluon.tabular`, `autogluon.core`, `autogluon.features` (all `==1.5.1b20260415`), plus `autogluon.timeseries==1.5.1b20260415` for forecasting. Only include `autogluon.multimodal==1.5.1b20260415` if it was used at train time; **if so, also pin `ray==<runtime_version>` in `pip_requirements`** to match the training runtime (capture via `import ray; print(ray.__version__)`) — otherwise Ray will resolve to a version `autogluon.multimodal` doesn't support and inference will fail.

     **Both options:** If OpenFE features were discovered, compute them directly in the pipeline (Option A) or wrapper (Option B) — e.g., `df['feat'] = df['A'] * df['B']`. Do not call `ofe.transform()` at inference; extract formulas with `tree_to_formula()` and hardcode them.

     After the user chooses, load `../model-registry/SKILL.md` for registry patterns and proceed with the chosen option.
   - **Deep research** — additional trials with iterative hypothesis → implement → evaluate → KEEP/REVERT cycles. Additional feature engineering, model families, stacking strategies, and aggressive HPO sweeps beyond what AutoGluon explored. Always offer this as the primary continuation path.
   - **Training script** (notebook in Snowsight, `train.py` in CLI) — locked-in retraining, not a re-search. Requirements:
     - Reproduce the full pipeline: all FE transformations from Step 3, then the winning model with exact hyperparameters. If OpenFE features were discovered, hardcode the formulas directly (no OpenFE dependency).
     - All config at the top: data source, feature definitions, hyperparameters, stack levels, bag folds, time limit, version.
     - Model selection locked — only the winning model families with their exact parameters. AutoGluon still handles stacking/bagging mechanics.
     - Include registration (CustomModel wrapper + `log_model()`) so the script produces a registered model end-to-end.
     - **Editable hyperparameter config:** Surface the winning model's hyperparameters as a plain dict at the top — e.g., `lgbm_params = {"learning_rate": 0.059, "max_depth": 7, ...}`. Extract with `predictor.info()`, pass via `hyperparameters={ModelFamily: params_dict}`.
     - Self-contained and reproducible in a new environment. No dead ends, no reverted experiments.
   - **Inference** — load `../batch-inference-jobs/SKILL.md` for batch or `../spcs-inference/SKILL.md` for real-time
   - **Feature Store** — load `../feature-store/SKILL.md` for managed feature views
   - **Monitoring** — load `../model-monitor/SKILL.md` for model version monitor and `../gateway-ab-testing/SKILL.md` for gateway model monitor

   Additional options depending on the use case:
   - **Dataset snapshot** — load `../datasets/SKILL.md` for dataset versioning
   - **Retraining** — load `../ml-pipeline-orchestration/SKILL.md` for pipeline orchestration and scheduled retraining
   - **Lineage** — load `../ml-lineage/SKILL.md` for end-to-end lineage tracing
