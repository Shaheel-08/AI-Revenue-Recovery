"""Simulation / Batch Evaluation API — the proof endpoint."""
from __future__ import annotations

from fastapi import APIRouter
from app.schemas.base import BatchEvaluationRequest
from app.simulation.batch_evaluator import batch_evaluator

router = APIRouter()


@router.post("/batch")
async def run_batch_evaluation(
    request: BatchEvaluationRequest = BatchEvaluationRequest(),
):
    """
    Run the batch evaluator: RecoverOS vs fixed-retry baseline.

    Returns a structured comparison report with recovery rate, net revenue,
    average attempts, message count, and duplicate-charge incidents for both.
    """
    report = batch_evaluator.run_evaluation(
        transaction_count=request.transaction_count,
        seed=request.seed,
    )
    return report
