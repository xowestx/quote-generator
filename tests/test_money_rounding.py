import ast
import unittest
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "app.py"
SCRIPT_PATH = ROOT / "apps-script" / "Code.gs"


class MoneyRoundingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app_source = APP_PATH.read_text(encoding="utf-8")
        cls.script_source = SCRIPT_PATH.read_text(encoding="utf-8")
        tree = ast.parse(cls.app_source)
        helper = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "round_egp"
        )
        namespace = {
            "Decimal": Decimal,
            "ROUND_HALF_UP": ROUND_HALF_UP,
        }
        exec(
            compile(
                ast.Module(body=[helper], type_ignores=[]),
                APP_PATH,
                "exec",
            ),
            namespace,
        )
        cls.round_egp = staticmethod(namespace["round_egp"])

    def test_python_uses_commercial_half_up_whole_egp_rounding(self):
        self.assertEqual(self.round_egp(10.49), 10)
        self.assertEqual(self.round_egp(10.50), 11)
        self.assertEqual(self.round_egp(0), 0)

    def test_apps_script_rounds_lines_vat_and_document_totals(self):
        self.assertIn("function roundEgp(value)", self.script_source)
        self.assertIn(
            "total: roundEgp((Number(item.qty) || 0) * (Number(item.rate) || 0))",
            self.script_source,
        )
        self.assertIn(
            "const vatAmount = roundEgp(subTotal * vatRate);",
            self.script_source,
        )
        self.assertIn(
            'body.replaceText("{{subtotal}}", formatWholeEgp(subTotal));',
            self.script_source,
        )
        self.assertIn(
            'body.replaceText("{{total}}", formatWholeEgp(grandTotal));',
            self.script_source,
        )
        self.assertIn(
            "Egyptian Pound & Zero Piaster",
            self.script_source,
        )

    def test_quotation_rates_and_totals_end_in_dot_zero_zero(self):
        self.assertIn(
            "minimumFractionDigits: 2",
            self.script_source,
        )
        self.assertIn("maximumFractionDigits: 2", self.script_source)
        self.assertIn("formatWholeEgp(item.rate)", self.script_source)
        self.assertIn("formatWholeEgp(item.total)", self.script_source)


if __name__ == "__main__":
    unittest.main()
