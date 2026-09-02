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


class ACConfigurationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app_source = APP_PATH.read_text(encoding="utf-8")
        cls.app_tree = ast.parse(cls.app_source)
        cls.script_source = SCRIPT_PATH.read_text(encoding="utf-8")
        cls.catalog = assigned_literal(cls.app_tree, "AC_RATE_CATALOG")
        cls.ac_section = cls.app_source.split(
            'elif selected_request_type == "A.C":',
            1,
        )[1].split(
            '    else:\n'
            '        st.markdown(f"### 📝 Custom BOQ Entry Table: '
            '{selected_request_type}")',
            1,
        )[0]

        calculation_nodes = [
            node
            for node in cls.app_tree.body
            if (
                isinstance(node, ast.Assign)
                and any(
                    isinstance(target, ast.Name)
                    and target.id.startswith("AC_")
                    for target in node.targets
                )
            )
            or (
                isinstance(node, ast.FunctionDef)
                and node.name in {
                    "ac_configuration_key",
                    "ac_catalog_options",
                    "build_ac_line_items",
                    "build_ac_detailed_scope_rows",
                }
            )
        ]
        namespace = {}
        exec(
            compile(
                ast.Module(body=calculation_nodes, type_ignores=[]),
                APP_PATH,
                "exec",
            ),
            namespace,
        )
        cls.namespace = namespace

    def find_item(self, **filters):
        return next(
            item
            for item in self.catalog
            if all(item[field] == value for field, value in filters.items())
        )

    def test_catalog_contains_only_approved_models_and_34_valid_rows(self):
        self.assertEqual(len(self.catalog), 34)
        self.assertEqual(
            {item["Model"] for item in self.catalog},
            {"Carrier", "Midea", "Fresh"},
        )

    def test_representative_source_rates_are_exact(self):
        expected_rows = (
            (
                {
                    "Model": "Carrier",
                    "Type": "Inverter",
                    "Installation Type": "Split",
                    "Cooling": "Cold Only",
                    "Horse Power": 1.5,
                },
                28640.0,
            ),
            (
                {
                    "Model": "Midea",
                    "Type": "Normal",
                    "Installation Type": "Split",
                    "Cooling": "Cold Only",
                    "Horse Power": 1.5,
                },
                21900.0,
            ),
            (
                {
                    "Model": "Fresh",
                    "Type": "Normal",
                    "Installation Type": "Split",
                    "Cooling": "Cold Only",
                    "Horse Power": 1.5,
                },
                18500.0,
            ),
            (
                {
                    "Model": "Carrier",
                    "Type": "Normal",
                    "Installation Type": "Concealed",
                    "Cooling": "Hot & Cold",
                    "Horse Power": 7.5,
                },
                119610.0,
            ),
        )
        for filters, expected_cost in expected_rows:
            self.assertEqual(self.find_item(**filters)["Dry Cost"], expected_cost)

    def test_selling_rate_constants_are_exact(self):
        self.assertEqual(self.namespace["AC_DRY_COST_FACTOR"], 0.85)
        self.assertEqual(self.namespace["AC_FREON_PIPE_RATE"], 1176.4)
        self.assertEqual(self.namespace["AC_CONCEALED_DUCT_RATE"], 10588.2)
        self.assertEqual(self.namespace["AC_GRILLE_RATE"], 2353.0)

    def test_selector_hierarchy_is_in_required_order(self):
        positions = [
            self.ac_section.index(f'"{label}"')
            for label in (
                "Model",
                "Type",
                "Installation Type",
                "Cooling",
                "Horse Power",
            )
        ]
        self.assertEqual(positions, sorted(positions))

    def test_installation_ranges_are_enforced(self):
        self.assertEqual(self.namespace["AC_FREON_METERS_MIN"], 10.0)
        self.assertEqual(self.namespace["AC_FREON_METERS_MAX"], 15.0)
        self.assertEqual(self.namespace["AC_GRILLE_METERS_MIN"], 4.0)
        self.assertEqual(self.namespace["AC_GRILLE_METERS_MAX"], 6.0)
        self.assertIn("min_value=AC_FREON_METERS_MIN", self.ac_section)
        self.assertIn("max_value=AC_FREON_METERS_MAX", self.ac_section)
        self.assertIn("min_value=AC_GRILLE_METERS_MIN", self.ac_section)
        self.assertIn("max_value=AC_GRILLE_METERS_MAX", self.ac_section)

    def test_split_configuration_has_equipment_and_freon_only(self):
        configuration = {
            **self.find_item(
                Model="Midea",
                Type="Normal",
                **{
                    "Installation Type": "Split",
                    "Cooling": "Cold Only",
                    "Horse Power": 1.5,
                },
            ),
            "Room": "Bedroom",
            "Unit QTY": 2,
            "Freon Meters per Unit": 12.0,
            "Grille Meters per Unit": 0.0,
        }
        lines = self.namespace["build_ac_line_items"](configuration)
        self.assertEqual(
            [line["Component"] for line in lines],
            ["A.C Unit", "Freon Piping"],
        )
        self.assertEqual(lines[0]["Rate"], round(21900.0 / 0.85, 2))
        self.assertEqual(lines[0]["QTY"], 2.0)
        self.assertEqual(lines[1]["QTY"], 24.0)
        self.assertEqual(lines[1]["Rate"], 1176.4)

    def test_concealed_configuration_adds_duct_and_grille_once_per_unit(self):
        configuration = {
            **self.find_item(
                Model="Carrier",
                Type="Inverter",
                **{
                    "Installation Type": "Concealed",
                    "Cooling": "Hot & Cold",
                    "Horse Power": 2.25,
                },
            ),
            "Room": "Reception",
            "Unit QTY": 2,
            "Freon Meters per Unit": 15.0,
            "Grille Meters per Unit": 5.0,
        }
        lines = self.namespace["build_ac_line_items"](configuration)
        self.assertEqual(
            [line["Component"] for line in lines],
            [
                "A.C Unit",
                "Freon Piping",
                "Ductwork & Insulation",
                "A.C Grille",
            ],
        )
        self.assertEqual(lines[0]["Rate"], round(56010.0 / 0.85, 2))
        self.assertEqual(lines[1]["QTY"], 30.0)
        self.assertEqual(lines[2]["QTY"], 2.0)
        self.assertEqual(lines[2]["Rate"], 10588.2)
        self.assertEqual(lines[3]["QTY"], 10.0)
        self.assertEqual(lines[3]["Rate"], 2353.0)

    def test_duplicate_equipment_combination_is_blocked(self):
        self.assertIn('"Room / Location"', self.ac_section)
        self.assertIn('missing_room = not preview_configuration["Room"]', self.ac_section)
        self.assertIn("existing_configuration_keys", self.ac_section)
        self.assertIn(
            "selected_configuration_key in existing_configuration_keys",
            self.ac_section,
        )
        self.assertIn(
            "disabled=missing_room or duplicate_configuration",
            self.ac_section,
        )

    def test_duplicate_key_is_specific_to_room_and_equipment(self):
        base = {
            **self.find_item(
                Model="Carrier",
                Type="Inverter",
                **{
                    "Installation Type": "Split",
                    "Cooling": "Cold Only",
                    "Horse Power": 1.5,
                },
            ),
            "Room": "Master Bedroom",
        }
        same_room_spacing = {**base, "Room": "  master   bedroom "}
        different_room = {**base, "Room": "Reception"}
        key_function = self.namespace["ac_configuration_key"]
        self.assertEqual(key_function(base), key_function(same_room_spacing))
        self.assertNotEqual(key_function(base), key_function(different_room))

    def test_results_have_required_column_order(self):
        required_order = '''result_columns = [
                "No.",
                "Room",
                "Component",
                "Model",
                "Type",
                "Installation Type",
                "Cooling",
                "Horse Power",
                "Description",
                "Unit",
                "QTY",
                "Rate",
                "Total Amount",'''
        self.assertIn(required_order, self.ac_section)

    def test_detailed_scope_is_grouped_and_contains_authoritative_prices(self):
        concealed = {
            **self.find_item(
                Model="Carrier",
                Type="Inverter",
                **{
                    "Installation Type": "Concealed",
                    "Cooling": "Hot & Cold",
                    "Horse Power": 2.25,
                },
            ),
            "Room": "Master Bedroom",
            "Unit QTY": 2,
            "Freon Meters per Unit": 12.0,
            "Grille Meters per Unit": 5.0,
        }
        split = {
            **self.find_item(
                Model="Midea",
                Type="Normal",
                **{
                    "Installation Type": "Split",
                    "Cooling": "Cold Only",
                    "Horse Power": 1.5,
                },
            ),
            "Room": "Bedroom",
            "Unit QTY": 1,
            "Freon Meters per Unit": 10.0,
            "Grille Meters per Unit": 0.0,
        }
        rows = self.namespace["build_ac_detailed_scope_rows"](
            [concealed, split]
        )
        sections = [
            row["Item"] for row in rows if row["Row Type"] == "section"
        ]
        self.assertEqual(
            sections,
            [
                "HVAC WORKS",
                "Refrigerant Pipes",
                "A.C Units",
                "Ductwork & Accessories",
            ],
        )
        refrigerant_row = next(row for row in rows if row["No."] == "1.1")
        grille_row = next(row for row in rows if row["No."] == "3.1")
        self.assertEqual(refrigerant_row["QTY"], 34.0)
        self.assertEqual(grille_row["QTY"], 10.0)
        self.assertEqual(refrigerant_row["Rate"], 1176.4)
        self.assertEqual(grille_row["Rate"], 2353.0)
        item_total = sum(
            float(row["Total (EGP)"])
            for row in rows
            if row["Row Type"] == "item"
        )
        self.assertEqual(rows[-1]["Total (EGP)"], item_total)
        self.assertIn("Master Bedroom", rows[4]["Item"])

    def test_commercial_quotation_is_one_lump_sum_line(self):
        self.assertIn(
            '"Required fees for supplying and installing A.C works "',
            self.ac_section,
        )
        self.assertIn('"Unit": "LS"', self.ac_section)
        self.assertIn('"QTY": 1.0', self.ac_section)
        self.assertIn('"Rate": ac_subtotal', self.ac_section)
        self.assertIn('"Total Amount": ac_subtotal', self.ac_section)

    def test_ac_uses_shared_standard_export(self):
        self.assertLess(
            self.app_source.index('elif selected_request_type == "A.C":'),
            self.app_source.index(
                '    else:\n'
                '        st.markdown(f"### 📝 Custom BOQ Entry Table: '
                '{selected_request_type}")'
            ),
        )
        self.assertIn('"action": "standard"', self.app_source)
        self.assertIn('"Lookup Name": "A.C"', self.app_source)
        self.assertIn('payload["requestCategory"] = "A.C"', self.app_source)
        self.assertIn('payload["detailedScopeItems"]', self.app_source)
        self.assertIn('payload["priceAttachedDetailedScope"]', self.app_source)

    def test_attached_scope_pricing_checkbox_defaults_to_unchecked(self):
        checkbox_start = self.ac_section.index(
            '"Include prices in the detailed scope attached to the quotation"'
        )
        checkbox_block = self.ac_section[checkbox_start:checkbox_start + 500]
        self.assertIn("value=False", checkbox_block)
        self.assertIn(
            "A separate priced breakdown (Google Doc and PDF) will always be",
            self.ac_section,
        )

    def test_apps_script_controls_attached_prices_and_makes_breakdown_mandatory(self):
        self.assertIn("function appendAcDetailedScope(", self.script_source)
        self.assertIn("body.appendPageBreak();", self.script_source)
        self.assertIn('"Detailed Scope of Work"', self.script_source)
        self.assertIn('"Total (EGP)"', self.script_source)
        self.assertIn(
            "payload.detailedScopeItems,",
            self.script_source,
        )
        helper = self.script_source.split(
            "function appendAcDetailedScope(",
            1,
        )[1].split(
            "// ==========================================",
            1,
        )[0]
        self.assertIn(
            'includePrices ? formatAcScopeAmount(item["Rate"]) : ""',
            helper,
        )
        self.assertIn(
            'includePrices ? formatAcScopeAmount(item["Total (EGP)"]) : ""',
            helper,
        )
        self.assertIn("function createAcPricedBreakdown(", self.script_source)
        self.assertIn(
            'quotationName + " - Priced Breakdown"',
            self.script_source,
        )
        self.assertIn(
            "A.C quotation requires detailed scope items for the mandatory breakdown.",
            self.script_source,
        )
        self.assertIn(
            "const includeAttachedScopePrices = payload.priceAttachedDetailedScope === true;",
            self.script_source,
        )
        self.assertIn("const acPricedBreakdown = isAc", self.script_source)
        self.assertIn("pricedBreakdownDocUrl", self.script_source)
        self.assertIn("pricedBreakdownPdfUrl", self.script_source)


if __name__ == "__main__":
    unittest.main()
