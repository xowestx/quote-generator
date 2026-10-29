"""O-PLUS quotation PDF renderer (new design, introduced with quotation 1778).

Builds the client-facing PDF from the same data the generator already
calculates: line items, VAT, generated Terms & Conditions and the payment
plan (down payment, remaining balance, number and frequency of instalments).

Pages:
  1. Quotation: header, unit/owner/date/ref, scope & pricing, totals,
     amount in words, payment plan, terms (two columns), signatures.
  2. Bank details.
  3. BOQ / detailed scope (only when detailed scope rows are supplied).
  Any extra PDFs (e.g. furniture room designs) are appended at the end.
"""

from __future__ import annotations

import io
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

# --------------------------------------------------------------------------
# Brand constants
# --------------------------------------------------------------------------
NAVY = HexColor("#0B1F51")
INK = HexColor("#2B3140")
MUTED = HexColor("#6B7385")
LABEL = HexColor("#5A6478")
RULE = HexColor("#D5DAE4")
BAND = HexColor("#EEF0F5")
SAND = HexColor("#F1EFEA")
WHITE = HexColor("#FFFFFF")

PAGE_W, PAGE_H = A4
MARGIN = 25.5
CONTENT_W = PAGE_W - 2 * MARGIN
HEADER_H = 58.0
FOOTER_Y = 22.0

BANK_DETAILS = [
    ("Account Name", "O West Services"),
    ("Bank", "Commercial International Bank (CIB)"),
    ("Account Number", "100073973637"),
    ("Currency", "EGP"),
    ("IBAN", "EG810010000700000100073973637"),
    ("SWIFT Code", "CIBEEGCX007"),
]

FOOTER_BRAND = "O West by Orascom Development"

_ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
_FONTS_READY = False

REG, MED, BOLD = "Poppins", "Poppins-Medium", "Poppins-Bold"


def _register_fonts() -> None:
    global _FONTS_READY
    if _FONTS_READY:
        return
    font_dir = os.path.join(_ASSETS, "fonts")
    pdfmetrics.registerFont(TTFont(REG, os.path.join(font_dir, "Poppins-Regular.ttf")))
    pdfmetrics.registerFont(TTFont(MED, os.path.join(font_dir, "Poppins-Medium.ttf")))
    pdfmetrics.registerFont(TTFont(BOLD, os.path.join(font_dir, "Poppins-Bold.ttf")))
    _FONTS_READY = True


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------
@dataclass
class PaymentPlan:
    down_payment_percent: float = 100.0
    due_event: str = "Upon approval"
    installment_count: int = 0
    installment_frequency: str = "monthly"
    payment_method: str = ""

    @property
    def remaining_percent(self) -> float:
        return round(100.0 - float(self.down_payment_percent), 10)


@dataclass
class QuotationData:
    unit_id: str
    client_name: str
    request_type: str
    date_text: str
    ref_no: str
    items: List[Dict[str, object]]
    terms_text: str = ""
    payment: PaymentPlan = field(default_factory=PaymentPlan)
    vat_rate: float = 0.14
    detailed_scope_items: List[Dict[str, object]] = field(default_factory=list)
    show_scope_prices: bool = True
    scope_label: str = ""
    service_label: str = ""


# --------------------------------------------------------------------------
# Formatting helpers
# --------------------------------------------------------------------------
def money(value: float) -> str:
    return f"{float(value):,.2f}"


def clean_number(value: object) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value or "")
    if number.is_integer():
        return f"{int(number):,}" if abs(number) >= 1000 else str(int(number))
    return f"{number:,.2f}".rstrip("0").rstrip(".")


def percent(value: float) -> str:
    value = float(value)
    return str(int(value)) if value.is_integer() else f"{value:g}"


_ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight",
         "Nine", "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen",
         "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy",
         "Eighty", "Ninety"]


