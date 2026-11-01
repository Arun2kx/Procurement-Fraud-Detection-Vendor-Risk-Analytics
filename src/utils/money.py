"""Money helpers. Values are Indian rupees rounded to paise."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

TWOPLACES = Decimal("0.01")


def money(value: object) -> float:
    """Round a numeric value to two decimal places using half-up rules."""
    if value is None:
        raise ValueError("Cannot round a null amount.")
    decimal_value = Decimal(str(value)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    return float(decimal_value)


def split_gst_inclusive(total: float, gst_rate: float = 0.18) -> tuple[float, float, float]:
    """Split a tax-inclusive total into taxable value, GST, and total.

    The returned taxable value and tax sum to the rounded total.
    """
    total_d = Decimal(str(total)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    rate = Decimal(str(gst_rate))
    taxable = (total_d / (Decimal("1") + rate)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    tax = (total_d - taxable).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    return float(taxable), float(tax), float(total_d)


def line_amounts(unit_price: float, quantity: int, gst_rate: float = 0.18) -> tuple[float, float, float, float]:
    """Return unit price, taxable amount, tax, and total for a single line."""
    unit = Decimal(str(unit_price)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    taxable = (unit * Decimal(quantity)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    tax = (taxable * Decimal(str(gst_rate))).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    total = (taxable + tax).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    return float(unit), float(taxable), float(tax), float(total)
