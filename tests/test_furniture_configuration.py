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
        cls.furniture_section = cls.app_source.split(
            'elif selected_request_type == "Furniture":',
            1,
        )[1].split(
            'elif selected_request_type == "Closing Double Height":',
            1,
        )[0]

    def test_existing_furniture_rates_are_unchanged(self):
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

    def test_existing_optional_addon_prices_are_unchanged(self):
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
            self.assertIn(exact_price, self.furniture_section)

    def test_room_options_use_checkbox_quantity_table(self):
        for required_text in (
            '"Add": False',
            '"Furniture Option"',
            '"QTY"',
            '"Rate (EGP)"',
            "CheckboxColumn",
            "Add Selected Items to Quotation",
        ):
            self.assertIn(required_text, self.furniture_section)
        self.assertNotIn("Select Furniture Package", self.furniture_section)
        self.assertNotIn("Populate Package", self.furniture_section)

    def test_typology_filters_applicable_rooms(self):
        for required_room in (
            '"RECEPTION"',
            '"DINING ROOM"',
            '"MASTER BEDROOM"',
            '"KIDS BEDROOM"',
            '"NANNY\'S ROOM"',
            '"LIVING ROOM"',
            '"TERRACE"',
            '"OUTDOORS"',
        ):
            self.assertIn(required_room, self.furniture_section)
        self.assertIn('if num_beds > 1:', self.furniture_section)
        self.assertIn('if "+N" in fur_unit_type:', self.furniture_section)
        self.assertIn('if "+F" in fur_unit_type:', self.furniture_section)

    def test_room_prices_are_direct_and_not_package_scaled(self):
        self.assertIn(
            'float(FURNITURE_RATES[rate_key])',
            self.furniture_section,
        )
        self.assertNotIn("* multiplier", self.furniture_section)
        self.assertNotIn("build_furniture_package", self.furniture_section)

    def test_optional_items_use_same_check_and_quantity_pattern(self):
        self.assertIn(
            "Optional Kitchen, Closets & Air Conditioning",
            self.furniture_section,
        )
        for label in (
            "KITCHEN",
            "MASTER BEDROOM CLOSETS",
            "RECEPTION AC 3 HP",
            "BEDROOM AC 1.5 HP",
        ):
            self.assertIn(label, self.furniture_section)

    def test_duplicate_pricing_keys_are_not_added_twice(self):
        self.assertIn("existing_keys", self.furniture_section)
        self.assertIn(
            'if item["Pricing Key"] in existing_keys:',
            self.furniture_section,
        )

    def test_streamlit_ignores_design_pdf_workflow(self):
        for forbidden_text in (
            '"baseKey":',
            '"Base Key":',
            "generateDocOnly",
            "roomBase64s",
            "missingRoomPdfs",
            "merge_pdf_base64",
        ):
            self.assertNotIn(forbidden_text, self.app_source)

    def test_furniture_uses_standard_deployed_apps_script_route(self):
        furniture_export = self.app_source.split(
            'if selected_request_type == "Furniture":\n'
            '                            payload["requestCategory"] = "Furniture"',
            1,
        )
        self.assertEqual(len(furniture_export), 2)
        self.assertIn('"action": "standard"', self.app_source)
        self.assertIn('payload.requestCategory || ""', self.script_source)

    def test_furniture_terms_use_generic_master_record(self):
        terms_section = self.app_source.split(
            "# --- SECTION 3B: QUOTATION-SPECIFIC TERMS & DURATION ---",
            1,
        )[1].split('st.markdown("### Quotation Terms & Duration")', 1)[0]
        self.assertNotIn(
            'selected_request_type in ["Roof Room", "Closing Double Height", "Furniture"]',
            terms_section,
        )


if __name__ == "__main__":
    unittest.main()
