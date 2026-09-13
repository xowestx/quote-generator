import ast
import re
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


class GlassHouseConfigurationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app_source = APP_PATH.read_text(encoding="utf-8")
        cls.app_tree = ast.parse(cls.app_source)
        cls.script_source = SCRIPT_PATH.read_text(encoding="utf-8")

        selected_names = {
            "resolve_glass_house_context",
            "glass_house_tab_name",
            "google_visualization_cell",
            "parse_glass_house_option",
        }
        calculation_nodes = [
            node
            for node in cls.app_tree.body
            if (
                isinstance(node, ast.Assign)
                and any(
                    isinstance(target, ast.Name)
                    and target.id == "GLASS_HOUSE_TAB_MAP"
                    for target in node.targets
                )
            )
            or (
                isinstance(node, ast.FunctionDef)
                and node.name in selected_names
            )
        ]
        namespace = {"re": re}
        exec(
            compile(
                ast.Module(body=calculation_nodes, type_ignores=[]),
                APP_PATH,
                "exec",
            ),
            namespace,
        )
        cls.namespace = namespace

    def test_exact_six_live_sheet_mappings_exist(self):
        self.assertEqual(
            assigned_literal(self.app_tree, "GLASS_HOUSE_TAB_MAP"),
            {
                ("G", 1): "G op1",
                ("G", 2): "G op2",
                ("J-ABCD", 1): "J-A,B,C,D OP1",
                ("J-ABCD", 2): "J-A,B,C,D OP2",
                ("J-E", 1): "J-E OP1",
                ("J-E", 2): "J-E OP2",
            },
        )

    def test_fact_routing_handles_g_and_both_j_price_groups(self):
        resolve = self.namespace["resolve_glass_house_context"]
        self.assertEqual(
            resolve("OW/RV1-16A", "Townhouse Corner", "G", "G1-Design 1")
            ["Price Group"],
            "G",
        )
        self.assertEqual(
            resolve("OW/RV1-16D", "Townhouse Corner", "Townhouse G", "")
            ["Price Group"],
            "G",
        )
        self.assertEqual(
            resolve("OW/RV1-16B", "Townhouse Middle", "J", "JB-OPTION 1")
            ["Price Group"],
            "J-ABCD",
        )
        self.assertEqual(
            resolve("OW/RV1-16E", "Townhouse Corner", "Townhouse J", "")
            ["Price Group"],
            "J-E",
        )
        self.assertEqual(
            resolve(
                "OW/RV1-16E",
                "Townhouse Corner",
                "J",
                "Townhouse J Corner",
            )["Price Group"],
            "J-E",
        )

    def test_ineligible_and_conflicting_fact_rows_are_blocked(self):
        resolve = self.namespace["resolve_glass_house_context"]
        with self.assertRaisesRegex(ValueError, "townhouse"):
            resolve("OW/RV1-16A", "Apartment", "G", "GA-OPTION 1")
        with self.assertRaisesRegex(ValueError, "conflict"):
            resolve("OW/RV1-16A", "Townhouse Corner", "G", "GB-OPTION 1")
        with self.assertRaisesRegex(ValueError, "Corner"):
            resolve("OW/RV1-16B", "Townhouse Corner", "G", "GB-OPTION 1")

    def test_sheet_parser_uses_raw_values_and_validates_subtotal(self):
        rows = [
            {"c": [None, {"v": "OPTION 1"}]},
            {"c": []},
            {"c": [{"v": "No."}, {"v": "Item"}]},
            {"c": [None, {"v": "GLASS"}]},
            {
                "c": [
                    {"v": 1.1},
                    {"v": "Glass partition"},
                    {"v": "sqm"},
                    {"v": 11.21875, "f": "11"},
                    {"v": 2875, "f": "2,875"},
                    {"v": 32253.90625, "f": "32,254"},
                ]
            },
            {
                "c": [
                    None,
                    {"v": "Total"},
                    None,
                    None,
                    None,
                    {"v": 32253.90625},
                ]
            },
        ]
        parsed = self.namespace["parse_glass_house_option"](rows, "G op1")
        item = next(
            row for row in parsed["Scope Rows"] if row["Row Type"] == "item"
        )
        self.assertEqual(item["QTY"], 11.21875)
        self.assertEqual(item["Rate"], 2875)
        self.assertEqual(parsed["Subtotal"], 32253.90625)

    def test_streamlit_reads_live_raw_values_without_hardcoded_prices(self):
        self.assertIn('"tqx": "out:json"', self.app_source)
        self.assertIn('"range": "A1:F20"', self.app_source)
        self.assertIn('cells[column_index].get("v", "")', self.app_source)
        for hardcoded_rate in ("2875.0", "7187.5", "7245.0", "5134.75"):
            self.assertNotIn(hardcoded_rate, self.app_source)

    def test_glass_house_payload_and_mandatory_breakdown_are_enabled(self):
        self.assertIn('payload["requestCategory"] = "Glass House"', self.app_source)
        self.assertIn('"glass_house_detailed_scope_items"', self.app_source)
        self.assertIn('const isGlassHouse =', self.script_source)
        self.assertIn('if (isAc || isGlassHouse)', self.script_source)
        self.assertIn('const pricedBreakdown = (isAc || isGlassHouse)', self.script_source)
        self.assertIn('isGlassHouse ? "Glass House Works"', self.script_source)


if __name__ == "__main__":
    unittest.main()
