"""Evidence route. Owner: Taleb.
Serves backend/eval/results/results.json once it exists, mock numbers before that.
"""
import json
from pathlib import Path

from fastapi import APIRouter

from backend.app import fixtures
from backend.app.schemas import EvalResults

router = APIRouter(prefix="/api", tags=["eval"])

RESULTS = Path(__file__).parent / "results" / "results.json"


@router.get("/eval", response_model=EvalResults)
def get_eval():
    if RESULTS.exists():
        return EvalResults(**json.loads(RESULTS.read_text()))
    return fixtures.EVAL
