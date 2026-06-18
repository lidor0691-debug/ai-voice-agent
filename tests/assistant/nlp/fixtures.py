"""Fake contacts for the eval suite. TEST-ONLY.

Production code must NEVER import this module. These stand in for the rows the
Stage-2 resolver would otherwise receive injected from Supabase.
"""
from __future__ import annotations

from typing import Dict, Optional

from app.assistant.nlp.contract import Contact, RecipientType

# 7 fake contacts, keyed by the Hebrew name the parser extracts.
CONTACTS: Dict[str, Contact] = {
    "דנה": Contact("דנה", RecipientType.CLIENT, phone="+972500000001"),
    "רבקה": Contact("רבקה", RecipientType.CLIENT, phone="+972500000003"),
    "אבי": Contact("אבי", RecipientType.CLIENT, phone="+972500000004"),
    "נועה": Contact("נועה", RecipientType.CLIENT, phone=None),  # no phone on file
    "יוסי": Contact("יוסי", RecipientType.TEACHER, phone="+972500000002"),
    "קבוצת בוקר": Contact("קבוצת בוקר", RecipientType.GROUP, phone=None),
    "צוות הסטודיו": Contact("צוות הסטודיו", RecipientType.GROUP, phone=None),
}


def lookup(name: Optional[str]) -> Optional[Contact]:
    """Resolve a parsed recipient name to a fake Contact (or None if unknown)."""
    if name is None:
        return None
    return CONTACTS.get(name)
