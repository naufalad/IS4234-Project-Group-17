"""Project-local drag-and-drop component for case assignment."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit.components.v1 as components

_FRONTEND_DIR = Path(__file__).resolve().parent / "case_board_frontend"
_case_board = components.declare_component(
    "case_assignment_board",
    path=str(_FRONTEND_DIR),
)


def case_assignment_board(
    *,
    unassigned: list[dict[str, Any]],
    officers: list[dict[str, Any]],
    assignments: list[dict[str, Any]],
    key: str,
) -> dict[str, str] | None:
    """Render the assignment board and return the latest completed drop."""
    return _case_board(
        unassigned=unassigned,
        officers=officers,
        assignments=assignments,
        default=None,
        key=key,
    )
