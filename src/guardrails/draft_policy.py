"""Content policy for the LLM's customer reply draft (R8, decision D4).

The LLM writes the draft from an example template; this deterministic check runs before the draft is
stored. A violating draft is replaced by a safe fallback. The policy is deliberately conservative:
a false positive costs a blander reply, while a false negative could promise money no human approved.
"""

import re

from src.common.schemas import PolicyViolation, RuleId

_AMOUNT = r"(?:a\s+|an\s+|your\s+)?(?:full\s+|partial\s+)?"
_REFUND_PROMISES = [
    r"\b(?:we|i)(?:'ve| have)?\s+(?:already\s+)?refunded\b",
    r"\b(?:we|i)(?:'ve| have)\s+(?:processed|issued|approved|sent)\s+(?:the\s+)?" + _AMOUNT + r"refund\b",
    r"\b(?:we|i)(?:'ll| will)\s+(?:refund|reimburse)\b",
    r"\byou(?:'ll| will)\s+(?:receive|get|be\s+(?:issued|given|sent))\s+" + _AMOUNT + r"refund\b",
    r"\brefund\s+(?:has\s+been|was|is\s+being|will\s+be)\s+(?:processed|issued|approved|sent|completed|credited)\b",
    r"\brefund\s+(?:is\s+)?(?:approved|guaranteed|confirmed)\b",
]
_COMPENSATION_PROMISES = [
    r"\bcompensat\w*",
    r"\b(?:store\s+credit|voucher|coupon|discount\s+code|gift\s+card)\b",
]
_INTERNAL_DETAILS = [
    r"\bseverity\b",
    r"\b(?:low|medium|high|critical)[\s-]+priority\b",
    r"\bguardrails?\b",
    r"\b(?:TCK|APR|NTF|DRF|RFD)-\d+\b",  # internal record IDs; the customer's own order ID is fine
    r"\b(?:" + "|".join(re.escape(rule.value) for rule in RuleId) + r")\b",
]

_CHECKS: list[tuple[str, list[re.Pattern[str]]]] = [
    ("refund_promise", [re.compile(p, re.IGNORECASE) for p in _REFUND_PROMISES]),
    ("compensation_promise", [re.compile(p, re.IGNORECASE) for p in _COMPENSATION_PROMISES]),
    ("internal_detail", [re.compile(p, re.IGNORECASE) for p in _INTERNAL_DETAILS]),
]


def check_customer_draft(text: str | None) -> list[PolicyViolation]:
    """Return every policy violation in the draft; an empty list means the draft may be used."""
    if text is None or not text.strip():
        return [PolicyViolation(code="empty", detail="The draft is empty.")]
    violations: list[PolicyViolation] = []
    for code, patterns in _CHECKS:
        for pattern in patterns:
            if match := pattern.search(text):
                violations.append(PolicyViolation(code=code, detail=match.group(0)))
    return violations
