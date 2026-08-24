# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Snowflake GEPA engine with pluggable iteration strategy.

This module provides ``SnowGEPAEngine``, a subclass of GEPA's
``GEPAEngine`` that replaces the hardcoded merge-then-reflective loop
with a pluggable ``IterationStrategy`` protocol.  This mirrors the
iteration_strategy refactor in the local GEPA fork and enables custom
proposer scheduling (e.g. interleaved reflection, multi-strategy
tournaments) without modifying the installed GEPA package.

Use ``patched_engine()`` to inject ``SnowGEPAEngine`` into the relevant
GEPA module namespaces so that ``optimize_anything()`` and
``gepa.optimize()`` instantiate it instead of the stock ``GEPAEngine``.
"""

from __future__ import annotations

import contextlib
import traceback
from collections.abc import Iterator
from typing import Any, Protocol, runtime_checkable

from gepa.core.adapter import GEPAAdapter
from gepa.core.callbacks import (
    BudgetUpdatedEvent,
    CandidateAcceptedEvent,
    CandidateRejectedEvent,
    ErrorEvent,
    GEPACallback,
    IterationEndEvent,
    IterationStartEvent,
    MergeAcceptedEvent,
    MergeAttemptedEvent,
    MergeRejectedEvent,
    OptimizationEndEvent,
    OptimizationStartEvent,
    StateSavedEvent,
    ValsetEvaluatedEvent,
    notify_callbacks,
)
from gepa.core.data_loader import DataLoader
from gepa.core.engine import GEPAEngine
from gepa.core.state import (
    EvaluationCache,
    FrontierType,
    GEPAState,
    ValsetEvaluation,
    initialize_gepa_state,
)
from gepa.logging.experiment_tracker import ExperimentTracker
from gepa.logging.logger import LoggerProtocol
from gepa.proposer.base import CandidateProposal, ProposeNewCandidate
from gepa.proposer.merge import MergeProposer
from gepa.proposer.reflective_mutation.reflective_mutation import (
    ReflectiveMutationProposer,
)
from gepa.strategies.eval_policy import EvaluationPolicy
from gepa.utils import StopperProtocol

# ===========================================================================
# Iteration Strategy Protocol (ported from fork)
# ===========================================================================


@runtime_checkable
class IterationStrategy(Protocol):
    """Strategy that decides which proposer(s) to run each iteration.

    The engine calls ``get_proposers`` at the start of each iteration,
    iterates through the returned list, and breaks after the first accepted
    proposal.  After acceptance or rejection, the corresponding hook is
    called so the strategy can update its internal scheduling state.
    """

    def get_proposers(
        self, state: GEPAState[Any, Any]
    ) -> list[ProposeNewCandidate[Any]]:
        """Return an ordered list of proposers to try this iteration."""
        ...

    def on_proposal_accepted(
        self,
        proposer: ProposeNewCandidate[Any],
        proposal: CandidateProposal[Any],
        state: GEPAState[Any, Any],
    ) -> None:
        """Handle the hook fired after the engine accepts a proposal."""
        ...

    def on_proposal_rejected(
        self,
        proposer: ProposeNewCandidate[Any],
        proposal: CandidateProposal[Any],
        state: GEPAState[Any, Any],
    ) -> None:
        """Handle the hook fired after the engine rejects a proposal."""
        ...


# ===========================================================================
# Default Iteration Strategy (ported from fork)
# ===========================================================================


class MergeThenReflectiveStrategy:
    """Default iteration strategy matching the original hard-coded merge scheduling.

    Behaviour:
    - When a merge is scheduled (``merges_due > 0``) **and** the previous
      iteration discovered a new program, the merge proposer is returned as
      the first proposer, with reflective as fallback.
    - Otherwise the reflective mutation proposer is returned.
    - After a successful reflective mutation, a merge is scheduled for a
      future iteration (if the budget allows).
    """

    def __init__(
        self,
        reflective_proposer: ReflectiveMutationProposer,
        merge_proposer: MergeProposer | None = None,
    ):
        self.reflective = reflective_proposer
        self.merge = merge_proposer

    def get_proposers(
        self, state: GEPAState[Any, Any]
    ) -> list[ProposeNewCandidate[Any]]:
        if (
            self.merge is not None
            and self.merge.use_merge
            and self.merge.merges_due > 0
            and self.merge.last_iter_found_new_program
        ):
            self.merge.last_iter_found_new_program = False
            return [self.merge, self.reflective]
        if self.merge is not None:
            self.merge.last_iter_found_new_program = False
        return [self.reflective]

    def on_proposal_accepted(
        self,
        proposer: ProposeNewCandidate[Any],
        proposal: CandidateProposal[Any],
        state: GEPAState[Any, Any],
    ) -> None:
        if self.merge is None:
            return
        if proposer is self.merge:
            self.merge.merges_due -= 1
            self.merge.total_merges_tested += 1
            self.merge.last_iter_found_new_program = False
        elif proposer is self.reflective:
            self.merge.last_iter_found_new_program = True
            if self.merge.total_merges_tested < self.merge.max_merge_invocations:
                self.merge.merges_due += 1

    def on_proposal_rejected(
        self,
        proposer: ProposeNewCandidate[Any],
        proposal: CandidateProposal[Any],
        state: GEPAState[Any, Any],
    ) -> None:
        if self.merge is not None and proposer is self.merge:
            self.merge.last_iter_found_new_program = False


# ===========================================================================
# Acceptance Criterion Protocol (ported from fork)
# ===========================================================================


@runtime_checkable
class AcceptanceCriterion(Protocol):
    """Decides whether a proposed candidate should be accepted."""

    def should_accept(self, proposal: CandidateProposal, state: GEPAState) -> bool: ...


class StrictImprovementAcceptance:
    """Accept only if new subsample score sum strictly exceeds old sum."""

    def should_accept(self, proposal: CandidateProposal, state: GEPAState) -> bool:
        old_sum = sum(proposal.subsample_scores_before or [])
        new_sum = sum(proposal.subsample_scores_after or [])
        return new_sum > old_sum


class ImprovementOrEqualAcceptance:
    """Accept if new subsample score sum is >= old sum (allows lateral moves)."""

    def should_accept(self, proposal: CandidateProposal, state: GEPAState) -> bool:
        old_sum = sum(proposal.subsample_scores_before or [])
        new_sum = sum(proposal.subsample_scores_after or [])
        return new_sum >= old_sum


# ===========================================================================
# SnowGEPAEngine — subclass with iteration_strategy-driven run()
# ===========================================================================


class SnowGEPAEngine(GEPAEngine):
    """GEPAEngine subclass that uses a pluggable IterationStrategy.

    The installed GEPAEngine has merge/reflective scheduling hardcoded in
    its ``run()`` method.  This subclass overrides ``run()`` with the
    strategy-driven loop from the GEPA fork, allowing custom proposer
    scheduling without modifying the installed package.
    """

    def __init__(
        self,
        *,
        adapter: GEPAAdapter,
        run_dir: str | None,
        valset: list | DataLoader | None,
        seed_candidate: dict[str, str],
        perfect_score: float | None,
        seed: int,
        reflective_proposer: ReflectiveMutationProposer,
        merge_proposer: MergeProposer | None,
        frontier_type: FrontierType,
        logger: LoggerProtocol,
        experiment_tracker: ExperimentTracker,
        callbacks: list[GEPACallback] | None = None,
        track_best_outputs: bool = False,
        display_progress_bar: bool = False,  # accepted but ignored
        raise_on_exception: bool = True,
        use_cloudpickle: bool = False,
        stop_callback: StopperProtocol | None = None,
        val_evaluation_policy: EvaluationPolicy | None = None,
        evaluation_cache: EvaluationCache | None = None,
        # New parameters from the fork
        iteration_strategy: IterationStrategy | None = None,
        acceptance_criterion: AcceptanceCriterion | None = None,
    ):
        if display_progress_bar:
            raise ValueError("display_progress_bar cannot be used with this engine")

        super().__init__(
            adapter=adapter,
            run_dir=run_dir,
            valset=valset,
            seed_candidate=seed_candidate,
            perfect_score=perfect_score,
            seed=seed,
            reflective_proposer=reflective_proposer,
            merge_proposer=merge_proposer,
            frontier_type=frontier_type,
            logger=logger,
            experiment_tracker=experiment_tracker,
            callbacks=callbacks,
            track_best_outputs=track_best_outputs,
            display_progress_bar=False,
            raise_on_exception=raise_on_exception,
            use_cloudpickle=use_cloudpickle,
            stop_callback=stop_callback,
            val_evaluation_policy=val_evaluation_policy,
            evaluation_cache=evaluation_cache,
        )
        self.acceptance_criterion: AcceptanceCriterion = (
            acceptance_criterion or StrictImprovementAcceptance()
        )
        self.iteration_strategy: IterationStrategy = (
            iteration_strategy
            or MergeThenReflectiveStrategy(
                reflective_proposer=reflective_proposer,
                merge_proposer=merge_proposer,
            )
        )

    # ------------------------------------------------------------------
    # Adapter state sync (fork addition — no-op if adapter lacks methods)
    # ------------------------------------------------------------------

    def _sync_adapter_state_to_state(self, state: GEPAState) -> None:
        """Snapshot adapter state into GEPAState before saving."""
        getter = getattr(self.adapter, "get_adapter_state", None)
        if getter is not None:
            state.adapter_state = dict(getter())  # type: ignore[attr-defined]

    def _sync_state_to_adapter(self, state: GEPAState) -> None:
        """Restore persisted adapter state into the adapter after loading."""
        setter = getattr(self.adapter, "set_adapter_state", None)
        if setter is not None:
            setter(state.adapter_state)  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Overridden run() with iteration_strategy loop
    # ------------------------------------------------------------------

    def run(self) -> GEPAState:
        """Run the optimization loop using pluggable iteration strategy.

        This replaces the hardcoded merge-then-reflective scheduling in the
        installed GEPAEngine with the strategy-driven loop from the fork.
        """
        # Prepare valset
        valset = self.valset
        if valset is None:
            raise ValueError("valset must be provided to SnowGEPAEngine.run()")

        def valset_evaluator(
            program: dict[str, str],
        ) -> ValsetEvaluation:
            all_ids = list(valset.all_ids())
            outputs, scores, objective_scores = self.evaluator(
                valset.fetch(all_ids), program
            )
            outputs_dict = dict(zip(all_ids, outputs, strict=False))
            scores_dict = dict(zip(all_ids, scores, strict=False))
            objective_scores_dict = (
                dict(zip(all_ids, objective_scores, strict=False))
                if objective_scores is not None
                else None
            )
            return ValsetEvaluation(
                outputs_by_val_id=outputs_dict,
                scores_by_val_id=scores_dict,
                objective_scores_by_val_id=objective_scores_dict,
            )

        # Notify optimization start
        notify_callbacks(
            self.callbacks,
            "on_optimization_start",
            OptimizationStartEvent(
                seed_candidate=self.seed_candidate,
                trainset_size=len(self.reflective_proposer.trainset),
                valset_size=len(valset),
                config={
                    "perfect_score": self.perfect_score,
                    "seed": self.seed,
                    "track_best_outputs": self.track_best_outputs,
                },
            ),
        )

        # Evaluate seed candidate on valset
        seed_valset_evaluation = valset_evaluator(self.seed_candidate)

        # Initialize state
        state = initialize_gepa_state(
            run_dir=self.run_dir,
            logger=self.logger,
            seed_candidate=self.seed_candidate,
            seed_valset_evaluation=seed_valset_evaluation,
            track_best_outputs=self.track_best_outputs,
            frontier_type=self.frontier_type,
            evaluation_cache=self._initial_evaluation_cache,
        )

        # Log run config
        self.experiment_tracker.log_config(
            {
                "seed": self.seed,
                "perfect_score": self.perfect_score,
                "frontier_type": self.frontier_type,
                "track_best_outputs": self.track_best_outputs,
                "use_cloudpickle": self.use_cloudpickle,
                "raise_on_exception": self.raise_on_exception,
                "trainset_size": len(self.reflective_proposer.trainset),
                "valset_size": len(valset),
                "seed_candidate_components": sorted(self.seed_candidate.keys()),
                "val_evaluation_policy": type(self.val_evaluation_policy).__name__,
                "has_merge_proposer": self.merge_proposer is not None,
                "iteration_strategy": type(self.iteration_strategy).__name__,
                "acceptance_criterion": type(self.acceptance_criterion).__name__,
                "run_dir": self.run_dir,
            }
        )

        # Log base program score
        base_val_avg, base_val_coverage = state.get_program_average_val_subset(0)
        pareto_scores = list(state.pareto_front_valset.values())
        base_pareto_avg = (
            sum(pareto_scores) / len(pareto_scores) if pareto_scores else base_val_avg
        )
        self.experiment_tracker.log_metrics(
            {
                "val_program_average": base_val_avg,
                "best_score_on_valset": base_val_avg,
                "val_evaluated_count_new_program": base_val_coverage,
                "val_total_count": len(valset),
                "total_metric_calls": state.total_num_evals,
                "valset_pareto_front_agg": base_pareto_avg,
                "new_program_idx": 0,
                "linear_pareto_front_program_idx": 0,
                "best_program_as_per_agg_score_valset": 0,
            },
            step=state.i + 1,
        )

        self.logger.log(
            f"Iteration {state.i + 1}: Base program full valset score: {base_val_avg} "
            f"over {base_val_coverage} / {len(valset)} examples"
        )

        # Notify seed valset eval
        seed_scores = state.prog_candidate_val_subscores[0]
        notify_callbacks(
            self.callbacks,
            "on_valset_evaluated",
            ValsetEvaluatedEvent(
                iteration=0,
                candidate_idx=0,
                candidate=self.seed_candidate,
                scores_by_val_id=dict(seed_scores),
                average_score=base_val_avg,
                num_examples_evaluated=len(seed_scores),
                total_valset_size=len(valset),
                parent_ids=[],
                is_best_program=True,
                outputs_by_val_id=None,
            ),
        )

        # Register budget hook
        def budget_hook(new_total: int, delta: int) -> None:
            notify_callbacks(
                self.callbacks,
                "on_budget_updated",
                BudgetUpdatedEvent(
                    iteration=state.i + 1,
                    metric_calls_used=new_total,
                    metric_calls_delta=delta,
                    metric_calls_remaining=self._get_remaining_budget(state),
                ),
            )

        state.add_budget_hook(budget_hook)

        # ===== Main loop (iteration_strategy-driven) =====
        while not self._should_stop(state):
            if not state.is_consistent():
                raise RuntimeError("GEPAState invariants violated mid-run")
            proposal_accepted = False
            iteration_started = False
            try:
                self._sync_adapter_state_to_state(state)
                state.save(self.run_dir, use_cloudpickle=self.use_cloudpickle)
                notify_callbacks(
                    self.callbacks,
                    "on_state_saved",
                    StateSavedEvent(iteration=state.i + 1, run_dir=self.run_dir),
                )

                state.i += 1
                state.full_program_trace.append({"i": state.i})

                notify_callbacks(
                    self.callbacks,
                    "on_iteration_start",
                    IterationStartEvent(
                        iteration=state.i + 1,
                        state=state,
                    ),
                )
                iteration_started = True

                # --- Iterate through proposers from the strategy ---
                proposers = self.iteration_strategy.get_proposers(state)
                for proposer in proposers:
                    proposal = proposer.propose(state)
                    if proposal is None:
                        self.logger.log(
                            f"Iteration {state.i + 1}: Proposer "
                            f"{type(proposer).__name__} did not propose a new candidate"
                        )
                        continue

                    is_merge = proposal.tag == "merge"
                    old_sum = sum(proposal.subsample_scores_before or [])
                    new_sum = sum(proposal.subsample_scores_after or [])

                    if is_merge:
                        # Merge acceptance: new >= max(parents)
                        parent_sums = proposal.subsample_scores_before or [
                            float("-inf"),
                            float("-inf"),
                        ]

                        notify_callbacks(
                            self.callbacks,
                            "on_merge_attempted",
                            MergeAttemptedEvent(
                                iteration=state.i + 1,
                                parent_ids=proposal.parent_program_ids,
                                merged_candidate=proposal.candidate,
                            ),
                        )

                        if new_sum >= max(parent_sums):
                            new_idx, _ = self._run_full_eval_and_add(
                                new_program=proposal.candidate,
                                state=state,
                                parent_program_idx=proposal.parent_program_ids,
                            )
                            proposal_accepted = True
                            self.iteration_strategy.on_proposal_accepted(
                                proposer, proposal, state
                            )
                            notify_callbacks(
                                self.callbacks,
                                "on_merge_accepted",
                                MergeAcceptedEvent(
                                    iteration=state.i + 1,
                                    new_candidate_idx=new_idx,
                                    parent_ids=proposal.parent_program_ids,
                                ),
                            )
                            notify_callbacks(
                                self.callbacks,
                                "on_candidate_accepted",
                                CandidateAcceptedEvent(
                                    iteration=state.i + 1,
                                    new_candidate_idx=new_idx,
                                    new_score=new_sum,
                                    parent_ids=proposal.parent_program_ids,
                                ),
                            )
                            break  # stop after first accepted proposal
                        else:
                            self.iteration_strategy.on_proposal_rejected(
                                proposer, proposal, state
                            )
                            self.logger.log(
                                f"Iteration {state.i + 1}: New program subsample "
                                f"score {new_sum} is worse than both parents "
                                f"{parent_sums}, skipping merge"
                            )
                            notify_callbacks(
                                self.callbacks,
                                "on_merge_rejected",
                                MergeRejectedEvent(
                                    iteration=state.i + 1,
                                    parent_ids=proposal.parent_program_ids,
                                    reason=(
                                        f"Merged score {new_sum} worse than "
                                        f"both parents {parent_sums}"
                                    ),
                                ),
                            )
                            break  # merge rejected — end iteration

                    else:
                        # Reflective acceptance: delegate to criterion
                        if not self.acceptance_criterion.should_accept(proposal, state):
                            self.iteration_strategy.on_proposal_rejected(
                                proposer, proposal, state
                            )
                            self.logger.log(
                                f"Iteration {state.i + 1}: Candidate rejected by "
                                f"acceptance criterion (old_sum={old_sum}, "
                                f"new_sum={new_sum}), skipping"
                            )
                            notify_callbacks(
                                self.callbacks,
                                "on_candidate_rejected",
                                CandidateRejectedEvent(
                                    iteration=state.i + 1,
                                    old_score=old_sum,
                                    new_score=new_sum,
                                    reason=(
                                        f"Candidate rejected by acceptance criterion "
                                        f"(old_sum={old_sum}, new_sum={new_sum})"
                                    ),
                                ),
                            )
                            continue  # try next proposer in the list

                        self.logger.log(
                            f"Iteration {state.i + 1}: Candidate accepted "
                            f"(old_sum={old_sum}, new_sum={new_sum}). "
                            f"Continue to full eval."
                        )

                        new_idx, _ = self._run_full_eval_and_add(
                            new_program=proposal.candidate,
                            state=state,
                            parent_program_idx=proposal.parent_program_ids,
                        )
                        proposal_accepted = True
                        self.iteration_strategy.on_proposal_accepted(
                            proposer, proposal, state
                        )
                        notify_callbacks(
                            self.callbacks,
                            "on_candidate_accepted",
                            CandidateAcceptedEvent(
                                iteration=state.i + 1,
                                new_candidate_idx=new_idx,
                                new_score=new_sum,
                                parent_ids=proposal.parent_program_ids,
                            ),
                        )
                        break  # stop after first accepted proposal

            except Exception as e:
                self.logger.log(
                    f"Iteration {state.i + 1}: Exception during optimization: {e}"
                )
                self.logger.log(traceback.format_exc())
                notify_callbacks(
                    self.callbacks,
                    "on_error",
                    ErrorEvent(
                        iteration=state.i + 1,
                        exception=e,
                        will_continue=not self.raise_on_exception,
                    ),
                )
                if self.raise_on_exception:
                    raise e
                else:
                    continue
            finally:
                if iteration_started:
                    notify_callbacks(
                        self.callbacks,
                        "on_iteration_end",
                        IterationEndEvent(
                            iteration=state.i + 1,
                            state=state,
                            proposal_accepted=proposal_accepted,
                        ),
                    )

        self._sync_adapter_state_to_state(state)
        state.save(self.run_dir, use_cloudpickle=self.use_cloudpickle)

        # Notify optimization end
        best_candidate_idx = self.val_evaluation_policy.get_best_program(state)
        notify_callbacks(
            self.callbacks,
            "on_optimization_end",
            OptimizationEndEvent(
                best_candidate_idx=best_candidate_idx,
                total_iterations=state.i,
                total_metric_calls=state.total_num_evals,
                final_state=state,
            ),
        )

        # Log final summary
        best_candidate = state.program_candidates[best_candidate_idx]
        best_score = self.val_evaluation_policy.get_valset_score(
            best_candidate_idx, state
        )
        summary: dict[str, Any] = {
            "best_candidate_idx": best_candidate_idx,
            "best_valset_score": best_score,
            "total_iterations": state.i,
            "total_candidates": len(state.program_candidates),
        }
        for name in sorted(self.seed_candidate.keys()):
            summary[f"seed/{name}"] = self.seed_candidate[name]
            summary[f"best/{name}"] = best_candidate[name]
        self.experiment_tracker.log_summary(summary)

        return state


# ===========================================================================
# Monkey-patch utility for injecting SnowGEPAEngine
# ===========================================================================


@contextlib.contextmanager
def patched_engine(cls: type[GEPAEngine] | None = None) -> Iterator[None]:
    """Context manager that patches GEPAEngine for the duration of a block.

    Both ``optimize_anything.py`` and ``api.py`` import GEPAEngine as a
    local name (``from gepa.core.engine import GEPAEngine``), so patching
    only ``gepa.core.engine`` is insufficient — we must also patch the
    name in each module's namespace.

    Usage::

        with patched_engine(ParallelReflectionEngine):
            optimize_anything(...)

    Args:
        cls: The engine class to inject.  Defaults to ``SnowGEPAEngine``.

    """
    if cls is None:
        cls = SnowGEPAEngine

    import gepa.api as _api_module
    import gepa.core.engine as _engine_module
    import gepa.optimize_anything as _oa_module

    saved_engine = _engine_module.GEPAEngine
    saved_oa = getattr(_oa_module, "GEPAEngine", None)
    saved_api = getattr(_api_module, "GEPAEngine", None)
    _engine_module.GEPAEngine = cls  # type: ignore[misc]
    _oa_module.GEPAEngine = cls  # type: ignore[misc]
    _api_module.GEPAEngine = cls  # type: ignore[misc]
    try:
        yield
    finally:
        _engine_module.GEPAEngine = saved_engine  # type: ignore[misc]
        if saved_oa is not None:
            _oa_module.GEPAEngine = saved_oa  # type: ignore[misc]
        if saved_api is not None:
            _api_module.GEPAEngine = saved_api  # type: ignore[misc]


# ===========================================================================
# Public API
# ===========================================================================

__all__ = [
    "AcceptanceCriterion",
    "ImprovementOrEqualAcceptance",
    "IterationStrategy",
    "MergeThenReflectiveStrategy",
    "SnowGEPAEngine",
    "StrictImprovementAcceptance",
    "patched_engine",
]
