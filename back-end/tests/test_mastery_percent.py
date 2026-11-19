"""TK-063: Tính mastery_percent = ROUND(correct_count / total_count × 100, 2)."""

from decimal import Decimal

import pytest

from app.services.mastery import calculate_mastery_percent
from app.services.progress_service import ProgressService
from app.utils.errors import AppError


@pytest.mark.parametrize("correct,total,expected", [
    (0, 0, Decimal("0.00")),
    (0, 5, Decimal("0.00")),
    (3, 5, Decimal("60.00")),
    (7, 10, Decimal("70.00")),
    (5, 5, Decimal("100.00")),
    (1, 3, Decimal("33.33")),
    (2, 3, Decimal("66.67")),
    (1, 6, Decimal("16.67")),
    (1, 8, Decimal("12.50")),
])
def test_calculate_mastery_percent_exact_and_rounding(correct, total, expected):
    assert calculate_mastery_percent(correct, total) == expected
    assert ProgressService.calculate_mastery(correct, total) == expected


@pytest.mark.parametrize("correct,total", [
    (-1, 5),
    (0, -1),
    (6, 5),
    (1, 0),
    (True, 5),
    (1, False),
])
def test_calculate_mastery_percent_rejects_invalid_inputs(correct, total):
    with pytest.raises(ValueError):
        calculate_mastery_percent(correct, total)
    with pytest.raises(AppError) as exc_info:
        ProgressService.calculate_mastery(correct, total)
    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "VALIDATION_ERROR"
