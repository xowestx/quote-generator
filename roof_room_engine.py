"""Validation and selection helpers for Roof Room commercial scenarios."""

from __future__ import annotations

from typing import Iterable, Mapping, Dict, List


ROOF_ROOM_VAT_RATE = 0.14
ROOF_ROOM_MOBILIZATION_DAYS = 45
ROOF_ROOM_CONSTRUCTION_DAYS = 150
ROOF_ROOM_GRACE_DAYS = 30
ROOF_ROOM_MAXIMUM_CONTRACT_DAYS = 225


def percentage_points(value: object) -> float:
    """Return a percentage as points, accepting 25%, 0.25, or 25."""
    text = str(value or "").strip()
    if text.endswith("%"):
        return float(text[:-1].replace(",", "").strip())
    numeric = float(text.replace(",", ""))
    return numeric * 100.0 if 0 <= numeric <= 1 else numeric


def roof_room_area_group(area_sqm: float) -> str:
    """Exactly 10 sqm belongs to the smaller Roof Room price band."""
    return "Up to 10 m²" if float(area_sqm) <= 10.0 else "Above 10 m²"


def normalize_area_group(value: object) -> str:
    text = str(value or "").strip().lower().replace("²", "2")
    if "up to" in text or "below" in text:
        return "Up to 10 m²"
    if "above" in text or "over" in text:
        return "Above 10 m²"
    return ""


def select_roof_room_scenarios(
    records: Iterable[Mapping[str, object]], area_sqm: float
) -> List[Dict[str, object]]:
    """Validate and return only the commercial scenarios allowed for an area."""
    expected_group = roof_room_area_group(area_sqm)
    scenarios: List[Dict[str, object]] = []
    seen_ids = set()

    for record in records:
        if str(record.get("Category", "")).strip().upper() != "ROOF ROOM":
            continue
        if normalize_area_group(record.get("Area Group")) != expected_group:
            continue

        scenario_id = str(record.get("Options", "")).strip().upper()
        if not scenario_id or scenario_id in seen_ids:
            raise ValueError("Every eligible Roof Room scenario must have a unique Options ID.")
        seen_ids.add(scenario_id)

        rate = float(str(record.get("Rate (per sqm)", 0)).replace(",", ""))
        down_payment = percentage_points(record.get("Down Payment", 0))
        months = int(float(record.get("Months", 0)))
        approval = str(record.get("Approval", "No")).strip() or "No"

        if rate <= 0 or months <= 0 or not 0 <= down_payment <= 100:
            raise ValueError(f"Roof Room scenario {scenario_id} has invalid commercial data.")

        scenarios.append({
            "Scenario ID": scenario_id,
            "Area Group": expected_group,
            "Net Rate": rate,
            "Gross Rate": rate * (1.0 + ROOF_ROOM_VAT_RATE),
            "Down Payment": down_payment,
            "Months": months,
            "Approval": approval,
        })

    expected_count = 4 if expected_group == "Up to 10 m²" else 3
    if len(scenarios) != expected_count:
        raise ValueError(
            f"Expected {expected_count} Roof Room scenarios for {expected_group}; "
            f"found {len(scenarios)}."
        )
    return scenarios

