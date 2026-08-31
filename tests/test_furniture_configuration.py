import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "app.py"
SCRIPT_PATH = ROOT / "apps-script" / "Code.gs"


def assigned_literal(tree, name):
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
    raise AssertionError(f"{name} was not found")


class FurnitureConfigurationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app_source = APP_PATH.read_text(encoding="utf-8")
        cls.app_tree = ast.parse(cls.app_source)
        cls.script_source = SCRIPT_PATH.read_text(encoding="utf-8")

    def test_option_o_rates_are_unchanged(self):
        self.assertEqual(
            assigned_literal(self.app_tree, "FURNITURE_RATES"),
            {
                "RECEPTION - P1": 225193.10,
                "RECEPTION - P2": 204637.62,
                "RECEPTION - P3": 183530.38,
                "LIVING ROOM - P1": 204958.27,
                "LIVING ROOM - P2": 196108.33,
                "LIVING ROOM - P3": 193405.19,
                "DINING ROOM - P1": 201455.32,
                "DINING ROOM - P2": 245996.63,
                "MASTER BEDROOM - P1": 230736.11,
                "MASTER BEDROOM - P2": 194754.34,
                "MASTER BEDROOM - P3": 230557.03,
                "KIDS BEDROOM - P1": 199236.18,
                "KIDS BEDROOM - P2": 182723.31,
                "NANNY'S ROOM": 31914.96,
                "TERRACE - P1": 31262.77,
                "TERRACE - P2": 12829.63,
                "TERRACE - P3": 9803.42,
                "OUTDOORS - P1": 49704.38,
                "OUTDOORS - P2": 64153.21,
            },
        )

    def test_package_design_mapping_is_room_specific(self):
        mappings = assigned_literal(self.app_tree, "FURNITURE_PACKAGE_DESIGNS")
        self.assertEqual(mappings["L"]["DINING ROOM"], "DINING ROOM - P2")
        self.assertEqual(mappings["D"]["DINING ROOM"], "DINING ROOM - P1")
        self.assertEqual(mappings["R"]["DINING ROOM"], "DINING ROOM - P3")
        self.assertEqual(mappings["D"]["MASTER BEDROOM"], "MASTER BEDROOM - P3")
        self.assertEqual(mappings["R"]["MASTER BEDROOM"], "MASTER BEDROOM - P2")

    def test_existing_optional_addon_prices_are_locked(self):
        for exact_price in (
            "354350.00",
            "270050.00",
            "185750.00",
            "72800.00 * 0.7",
            "72800.00 * 0.5",
            "22500.00",
            "60694.40",
            "38772.20",
        ):
            self.assertIn(exact_price, self.app_source)

    def test_custom_option_o_has_no_package_multiplier(self):
        custom_section = self.app_source.split(
            'st.markdown("##### Option B: Custom Room / Design (Option O)")',
            1,
        )[1].split('if st.session_state.staged_items:', 1)[0]
        self.assertIn("exact_rate = FURNITURE_RATES[add_room_key]", custom_section)
        self.assertNotIn("multiplier_b", custom_section)
        self.assertNotIn("* multiplier", custom_section)

    def test_furniture_terms_use_generic_master_record(self):
        terms_section = self.app_source.split(
            "# --- SECTION 3B: QUOTATION-SPECIFIC TERMS & DURATION ---",
            1,
        )[1].split('st.markdown("### Quotation Terms & Duration")', 1)[0]
        self.assertNotIn(
            'selected_request_type in ["Roof Room", "Closing Double Height", "Furniture"]',
            terms_section,
        )

    def test_apps_script_routes_explicit_furniture_and_exact_design(self):
        self.assertIn('payload.requestCategory || ""', self.script_source)
        self.assertIn('const exactBaseKey = String(item.baseKey || "")', self.script_source)
        self.assertIn("P[123]", self.script_source)
        self.assertIn("searchName = exactBaseKey;", self.script_source)
        self.assertNotIn('.replace("DINING ROOM", "DINING")', self.script_source)
        self.assertIn("missingRoomPdfs", self.script_source)


if __name__ == "__main__":
    unittest.main()