def _int_words(n: int) -> str:
    if n == 0:
        return "Zero"
    parts = []
    for scale, name in ((1_000_000_000, "Billion"), (1_000_000, "Million"), (1_000, "Thousand")):
        if n >= scale:
            parts.append(f"{_int_words(n // scale)} {name}")
            n %= scale
    if n >= 100:
        parts.append(f"{_ONES[n // 100]} Hundred")
        n %= 100
    if n >= 20:
        parts.append(_TENS[n // 10] + (f" {_ONES[n % 10]}" if n % 10 else ""))
    elif n:
        parts.append(_ONES[n])
    return " ".join(parts)


def amount_in_words(amount: float) -> str:
    cents_total = int(round(float(amount) * 100))
    pounds, piasters = divmod(cents_total, 100)
    text = f"{_int_words(pounds)} Egyptian Pound{'s' if pounds != 1 else ''}"
    if piasters:
        text += f" and {_int_words(piasters)} Piaster{'s' if piasters != 1 else ''}"
    return text + " Only"


_HEADING_RE = re.compile(r"^(?:\d{1,2}\s*[.)\-]\s*)?([A-Z][A-Za-z0-9 &/'’()\-]{1,45}):\s*(.*)$")
_BULLET_RE = re.compile(r"^\s*(?:[-•▪●*]|\d{1,2}\s*[.)])\s+")


def parse_terms(terms_text: str) -> List[Dict[str, str]]:
    """Group generated terms lines into numbered clauses with bold headings."""
    terms: List[Dict[str, str]] = []
    for raw in (terms_text or "").splitlines():
        line = _BULLET_RE.sub("", raw.strip()).strip()
        if not line:
            continue
        previous = terms[-1] if terms else None
        heading_match = _HEADING_RE.match(line)
        continues = previous is not None and (
            previous["body"].rstrip().endswith(":")
            or re.match(r"^\d+(?:\.\d+)?\s*%", line) is not None
        )
        if continues:
            previous["body"] = f"{previous['body']} {line}".strip()
        elif line.lower().startswith("payment installments") or line.lower().startswith("payment instalments"):
            terms.append({"heading": "Payment", "body": line})
        elif heading_match and len(heading_match.group(1).split()) <= 6:
            terms.append({"heading": heading_match.group(1).strip(), "body": heading_match.group(2).strip()})
        else:
            terms.append({"heading": "", "body": line})
    return terms


# --------------------------------------------------------------------------
# Renderer
# --------------------------------------------------------------------------
class _Doc:
    def __init__(self, data: QuotationData):
        _register_fonts()
        self.data = data
        self.buffer = io.BytesIO()
        self.c = canvas.Canvas(self.buffer, pagesize=A4)
        title = f"{data.unit_id} - {data.ref_no} - {data.request_type}"
        self.c.setTitle(title)
        self.c.setAuthor("O-PLUS · O West by Orascom Development")
        self.y = 0.0
        self.footer_right = ""

    # ---- primitives ------------------------------------------------------
    def text(self, x, y, value, font=REG, size=8.4, color=INK, space=0.0, align="left"):
        c = self.c
        c.setFillColor(color)
        value = str(value)
        width = pdfmetrics.stringWidth(value, font, size) + space * max(len(value) - 1, 0)
        if align == "right":
            x -= width
        elif align == "center":
            x -= width / 2
        t = c.beginText(x, y)
        t.setFont(font, size)
        t.setCharSpace(space)
        t.textOut(value)
        c.drawText(t)
        return width

    def eyebrow(self, x, y, value, size=6.4, color=NAVY, space=1.9):
        return self.text(x, y, value.upper(), BOLD, size, color, space)

    def rule(self, y, color=RULE, width=0.6, x0=MARGIN, x1=PAGE_W - MARGIN):
        c = self.c
        c.setStrokeColor(color)
        c.setLineWidth(width)
        c.line(x0, y, x1, y)

    def rect(self, x, y, w, h, color):
        self.c.setFillColor(color)
        self.c.rect(x, y, w, h, stroke=0, fill=1)

    def wrap(self, value, font, size, width):
        return simpleSplit(str(value or ""), font, size, width) or [""]

    # ---- page furniture --------------------------------------------------
    def new_page(self, eyebrow: str, first: bool = False):
        if not first:
            self._footer()
            self.c.showPage()
        c = self.c
        self.rect(0, PAGE_H - HEADER_H, PAGE_W, HEADER_H, NAVY)
        logo = os.path.join(_ASSETS, "logos", "oplus_logo_white.png")
        brand = os.path.join(_ASSETS, "logos", "owest_orascom_white.png")
        if os.path.exists(logo):
            c.drawImage(ImageReader(logo), 28, PAGE_H - 50.5, width=33.5, height=36.1, mask="auto")
        if os.path.exists(brand):
            bw = 128.0
            c.drawImage(ImageReader(brand), PAGE_W - MARGIN - bw - 4, PAGE_H - 36.2,
                        width=bw, height=bw * 115 / 520, mask="auto")
        self.eyebrow(MARGIN, PAGE_H - 84.2, eyebrow)
        self.text(MARGIN, PAGE_H - 107.5, self.data.request_type or "Quotation", BOLD, 17.2, NAVY)
        self.rule(PAGE_H - 119.5, NAVY, 1.1)
        cols = [(MARGIN, "Unit", self.data.unit_id), (177.9, "Owner", self.data.client_name),
                (395.6, "Date", self.data.date_text), (493.5, "Ref. No.", self.data.ref_no)]
        for i, (x, label, value) in enumerate(cols):
            self.eyebrow(x, PAGE_H - 133.0, label, 5.4, LABEL, 1.5)
            limit = (cols[i + 1][0] - x - 10) if i + 1 < len(cols) else PAGE_W - MARGIN - x
            size = 9.3
            while pdfmetrics.stringWidth(str(value), REG, size) > limit and size > 6.5:
                size -= 0.2
            self.text(x, PAGE_H - 147.5, value, REG, size, INK)
        self.rule(PAGE_H - 157.5)
        self.y = PAGE_H - 157.5

    def _footer(self):
        self.rule(FOOTER_Y + 11, RULE, 0.6)
        w = self.text(MARGIN, FOOTER_Y, "O-PLUS", BOLD, 6.4, NAVY, 1.0)
        self.text(MARGIN + w + 2, FOOTER_Y, f"· {FOOTER_BRAND}", REG, 6.4, MUTED)
        if self.footer_right:
            self.text(PAGE_W - MARGIN, FOOTER_Y, self.footer_right, REG, 6.4, MUTED, align="right")

    def ensure(self, needed: float, eyebrow: str, bottom: float = 48.0) -> bool:
        if self.y - needed < bottom:
            self.new_page(eyebrow)
            return True
        return False

    # ---- page 1 ------------------------------------------------------------
    COLS = {"no": MARGIN + 4.5, "desc": 68.1, "unit": 307.6, "qty": 351.1,
            "rate": 470.0, "total": PAGE_W - MARGIN - 7}

    def _scope_header(self):
        self.y -= 9.6
        self.eyebrow(MARGIN, self.y, "Scope & Pricing · EGP")
        self.y -= 4.8
        self.rect(MARGIN, self.y - 24.4, CONTENT_W, 24.4, BAND)
        self.rule(self.y, NAVY, 1.1)
        hy = self.y - 15.0
        for key, label, align in (("no", "No.", "left"), ("desc", "Description", "left"),
                                  ("unit", "Unit", "left"), ("qty", "Qty", "left"),
                                  ("rate", "Rate", "right"), ("total", "Total Amount", "right")):
            self.eyebrow(self.COLS[key], hy, label, 5.6, NAVY, 1.6) if align == "left" else \
                self.text(self.COLS[key], hy, label.upper(), BOLD, 5.6, NAVY, 1.6, align="right")
        self.y -= 24.4

    def scope_table(self, items: Sequence[Dict[str, object]]):
        eyebrow = "O-PLUS · Extra-Works Quotation"
        self._scope_header()
        desc_w = self.COLS["unit"] - self.COLS["desc"] - 14
        size, lead = 8.4, 13.5
        for index, item in enumerate(items, start=1):
            lines = self.wrap(item.get("description", ""), REG, size, desc_w)
            row_h = len(lines) * lead + 14
            if self.ensure(row_h + 20, eyebrow):
                self._scope_header()
            top = self.y
            text_top = top - 7 - 9.6
            mid = top - row_h / 2 - 3
            for i, line in enumerate(lines):
                self.text(self.COLS["desc"], text_top - i * lead, line, REG, size)
            self.text(self.COLS["no"] + 13, mid, item.get("no", index), REG, size, align="center")
            self.text(self.COLS["unit"], mid, item.get("unit", ""), REG, size)
            self.text(self.COLS["qty"] + 4, mid, clean_number(item.get("qty", "")), REG, size)
            self.text(self.COLS["rate"], mid, money(item.get("rate", 0)), REG, size, align="right")
            self.text(self.COLS["total"], mid, money(item.get("total", 0)), REG, size, align="right")
            self.y -= row_h
            self.rule(self.y)

    def totals(self, subtotal, vat, grand):
        eyebrow = "O-PLUS · Extra-Works Quotation"
        self.ensure(110, eyebrow)
        rows = [("Subtotal", money(subtotal))]
        if self.data.vat_rate:
            rows.append((f"VAT {percent(self.data.vat_rate * 100)}%", money(vat)))
        for label, value in rows:
            self.text(self.COLS["desc"], self.y - 14.5, label, REG, 8.4)
            self.text(self.COLS["total"], self.y - 14.5, value, REG, 8.4, align="right")
            self.y -= 21.7
            self.rule(self.y)
        self.y -= 3
        self.rect(MARGIN, self.y - 28.5, CONTENT_W, 28.5, BAND)
        label = "Total incl. VAT (Egyptian Pounds)" if self.data.vat_rate else "Total (Egyptian Pounds)"
        self.text(MARGIN + 4.5, self.y - 18.6, label, BOLD, 11.3, NAVY)
        self.text(self.COLS["total"], self.y - 18.6, money(grand), BOLD, 11.3, NAVY, align="right")
        self.y -= 28.5
        self.rule(self.y)
        words = amount_in_words(grand)
        self.y -= 14.5
        w = self.eyebrow(MARGIN, self.y, "In Words", 5.6, NAVY, 1.6)
        lines = self.wrap(words, REG, 7.9, CONTENT_W - w - 8)
        for i, line in enumerate(lines):
            self.text(MARGIN + w + 6, self.y - i * 11, line, REG, 7.9)
        self.y -= (len(lines) - 1) * 11

    def payment_plan(self, grand):
        p = self.data.payment
        eyebrow = "O-PLUS · Extra-Works Quotation"
        self.ensure(105, eyebrow)
        self.y -= 11
        box_h = 72.5
        top = self.y
        self.rect(MARGIN, top - box_h, CONTENT_W, box_h, SAND)
        self.eyebrow(MARGIN + 9, top - 15.6, "Payment Plan", 6.0)
        col_w = (CONTENT_W - 18) / 3
        xs = [MARGIN + 18, MARGIN + 18 + col_w + 4, MARGIN + 18 + 2 * col_w + 8]
        line_top, line_bot = top - 23, top - box_h + 9
        self.c.setStrokeColor(NAVY)
        self.c.setLineWidth(2.2)
        self.c.line(MARGIN + 10.6, line_top, MARGIN + 10.6, line_bot)
        self.c.setStrokeColor(HexColor("#C9CBD0"))
        self.c.setLineWidth(0.7)
        for x in xs[1:]:
            self.c.line(x - 10, line_top, x - 10, line_bot)

        down_amount = grand * float(p.down_payment_percent) / 100.0
        remaining = p.remaining_percent
        balance_amount = grand - down_amount if remaining > 0 else 0.0
        count = int(p.installment_count or 0)
        freq = (p.installment_frequency or "monthly").lower()

        cells = []
        cells.append((f"Payment · {percent(p.down_payment_percent)}%", money(down_amount), True,
                      (p.due_event or "Upon approval").strip().capitalize()))
        if remaining > 0 and count > 0:
            per = balance_amount / count
            cells.append((f"Balance · {percent(remaining)}%", money(balance_amount), True,
                          f"{count} {freq} instalment{'s' if count != 1 else ''} of {money(per)} EGP"))
        elif remaining > 0:
            cells.append((f"Balance · {percent(remaining)}%", money(balance_amount), True, "As per terms"))
        else:
            cells.append(("Balance", "—", False, "No instalments"))
        service = self.data.service_label or self.data.request_type
        cells.append(("Service", service, False,
                      "As per attached BOQ" if self.data.detailed_scope_items else "As per quotation"))

        for x, (label, value, is_amount, sub) in zip(xs, cells):
            self.eyebrow(x, top - 29.7, label, 5.4, LABEL, 1.5)
            limit = col_w - 16
            size = 13.6
            unit_w = pdfmetrics.stringWidth(" EGP", REG, 5.9) if is_amount else 0
            while pdfmetrics.stringWidth(value, BOLD, size) + unit_w > limit and size > 8:
                size -= 0.3
            vw = self.text(x, top - 47.8, value, BOLD, size, NAVY)
            if is_amount:
                self.text(x + vw + 3, top - 47.8, "EGP", REG, 5.9, MUTED)
            sub_size = 7.3
            while pdfmetrics.stringWidth(sub, REG, sub_size) > limit and sub_size > 5.6:
                sub_size -= 0.2
            self.text(x, top - 61.9, sub, REG, sub_size, MUTED)
        self.y = top - box_h

    def _term_blocks(self, terms, size, col_w):
        blocks = []
        for i, term in enumerate(terms, start=1):
            head = f"{term['heading']}: " if term["heading"] else ""
            # Lay out heading (bold) + body (regular) as one wrapped paragraph.
            words = [(w, BOLD) for w in head.split(" ") if w] + \
                    [(w, REG) for w in term["body"].split(" ") if w]
            lines, current, current_w = [], [], 0.0
            space_w = pdfmetrics.stringWidth(" ", REG, size)
            for word, font in words:
                ww = pdfmetrics.stringWidth(word, font, size)
                add = ww if not current else ww + space_w
                if current and current_w + add > col_w:
                    lines.append(current)
                    current, current_w = [(word, font)], ww
                else:
                    current.append((word, font))
                    current_w += add
            if current:
                lines.append(current)
            blocks.append((f"{i:02d}", lines))
        return blocks

    def _draw_term_column(self, blocks, x, top, size, lead, gap):
        y = top
        for number, lines in blocks:
            self.text(x, y, number, BOLD, size, NAVY)
            for line in lines:
                cx = x + 16.5
                for j, (word, font) in enumerate(line):
                    color = NAVY if font == BOLD else INK
                    cx += self.text(cx, y, word, font, size, color) + pdfmetrics.stringWidth(" ", REG, size)
                y -= lead
            y -= gap
        return y

    def terms_and_signatures(self):
        terms = parse_terms(self.data.terms_text)
        eyebrow = "O-PLUS · Extra-Works Quotation"
        sig_h = 62.0
        col_gap = 22.0
        col_w = (CONTENT_W - col_gap) / 2 - 16.5

        def layout(size):
            lead, gap = size * 1.42, size * 1.2
            blocks = self._term_blocks(terms, size, col_w)
            heights = [len(lines) * lead + gap for _, lines in blocks]
            total = sum(heights)
            split, acc = len(blocks), 0.0
            for i, h in enumerate(heights):
                if acc + h / 2 > total / 2:
                    split = i
                    break
                acc += h
            left, right = blocks[:split], blocks[split:]
            h = max(sum(heights[:split]), sum(heights[split:]))
            return lead, gap, left, right, h

        if terms:
            self.y -= 15.5
            available = self.y - 14 - (FOOTER_Y + 20 + sig_h)
            chosen = None
            for size in (5.8, 5.6, 5.4, 5.2, 5.0):
                lead, gap, left, right, h = layout(size)
                if h <= available:
                    chosen = (size, lead, gap, left, right, h)
                    break
            if chosen is None:
                self.new_page(eyebrow)
                self.y -= 15.5
                size = 6.2
                while True:
                    lead, gap, left, right, h = layout(size)
                    if h <= self.y - 14 - (FOOTER_Y + 20 + sig_h) or size <= 5.0:
                        break
                    size -= 0.2
                chosen = (size, lead, gap, left, right, h)
            size, lead, gap, left, right, h = chosen
            self.eyebrow(MARGIN, self.y, "Terms & Conditions", 6.0)
            top = self.y - 14
            self._draw_term_column(left, MARGIN, top, size, lead, gap)
            self._draw_term_column(right, MARGIN + (CONTENT_W + col_gap) / 2, top, size, lead, gap)
            self.y = top - h

        # signatures pinned to the bottom of the page
        sig_top = FOOTER_Y + 20 + sig_h - 8
        if self.y < sig_top + 10:
            self.new_page(eyebrow)
        half = (CONTENT_W - 16) / 2
        for x, label, sub in ((MARGIN, "O-PLUS Manager", "Name & signature"),
                              (MARGIN + half + 16 + 20, "Client Signature", "Name & signature · Date")):
            width = half if x == MARGIN else CONTENT_W - (x - MARGIN)
            self.eyebrow(x, sig_top, label, 6.0)
            self.rule(sig_top - 21.5, NAVY, 1.1, x, x + width)
            self.text(x, sig_top - 33.5, sub, REG, 7.0, MUTED)

    # ---- page 2: bank details -------------------------------------------
    def bank_page(self):
        self.new_page("O-PLUS · Bank Details")
        self.footer_right = f"Attachment to quotation {self.data.ref_no}"
        self.y -= 15.5
        self.eyebrow(MARGIN, self.y, "Bank Transfer Details · EGP", 6.0)
        self.y -= 6.5
        self.rule(self.y, NAVY, 1.1)
        for label, value in BANK_DETAILS:
            self.text(MARGIN + 11.5, self.y - 21.4, label, MED, 8.4, NAVY)
            self.text(MARGIN + 320.5, self.y - 21.4, value, REG, 8.4)
            self.y -= 34.9
            self.rule(self.y)
        note = ("Transfer fees are borne by the client. Kindly send a copy of the transfer "
                f"confirmation to our office, quoting the unit and quotation number {self.data.ref_no}.")
        self.y -= 16
        for i, line in enumerate(self.wrap(note, REG, 7.9, CONTENT_W)):
            self.text(MARGIN, self.y - i * 12.2, line, REG, 7.9, MUTED)

    # ---- page 3: BOQ / detailed scope -----------------------------------
    def boq_pages(self):
        rows = self.data.detailed_scope_items
        if not rows:
            return
        eyebrow = "O-PLUS · Bill of Quantities"
        prices = self.data.show_scope_prices
        cols = {"no": MARGIN + 6, "item": MARGIN + 40, "unit": 355.0, "qty": 400.0,
                "rate": 482.0, "total": PAGE_W - MARGIN - 7}

        def header():
            self.y -= 15.5
            label = f"Detailed Scope of Work · {self.data.scope_label}" if self.data.scope_label else "Detailed Scope of Work"
            self.eyebrow(MARGIN, self.y, label, 6.0)
            self.y -= 4.8
            self.rect(MARGIN, self.y - 22, CONTENT_W, 22, BAND)
            self.rule(self.y, NAVY, 1.1)
            hy = self.y - 13.6
            self.eyebrow(cols["no"], hy, "No.", 5.6, NAVY, 1.6)
            self.eyebrow(cols["item"], hy, "Item", 5.6, NAVY, 1.6)
            self.eyebrow(cols["unit"], hy, "Unit", 5.6, NAVY, 1.6)
            self.eyebrow(cols["qty"], hy, "Qty", 5.6, NAVY, 1.6)
            if prices:
                self.text(cols["rate"], hy, "RATE", BOLD, 5.6, NAVY, 1.6, align="right")
                self.text(cols["total"], hy, "TOTAL (EGP)", BOLD, 5.6, NAVY, 1.6, align="right")
            self.y -= 22

        self.new_page(eyebrow)
        self.footer_right = f"Attachment to quotation {self.data.ref_no}"
        header()
        size, lead = 7.6, 11.4
        item_w = cols["unit"] - cols["item"] - 12
        for row in rows:
            kind = str(row.get("Row Type", "item") or "item").lower()
            font = BOLD if kind in ("section", "total") else REG
            lines = self.wrap(row.get("Item", ""), font, size, item_w)
            row_h = len(lines) * lead + 9
            if self.ensure(row_h + 4, eyebrow):
                header()
            if kind in ("section", "total"):
                self.rect(MARGIN, self.y - row_h, CONTENT_W, row_h, BAND if kind == "section" else SAND)
            color = NAVY if kind in ("section", "total") else INK
            base = self.y - 4.5 - size
            self.text(cols["no"], base, row.get("No.", ""), font, size, color)
            for i, line in enumerate(lines):
                self.text(cols["item"], base - i * lead, line, font, size, color)
            self.text(cols["unit"], base, row.get("Unit", ""), font, size, color)
            self.text(cols["qty"], base, clean_number(row.get("QTY", "")), font, size, color)
            if prices:
                for key, src in (("rate", "Rate"), ("total", "Total (EGP)")):
                    value = row.get(src, "")
                    if value not in ("", None):
                        try:
                            value = money(float(value))
                        except (TypeError, ValueError):
                            value = str(value)
                        self.text(cols[key], base, value, font, size, color, align="right")
            self.y -= row_h
            self.rule(self.y)

    # ---- build -------------------------------------------------------------
    def build(self) -> bytes:
        d = self.data
        items = []
        for i, item in enumerate(d.items, start=1):
            qty = float(item.get("qty") or 0)
            rate = float(item.get("rate") or 0)
            total = item.get("total")
            items.append({
                "no": i,
                "description": item.get("description", ""),
                "unit": item.get("unit", ""),
                "qty": qty,
                "rate": rate,
                "total": float(total) if total not in (None, "") else qty * rate,
            })
        subtotal = sum(i["total"] for i in items)
        vat = subtotal * d.vat_rate
        grand = subtotal + vat

        self.footer_right = "Bank details & BOQ attached" if d.detailed_scope_items else "Bank details attached"
        self.new_page("O-PLUS · Extra-Works Quotation", first=True)
        self.scope_table(items)
        self.totals(subtotal, vat, grand)
        self.payment_plan(grand)
        self.terms_and_signatures()
        self.bank_page()
        self.boq_pages()
        self._footer()
        self.c.save()
        return self.buffer.getvalue()


def build_quotation_pdf(data: QuotationData, append_pdfs: Optional[Sequence[bytes]] = None) -> bytes:
    """Render the new-design quotation and append any extra PDFs."""
    pdf_bytes = _Doc(data).build()
    extras = [p for p in (append_pdfs or []) if p]
    if not extras:
        return pdf_bytes
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    for blob in [pdf_bytes, *extras]:
        try:
            for page in PdfReader(io.BytesIO(blob)).pages:
                writer.add_page(page)
        except Exception:
            continue
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def totals_for(items: Sequence[Dict[str, object]], vat_rate: float) -> Dict[str, float]:
    subtotal = sum(
        float(i.get("total")) if i.get("total") not in (None, "")
        else float(i.get("qty") or 0) * float(i.get("rate") or 0)
        for i in items
    )
    vat = subtotal * vat_rate
    return {"subtotal": subtotal, "vat": vat, "grand": subtotal + vat}
