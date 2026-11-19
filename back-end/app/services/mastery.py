"""TK-063: Tính mức thành thạo mastery_percent = ROUND(correct_count / total_count × 100, 2)."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

ZERO_MASTERY = Decimal("0.00")
ONE_HUNDRED = Decimal("100")
TWO_DECIMALS = Decimal("0.01")


def calculate_mastery_percent(correct_count: int, total_count: int) -> Decimal:
    """Tính mastery_percent trong [0.00, 100.00], làm tròn 2 chữ số thập phân; total_count=0 trả 0.00."""
    if (
        not isinstance(correct_count, int) or isinstance(correct_count, bool)
        or not isinstance(total_count, int) or isinstance(total_count, bool)
    ):
        raise ValueError("correct_count và total_count phải là số nguyên.")
    if correct_count < 0 or total_count < 0:
        raise ValueError("correct_count và total_count không được âm.")
    if correct_count > total_count:
        raise ValueError("correct_count không được lớn hơn total_count.")
    if total_count == 0:
        return ZERO_MASTERY
    return (Decimal(correct_count) * ONE_HUNDRED / Decimal(total_count)).quantize(
        TWO_DECIMALS, rounding=ROUND_HALF_UP,
    )
