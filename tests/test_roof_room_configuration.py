import unittest
from pathlib import Path

from roof_room_engine import (
    ROOF_ROOM_CONSTRUCTION_DAYS,
    ROOF_ROOM_GRACE_DAYS,
    ROOF_ROOM_MAXIMUM_CONTRACT_DAYS,
    ROOF_ROOM_MOBILIZATION_DAYS,
    roof_room_area_group,
    select_roof_room_scenarios,
)


ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")


SCENARIOS = [
    {"Category": "Roof Room", "Rate (per sqm)": 92105.26, "Options": "RR-UPTO10-S1", "Area Group": "Up to 10 m²", "Down Payment": 0.25, "Months": 6, "Approval": "No"},
    {"Category": "Roof Room", "Rate (per sqm)": 92105.26, "Options": "RR-UPTO10-S2", "Area Group": "Up to 10 m²", "Down Payment": "30%", "Months": 12, "Approval": "No"},
    {"Category": "Roof Room", "Rate (per sqm)": 105263.16, "Options": "RR-UPTO10-S3", "Area Group": "Up to 10 m²", "Down Payment": 25, "Months": 24, "Approval": "No"},
    {"Category": "Roof Room", "Rate (per sqm)": 105263.16, "Options": "RR-UPTO10-S4", "Area Group": "Up to 10 m²", "Down Payment": 0.30, "Months": 30, "Approval": "Ghandour approval"},
    {"Category": "Roof Room", "Rate (per sqm)": 92105.26, "Options": "RR-ABOVE10-S1", "Area Group": "Above 10 m²", "Down Payment": 0.25, "Months": 6, "Approval": "No"},
    {"Category": "Roof Room", "Rate (per sqm)": 92105.26, "Options": "RR-ABOVE10-S2", "Area Group": "Above 10 m²", "Down Payment": 0.30, "Months": 12, "Approval": "No"},
    {"Category": "Roof Room", "Rate (per sqm)": 105263.16, "Options": "RR-ABOVE10-S3", "Area Group": "Above 10 m²", "Down Payment": 0.30, "Months": 24, "Approval": "No"},
]


class RoofRoomConfigurationTests(unittest.TestCase):
    def test_exactly_ten_is_in_smaller_area_band(self):
        self.assertEqual(roof_room_area_group(10), "Up to 10 m²")
        self.assertEqual(roof_room_area_group(10.01), "Above 10 m²")

    def test_smaller_area_has_four_scenarios_and_approval_only_on_s4(self):
        scenarios = select_roof_room_scenarios(SCENARIOS, 10)
        self.assertEqual(len(scenarios), 4)
        self.assertEqual([row["Months"] for row in scenarios], [6, 12, 24, 30])
        self.assertEqual([row["Down Payment"] for row in scenarios], [25, 30, 25, 30])
        self.assertEqual(scenarios[-1]["Approval"], "Ghandour approval")

    def test_larger_area_has_only_three_eligible_scenarios(self):
        scenarios = select_roof_room_scenarios(SCENARIOS, 10.01)
        self.assertEqual(len(scenarios), 3)
        self.assertEqual([row["Months"] for row in scenarios], [6, 12, 24])
        self.assertTrue(all(row["Approval"] == "No" for row in scenarios))

    def test_rates_are_net_and_reconstruct_approved_vat_inclusive_prices(self):
        scenarios = select_roof_room_scenarios(SCENARIOS, 9)
        self.assertAlmostEqual(scenarios[0]["Gross Rate"], 105000.00, places=2)
        self.assertAlmostEqual(scenarios[2]["Gross Rate"], 120000.00, places=2)

    def test_fixed_contract_timeline_totals_225_days(self):
        self.assertEqual(ROOF_ROOM_MOBILIZATION_DAYS, 45)
        self.assertEqual(ROOF_ROOM_CONSTRUCTION_DAYS, 150)
        self.assertEqual(ROOF_ROOM_GRACE_DAYS, 30)
        self.assertEqual(
            ROOF_ROOM_MOBILIZATION_DAYS
            + ROOF_ROOM_CONSTRUCTION_DAYS
            + ROOF_ROOM_GRACE_DAYS,
            ROOF_ROOM_MAXIMUM_CONTRACT_DAYS,
        )

    def test_roof_room_terms_controls_are_locked_to_selected_scenario(self):
        self.assertIn('roof_room_terms_locked = selected_request_type == "Roof Room"', APP_SOURCE)
        self.assertIn('disabled=roof_room_terms_locked', APP_SOURCE)
        self.assertIn('apply_roof_room_contract_terms(', APP_SOURCE)


if __name__ == "__main__":
    unittest.main()

