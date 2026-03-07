"""
Lead data helpers — formatting and validation before sending to external systems.
"""
from typing import Optional


def format_sms_confirmation(name: str, phone_number: str) -> str:
    """Build the Hebrew SMS confirmation message sent to the caller."""
    first_name = name.split()[0] if name else "לקוח יקר"
    return (
        f"שלום {first_name},\n"
        "תודה שפנית אלינו!\n"
        "קיבלנו את פרטיך ונציג שלנו יצור איתך קשר בהקדם.\n"
        "- צוות מאיה AI"
    )


def enrich_lead(lead_dict: dict) -> dict:
    """Add any computed/derived fields before forwarding to Make.com."""
    lead_dict["source"] = "phone_call"
    lead_dict["language"] = "he"
    return lead_dict
