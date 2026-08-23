"""Quotation-specific Terms & Conditions parsing and generation.

The product master text is immutable. Only payment, validity, and duration clauses
are replaced in a generated quotation copy.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Dict, List, Tuple


PRE_CONSTRUCTION_START = (
    "Start and End dates shall be subject to the approved construction sequence "
    "and site readiness."
)
PRE_CONSTRUCTION_EXTENSION = (
    "The items included in this quotation shall extend the unit handover date "
    "by ({months}) Months."
)


@dataclass
class TermsDefaults:
    delivery_stage: str = "Post-Delivery"
    duration_months: int = 0
    payment_method: str = "Post-Dated Cheques"
    custom_payment_method: str = ""
    down_payment_percent: float = 100.0
    due_event: str = "Upon Approval"
    custom_due_event: str = ""
    payment_term_months: int = 1
    installment_frequency: str = "Monthly"
    offer_validity_days: int = 7

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


def _clean_number(value: float) -> str:
    value = float(value)
    return str(int(value)) if value.is_integer() else f"{value:g}"


def number_to_words(value: int) -> str:
    """Convert an integer from 1 through 365 to lowercase English words."""
    if not isinstance(value, int) or not 1 <= value <= 365:
        raise ValueError("Offer validity must be a whole number from 1 to 365.")

    ones = [
        "zero", "one", "two", "three", "four", "five", "six", "seven",
        "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen",
        "fifteen", "sixteen", "seventeen", "eighteen", "nineteen",
    ]
    tens = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]

    def under_hundred(number: int) -> str:
        if number < 20:
            return ones[number]
        return tens[number // 10] + (f"-{ones[number % 10]}" if number % 10 else "")

    if value < 100:
        return under_hundred(value)
    return (
        f"{ones[value // 100]} hundred"
        + (f" {under_hundred(value % 100)}" if value % 100 else "")
    )


def parse_terms_defaults(default_terms: str) -> Tuple[TermsDefaults, List[str]]:
    """Extract editable defaults and return warnings for low-confidence fields."""
    text = default_terms or ""
    defaults = TermsDefaults()
    warnings: List[str] = []

    lower = text.lower()
    if "bank transfer" in lower and "post-dated cheque" not in lower:
        defaults.payment_method = "Bank Transfer"
    elif "post-dated cheque" in lower or "post dated cheque" in lower:
        defaults.payment_method = "Post-Dated Cheques"
    else:
        warnings.append("Payment method was not detected; Post-Dated Cheques was used.")

    down_match = re.search(
        r"(\d+(?:\.\d+)?)\s*%\s+down\s+payment(?:\s+to\s+be\s+paid)?\s*([^\n.]*)",
        text,
        flags=re.IGNORECASE,
    )
    if down_match:
        defaults.down_payment_percent = float(down_match.group(1))
        due_text = down_match.group(2).strip(" .")
        due_lower = due_text.lower()
        if "upon approval" in due_lower:
            defaults.due_event = "Upon Approval"
        elif "upon signing" in due_lower:
            defaults.due_event = "Upon Signing"
        elif "before start" in due_lower:
            defaults.due_event = "Before Start of Work"
        elif due_text:
            defaults.due_event = "Custom"
            defaults.custom_due_event = due_text
    else:
        warnings.append("Down payment was not detected; 100% was used.")

    installment_match = re.search(
        r"(?:\d+(?:\.\d+)?\s*%\s+)?over\s+(?:equally?\s+)?"
        r"(\d+)\s+(?:(monthly|quarterly)\s+)?instal+l?ments?",
        text,
        flags=re.IGNORECASE,
    )
    if installment_match:
        count = int(installment_match.group(1))
        detected_frequency = (installment_match.group(2) or "monthly").lower()
        defaults.installment_frequency = "Quarterly" if detected_frequency == "quarterly" else "Monthly"
        defaults.payment_term_months = count * 3 if defaults.installment_frequency == "Quarterly" else count
    elif defaults.down_payment_percent < 100:
        warnings.append("Payment term was not detected; 1 month was used.")

    validity_match = re.search(
        r"valid\s+for\s+a\s+period\s+of\s+[a-z -]+\((\d+)\)\s+days?",
        text,
        flags=re.IGNORECASE,
    )
    if validity_match:
        defaults.offer_validity_days = int(validity_match.group(1))
    else:
        warnings.append("Offer validity was not detected; 7 days was used.")

    duration_match = re.search(
        r"End\s+Date:.*?\((\d+)\)\s+calendar\s+days",
        text,
        flags=re.IGNORECASE,
    )
    if duration_match:
        days = int(duration_match.group(1))
        defaults.duration_months = max(0, round(days / 30))
    else:
        warnings.append("Construction duration was not detected; 0 months was used.")

    return defaults, warnings


def validate_terms_values(
    duration_months: int,
    down_payment_percent: float,
    payment_term_months: int,
    installment_frequency: str,
    offer_validity_days: int,
    custom_payment_method: str = "",
    payment_method: str = "Post-Dated Cheques",
    custom_due_event: str = "",
    due_event: str = "Upon Approval",
) -> List[str]:
    errors: List[str] = []
    if int(duration_months) < 0:
        errors.append("Construction duration cannot be negative.")
    if not 0 <= float(down_payment_percent) <= 100:
        errors.append("Down payment must be between 0% and 100%.")
    if int(payment_term_months) <= 0:
        errors.append("Payment term must be greater than zero.")
    if installment_frequency == "Quarterly" and int(payment_term_months) % 3:
        errors.append("Quarterly payment terms must be divisible by 3.")
    if int(offer_validity_days) <= 0:
        errors.append("Offer validity must be greater than zero.")
    if int(offer_validity_days) > 365:
        errors.append("Offer validity cannot exceed 365 days.")
    if payment_method == "Other" and not custom_payment_method.strip():
        errors.append("Enter the custom payment method.")
    if due_event == "Custom" and not custom_due_event.strip():
        errors.append("Enter the custom down-payment due event.")
    return errors


def _is_payment_header(line: str) -> bool:
    return bool(re.match(r"\s*Payment\s+Installments?\s+will\s+be", line, re.IGNORECASE))


def _is_down_payment(line: str) -> bool:
    return bool(re.search(r"\d+(?:\.\d+)?\s*%\s+down\s+payment", line, re.IGNORECASE))


def _is_installment_balance(line: str) -> bool:
    return bool(
        re.search(
            r"\d+(?:\.\d+)?\s*%\s+over\s+.*instal+l?ments?",
            line,
            re.IGNORECASE,
        )
    )


def _is_validity(line: str) -> bool:
    return line.strip().lower().startswith("validity of offer:")


def _is_start_date(line: str) -> bool:
    return line.strip().lower().startswith("start date:")


def _is_end_date(line: str) -> bool:
    return line.strip().lower().startswith("end date:")


def _replace_post_delivery_duration(line: str, duration_months: int) -> str:
    days = int(duration_months) * 30
    if re.search(r"\(\d+\)\s+calendar\s+days", line, re.IGNORECASE):
        return re.sub(
            r"\(\d+\)(\s+calendar\s+days)",
            rf"({days})\1",
            line,
            count=1,
            flags=re.IGNORECASE,
        )
    return f"End Date: The project completion date shall be ({days}) calendar days from the start date."


def generate_terms(
    default_terms: str,
    *,
    delivery_stage: str,
    duration_months: int,
    payment_method: str,
    custom_payment_method: str,
    down_payment_percent: float,
    due_event: str,
    custom_due_event: str,
    payment_term_months: int,
    installment_frequency: str,
    offer_validity_days: int,
) -> Tuple[str, Dict[str, object]]:
    """Return customized terms and calculated quotation-specific values."""
    errors = validate_terms_values(
        duration_months,
        down_payment_percent,
        payment_term_months,
        installment_frequency,
        offer_validity_days,
        custom_payment_method,
        payment_method,
        custom_due_event,
        due_event,
    )
    if errors:
        raise ValueError(" ".join(errors))

    method_text = custom_payment_method.strip() if payment_method == "Other" else payment_method
    due_text = custom_due_event.strip() if due_event == "Custom" else due_event
    method_clause = method_text.lower()
    due_clause = due_text.lower()

    remaining = round(100.0 - float(down_payment_percent), 10)
    installment_count = (
        int(payment_term_months) // 3
        if installment_frequency == "Quarterly"
        else int(payment_term_months)
    )
    frequency_clause = "quarterly" if installment_frequency == "Quarterly" else "monthly"

    payment_lines = [
        f"Payment installments will be through {method_clause} as follows:",
        f"{_clean_number(down_payment_percent)}% down payment to be paid {due_clause}.",
    ]
    if remaining > 0:
        payment_lines.append(
            f"{_clean_number(remaining)}% over {installment_count} equal "
            f"{frequency_clause} installments through {method_clause}."
        )

    validity_line = (
        "Validity of Offer: This offer is valid for a period of "
        f"{number_to_words(int(offer_validity_days))} ({int(offer_validity_days)}) "
        "days from the date of issuance."
    )

    source_lines = [line.rstrip() for line in (default_terms or "").splitlines()]
    output: List[str] = []
    payment_inserted = False
    validity_inserted = False
    duration_inserted = False

    for line in source_lines:
        if _is_payment_header(line) or _is_down_payment(line) or _is_installment_balance(line):
            if not payment_inserted:
                output.extend(payment_lines)
                payment_inserted = True
            continue

        if _is_validity(line):
            if not validity_inserted:
                output.append(validity_line)
                validity_inserted = True
            continue

        if delivery_stage == "Pre-Construction" and (_is_start_date(line) or _is_end_date(line)):
            if not duration_inserted:
                output.extend([
                    PRE_CONSTRUCTION_START,
                    PRE_CONSTRUCTION_EXTENSION.format(months=int(duration_months)),
                ])
                duration_inserted = True
            continue

        if delivery_stage == "Post-Delivery" and _is_end_date(line):
            output.append(_replace_post_delivery_duration(line, int(duration_months)))
            duration_inserted = True
            continue

        output.append(line)

    if not payment_inserted:
        output = payment_lines + output
    if not validity_inserted:
        insert_at = len(payment_lines)
        output.insert(insert_at, validity_line)
    if not duration_inserted:
        duration_lines = (
            [
                PRE_CONSTRUCTION_START,
                PRE_CONSTRUCTION_EXTENSION.format(months=int(duration_months)),
            ]
            if delivery_stage == "Pre-Construction"
            else [
                f"End Date: The project completion date shall be "
                f"({int(duration_months) * 30}) calendar days from the start date."
            ]
        )
        validity_index = next((i for i, line in enumerate(output) if _is_validity(line)), -1)
        insert_at = validity_index + 1 if validity_index >= 0 else len(output)
        output[insert_at:insert_at] = duration_lines

    final_text = "\n".join(line for line in output if line.strip())
    calculated = {
        "deliveryStage": "pre-construction" if delivery_stage == "Pre-Construction" else "post-delivery",
        "durationMonths": int(duration_months),
        "paymentMethod": payment_method,
        "customPaymentMethod": custom_payment_method.strip(),
        "downPaymentPercent": float(down_payment_percent),
        "downPaymentDueEvent": due_event,
        "customDownPaymentDueEvent": custom_due_event.strip(),
        "paymentTermMonths": int(payment_term_months),
        "installmentFrequency": installment_frequency.lower(),
        "calculatedInstallmentCount": installment_count,
        "calculatedRemainingBalancePercent": remaining,
        "offerValidityDays": int(offer_validity_days),
        "generatedTermsAndConditions": final_text,
    }
    return final_text, calculated
