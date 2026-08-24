# AutoGluon callback for live experiment-tracking

Drop-in pattern: per-model logging via AutoGluon's `AbstractCallback`, plus a per-trial summary run. Tabular only — `TimeSeriesPredictor` has no fit-level callback hook.

For ExperimentTracking class basics (constructor, `set_experiment`, `with start_run` exception safety, common pitfalls), see [`../../experiment-tracking/SKILL.md`](../../experiment-tracking/SKILL.md).

## ExperimentLogger class

```python
import re
from snowflake.ml.experiment import ExperimentTracking
from autogluon.core.callbacks import AbstractCallback

def safe_run_name(name: str) -> str:
    # Snowflake unquoted identifiers allow [A-Za-z0-9_$] only. Forecasting model
    # names like "ChronosWithRegressor[bolt_small]" must be sanitized.
    return re.sub(r"[^A-Za-z0-9_$]", "_", name)

class ExperimentLogger(AbstractCallback):
    def __init__(self, exp, trial_num):
        super().__init__()
        self.exp = exp
        self.trial_num = trial_num

    def __getstate__(self):
        # AutoGluon pickles the trainer (including callbacks) after every model
        # fit. Snowpark Session is not picklable — drop self.exp from the pickle.
        # Under best_quality (dynamic_stacking), the unpickled callback IS re-fired
        # during the sub-fit phase. _after_model_fit guards against self.exp=None,
        # so sub-fit runs are silently skipped (not logged) instead of crashing.
        state = self.__dict__.copy()
        state["exp"] = None
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)

    def _after_model_fit(self, trainer, model_names, stack_name, level, **kwargs):
        # **kwargs absorbs args added in future AutoGluon versions; do not remove.
        if self.exp is None:
            # Re-fired post-pickle (e.g., DyStack sub-fit). Skip silently —
            # main-fit pass will re-log the same models.
            return False
        # model_names is a LIST (usually 1, sometimes more under HPO). Iterate it.
        for name in model_names:
            # Include stack_name in the run name: dynamic_stacking (best_quality
            # preset) fits each model TWICE (sub-fit + main fit) with the same
            # `name` but different `stack_name`. Without this, the second pass
            # collides on start_run and raises "Run exists but cannot be resumed".
            run_name = safe_run_name(f"t{self.trial_num}_{name}_{stack_name}")
            with self.exp.start_run(run_name):
                self.exp.log_params({
                    "trial_num": str(self.trial_num),
                    "model_name": name,
                    "model_type": trainer.get_model_attribute(name, "type", default=None) or "",
                    "stack_name": stack_name,
                    "level": str(level),
                })
                # All hyperparameters via load_model.params
                self.exp.log_params(getattr(trainer.load_model(name), "params", {}) or {})
                # Performance + cost metrics; pass default=None — get_model_attribute raises otherwise
                metrics = {}
                for attr in ["val_score", "eval_metric_score", "fit_time",
                             "predict_time", "predict_1_time", "disk_usage"]:
                    v = trainer.get_model_attribute(name, attr, default=None)
                    if v is not None:
                        metrics[attr] = float(v)
                if metrics:
                    self.exp.log_metrics(metrics)
        return False
```

> AutoGluon's `AbstractCallback` is flagged experimental in 1.5.x. Verified against `autogluon==1.5.1b20260415` (2026-05-22). Re-verify the `_after_model_fit` signature on any AutoGluon upgrade.

## Trial number lookup

Determine `trial_num` from existing runs in the experiment — no manifest dependency:

```python
import re
existing = session.sql(
    f"SHOW RUNS IN EXPERIMENT {db}.{schema}.{experiment_name}"
).collect()
# Snowflake echoes run names UPPERCASED ("T1_LIGHTGBMXT"); use IGNORECASE so
# the trial counter actually advances past 1.
trial_nums = [
    int(m.group(1))
    for r in existing
    if (m := re.match(r"^t(\d+)_", r["name"], re.IGNORECASE))
]
trial_num = (max(trial_nums) + 1) if trial_nums else 1
```

## Pass to fit

```python
# ag_path must be fresh per trial
predictor = TabularPredictor(label=label, eval_metric=metric, path=ag_path)
predictor.fit(
    train_data,
    time_limit=time_limit,
    presets=preset,
    callbacks=[ExperimentLogger(exp, trial_num)],
)
```

`with exp.start_run(...)` commits even on exception, so failed model fits don't leave orphan RUNNING runs. No try/except needed for that.

> Do NOT wrap `predictor.fit(...)` in `redirect_stdout(buf)` — it buffers all callback output until fit returns, hiding live errors and breaking observability. To capture the experiment-URL line, parse stderr or the AutoGluon log file instead.

## Summary run after fit

```python
leaderboard = predictor.leaderboard(test_data, extra_metrics=[...])
leaderboard.to_csv("/tmp/leaderboard.csv", index=False)
best = leaderboard.iloc[0]

with exp.start_run(safe_run_name(f"t{trial_num}_summary")):  # can't reopen later — log everything in one block
    exp.log_params({
        "preset": preset,
        "time_limit": str(time_limit),
        "eval_metric": eval_metric,
        "problem_type": predictor.problem_type,
        "fe_delta": fe_delta_description,  # one-line description vs baseline
        "best_model": best["model"],
        "n_models_trained": str(len(leaderboard)),
        "status": "ok",  # "partial" if some models failed
    })
    exp.log_metrics({"best_test_score": float(best["score_test"])})
    exp.log_artifact("/tmp/leaderboard.csv", artifact_path="leaderboards")
```

If a per-model log call hits `EXPERIMENT_RUN_PROPERTY_SIZE_LIMIT_EXCEEDED` (error 400003), the run is poisoned for further metric logs. Trim or split very large hyperparameter dicts (common for ensemble-of-ensemble configs).
