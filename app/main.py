from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from app.config import get_settings
from app.directives import apply_directives
from app.errors import AppError, InternalServiceError
from app.llm.base import LLMError
from app.llm.interpreter import build_client, interpret_with_guardrails
from app.optimizer import OptimizerError, optimize_schedule
from app.replay_validator import ReplayError, calculate_totals, replay_validate
from app.schemas import OptimizeResponse, ScenarioRequest
from app.summary import build_summary


app = FastAPI(title="GridWise LLM", version="1.0.0")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=400, content={"error": {"code": "bad_request", "message": "Invalid request schema"}})


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code, "message": exc.message}})


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"error": {"code": "internal_error", "message": "Internal service error"}})


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/optimize-energy", response_model=OptimizeResponse)
def optimize_energy(request: ScenarioRequest):
    settings = get_settings()
    try:
        client = build_client(settings)
        interpretations = interpret_with_guardrails(request, client, settings.llm_max_retries)
        applied = apply_directives(request, interpretations)
        plan = optimize_schedule(request, applied)
        replay_validate(request, applied, plan)
        total_grid, total_cost, peak = calculate_totals(request, plan)
        summary = build_summary(interpretations, plan, total_grid, total_cost, peak)
        return OptimizeResponse(
            scenario_id=request.scenario_id,
            directive_interpretation=interpretations,
            hourly_plan=plan,
            total_grid_kwh=total_grid,
            total_cost_bdt=total_cost,
            peak_grid_kwh=peak,
            plan_summary=summary,
        )
    except LLMError as exc:
        raise InternalServiceError("LLM interpretation failed") from exc
    except OptimizerError as exc:
        raise InternalServiceError("Optimization failed") from exc
    except ReplayError as exc:
        raise InternalServiceError("Generated plan failed validation") from exc
