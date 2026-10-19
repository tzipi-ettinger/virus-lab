"""Unified error format (application/problem+json).

Raise ProblemError anywhere in a request, including in a dependency, and the
client gets a Problem body with its status.

Owner: shared
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.schemas.api import Problem


class ProblemError(Exception):
    def __init__(
        self,
        status: int,
        type_: str,
        title: str,
        detail: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(title)
        self.problem = Problem(type=type_, title=title, status=status, detail=detail)
        self.headers = headers


def problem_response(problem: Problem, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(
        problem.model_dump(exclude_none=True),
        status_code=problem.status,
        media_type="application/problem+json",
        headers=headers,
    )


async def _handle(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ProblemError)
    return problem_response(exc.problem, exc.headers)


def add_problem_handler(app: FastAPI) -> None:
    app.add_exception_handler(ProblemError, _handle)
