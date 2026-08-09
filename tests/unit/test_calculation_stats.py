"""
Unit tests for the calculation usage summary.

These exercise the aggregation rules only. Calculation.summarize takes a plain
list and touches no database, so the calculations here are built in memory and
never saved. The endpoint is covered in
tests/integration/test_calculation_stats.py and the dashboard section in
tests/e2e/test_calculation_stats_e2e.py.
"""

from datetime import datetime
from uuid import uuid4

from app.models.calculation import CALCULATION_TYPES, Calculation

USER_ID = uuid4()
CREATED_AT = datetime(2025, 1, 1, 12, 0, 0)


def make_calculation(calculation_type, inputs, created_at=CREATED_AT):
    """Build an unsaved calculation with an explicit creation time."""
    calculation = Calculation.create(calculation_type, USER_ID, inputs)
    calculation.created_at = created_at
    return calculation


# ---------------------------------------------------------------------------
# Empty history
# ---------------------------------------------------------------------------
def test_empty_history_reports_zero_totals():
    """A user who has calculated nothing gets a zeroed summary, not an error."""
    stats = Calculation.summarize([])

    assert stats["total_calculations"] == 0
    assert stats["average_operands"] == 0.0


def test_empty_history_leaves_the_optional_fields_unset():
    """With no calculations there is no most used type and no last activity."""
    stats = Calculation.summarize([])

    assert stats["most_used_type"] is None
    assert stats["last_calculation_at"] is None


def test_empty_history_still_lists_every_type():
    """The per-type breakdown keeps its shape so the UI has nothing to guess."""
    stats = Calculation.summarize([])

    assert stats["counts_by_type"] == {name: 0 for name in CALCULATION_TYPES}


# ---------------------------------------------------------------------------
# Totals and averages
# ---------------------------------------------------------------------------
def test_total_counts_every_calculation():
    """The total is the number of calculations, regardless of their type."""
    calculations = [
        make_calculation("addition", [1, 2]),
        make_calculation("division", [10, 2]),
        make_calculation("addition", [3, 4]),
    ]

    assert Calculation.summarize(calculations)["total_calculations"] == 3


def test_average_operands_is_the_mean_input_count():
    """Two inputs and four inputs average to three."""
    calculations = [
        make_calculation("addition", [1, 2]),
        make_calculation("addition", [1, 2, 3, 4]),
    ]

    assert Calculation.summarize(calculations)["average_operands"] == 3.0


def test_average_operands_is_rounded_to_two_decimals():
    """A repeating average is rounded so the report stays readable."""
    calculations = [
        make_calculation("addition", [1, 2]),
        make_calculation("addition", [1, 2]),
        make_calculation("addition", [1, 2, 3]),
    ]

    # 7 operands over 3 calculations = 2.333...
    assert Calculation.summarize(calculations)["average_operands"] == 2.33


def test_average_operands_of_a_single_calculation_is_its_input_count():
    """One calculation averages to itself."""
    calculations = [make_calculation("multiplication", [2, 3, 4])]

    assert Calculation.summarize(calculations)["average_operands"] == 3.0


# ---------------------------------------------------------------------------
# Per-type breakdown
# ---------------------------------------------------------------------------
def test_counts_by_type_tallies_each_type_separately():
    """Each calculation is counted under its own type."""
    calculations = [
        make_calculation("addition", [1, 2]),
        make_calculation("addition", [3, 4]),
        make_calculation("subtraction", [9, 1]),
    ]

    counts = Calculation.summarize(calculations)["counts_by_type"]
    assert counts["addition"] == 2
    assert counts["subtraction"] == 1


def test_counts_by_type_zero_fills_the_unused_types():
    """Types the user never picked are reported as zero rather than omitted."""
    calculations = [make_calculation("addition", [1, 2])]

    counts = Calculation.summarize(calculations)["counts_by_type"]
    assert counts["multiplication"] == 0
    assert counts["division"] == 0


def test_counts_by_type_adds_up_to_the_total():
    """The breakdown accounts for every calculation, with none double counted."""
    calculations = [
        make_calculation("addition", [1, 2]),
        make_calculation("subtraction", [9, 1]),
        make_calculation("multiplication", [2, 3]),
        make_calculation("division", [8, 2]),
    ]

    stats = Calculation.summarize(calculations)
    assert sum(stats["counts_by_type"].values()) == stats["total_calculations"]


# ---------------------------------------------------------------------------
# Most used type
# ---------------------------------------------------------------------------
def test_most_used_type_is_the_one_with_the_highest_count():
    """The clear favourite is reported."""
    calculations = [
        make_calculation("addition", [1, 2]),
        make_calculation("division", [8, 2]),
        make_calculation("division", [9, 3]),
    ]

    assert Calculation.summarize(calculations)["most_used_type"] == "division"


def test_most_used_type_breaks_ties_by_declaration_order():
    """A tie resolves the same way every time, so the report is stable."""
    calculations = [
        make_calculation("division", [8, 2]),
        make_calculation("subtraction", [9, 1]),
    ]

    # Both have one calculation; subtraction is declared before division.
    assert Calculation.summarize(calculations)["most_used_type"] == "subtraction"


# ---------------------------------------------------------------------------
# Last activity
# ---------------------------------------------------------------------------
def test_last_calculation_at_is_the_newest_creation_time():
    """The most recent calculation sets the last-activity timestamp."""
    newest = datetime(2025, 6, 1, 9, 30)
    calculations = [
        make_calculation("addition", [1, 2], created_at=datetime(2025, 1, 1)),
        make_calculation("addition", [3, 4], created_at=newest),
        make_calculation("addition", [5, 6], created_at=datetime(2025, 3, 1)),
    ]

    assert Calculation.summarize(calculations)["last_calculation_at"] == newest
