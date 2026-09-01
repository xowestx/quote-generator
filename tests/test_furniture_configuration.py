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

    def test_level_is_selected_before_method(self):
        level_position = self.furniture_section.index(
            'st.markdown("##### 1. Furniture Level")'
        )
        method_position = self.furniture_section.index(
            'st.markdown("##### 2. Selection Method")'
        )
        self.assertLess(level_position, method_position)
        self.assertIn(
            '["Luxury [L]", "Deluxe [D]", "Rent [R]"]',
            self.furniture_section,
        )
        self.assertIn(
            '["Full Package", "Select Rooms Individually"]',
            self.furniture_section,
        )

    def test_confirmed_level_multipliers_apply_to_rooms(self):
        for expected in (
            '1.0 if level_code == "L"',
            'else 0.7 if level_code == "D"',
            'else 0.35',
            '* level_multiplier',
        ):
            self.assertIn(expected, self.furniture_section)

    def test_full_package_and_individual_room_paths_exist(self):
        self.assertIn(
            'if selection_method == "Full Package":',
            self.furniture_section,
        )
        self.assertIn("Full Package Preview", self.furniture_section)
        self.assertIn("Room-by-Room Selection", self.furniture_section)
        self.assertIn("room_option_keys", self.furniture_section)

    def test_each_room_has_one_option_selector(self):
        self.assertIn(
            'selected_rate_key = st.selectbox(',
            self.furniture_section,
        )
        self.assertIn(
            "Each room has one option selector",
            self.furniture_section,
        )
        self.assertNotIn("CheckboxColumn", self.furniture_section)

    def test_duplicate_rooms_are_blocked_by_room_key(self):
        self.assertIn(
            '"Pricing Key": f"ROOM|{room_name.upper()}"',
            self.furniture_section,
        )
        self.assertIn("existing_keys", self.furniture_section)
        self.assertIn("Duplicate selection blocked", self.furniture_section)
        self.assertIn("seen_pricing_keys", self.furniture_section)

    def test_optional_section_is_separate_and_level_priced(self):
        self.assertIn(
            "Optional Kitchen, Closets & Air Conditioning",
            self.furniture_section,
        )
        for label in (
            "Kitchen",
            "Master Bedroom Closets",
            "Kids Bedroom Closets",
            "Nanny's Room Closet",
            "Reception AC 3 HP",
            "Bedroom AC 1.5 HP",
        ):
            self.assertIn(label, self.furniture_section)

    def test_results_have_required_column_order(self):
        required_order = '''result_columns = [
                "No.",
                "Level",
                "Room",
                "Option",
                "Description",
                "Unit",
                "QTY",
                "Rate",
                "Total Amount",'''
        self.assertIn(required_order, self.furniture_section)

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
