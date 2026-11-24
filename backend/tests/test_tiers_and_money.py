import random
from decimal import Decimal

import pytest

from app.engine.money import D, round_money
from app.engine.tiers import Tier, tiered_cost, tiered_cost_calculator_port, validate_tiers

S3_STANDARD = [
    Tier(Decimal(0), Decimal(51200), Decimal("0.025")),
    Tier(Decimal(51200), Decimal(512000), Decimal("0.024")),
    Tier(Decimal(512000), None, Decimal("0.023")),
]


def test_decimal_has_no_float_noise():
    assert D(0.1) + D(0.2) == D("0.3")
    assert float(0.1) + float(0.2) != 0.3  # the bug we avoid


@pytest.mark.parametrize(
    "value,mode,expected",
    [
        ("1.005", "standard", "1.01"),  # HALF_UP; banker's rounding would give 1.00
        ("1.004", "standard", "1.00"),
        ("1.001", "round_up", "1.01"),
        ("1.009", "round_down", "1.00"),
    ],
)
def test_rounding_modes(value, mode, expected):
    assert round_money(Decimal(value), 2, mode) == Decimal(expected)


def test_tier_zero_quantity_costs_nothing():
    assert tiered_cost(S3_STANDARD, 0).total == 0


def test_tier_inside_first_tier():
    assert tiered_cost(S3_STANDARD, 1000).total == Decimal("25.000")


def test_tier_exactly_at_boundary():
    assert tiered_cost(S3_STANDARD, 51200).total == Decimal("1280.000")


def test_tier_spanning_two_tiers():
    # 51200 x 0.025 + 8800 x 0.024 = 1280 + 211.2
    res = tiered_cost(S3_STANDARD, 60000)
    assert res.total == Decimal("1491.200")
    assert [s.quantity for s in res.slices] == [Decimal(51200), Decimal(8800)]


def test_tier_spanning_all_three():
    res = tiered_cost(S3_STANDARD, 600000)
    assert res.total == Decimal(51200) * Decimal("0.025") + Decimal(460800) * Decimal("0.024") + Decimal(88000) * Decimal("0.023")


def test_matches_literal_port_of_calculator_loop():
    rng = random.Random(7)
    for _ in range(500):
        qty = Decimal(rng.randint(0, 2_000_000))
        assert tiered_cost(S3_STANDARD, qty).total == tiered_cost_calculator_port(S3_STANDARD, qty)


def test_negative_quantity_rejected():
    with pytest.raises(ValueError):
        tiered_cost(S3_STANDARD, -1)


def test_validation_rejects_gaps_and_closed_last_tier():
    with pytest.raises(ValueError):
        validate_tiers([Tier(Decimal(0), Decimal(10), Decimal(1)), Tier(Decimal(11), None, Decimal(1))])
    with pytest.raises(ValueError):
        validate_tiers([Tier(Decimal(0), Decimal(10), Decimal(1))])
    with pytest.raises(ValueError):
        validate_tiers([Tier(Decimal(5), None, Decimal(1))])


def test_explain_lines_read_like_the_calculator():
    lines = tiered_cost(S3_STANDARD, 60000).explain("GB")
    assert lines[0] == "51200 GB x 0.025 USD = 1280.00 USD"
    assert lines[1] == "8800 GB x 0.024 USD = 211.20 USD"
