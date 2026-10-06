"""Deterministic guardrails. Nothing in this package calls an LLM.

- ``rules.evaluate``: business decisions per case and per proposed action (R1-R7).
- ``severity.classify_severity``: LOW/MEDIUM/HIGH/CRITICAL from data (spec §13).
- ``draft_policy.check_customer_draft``: content policy for customer reply drafts (R8).
"""
