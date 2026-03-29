"""
Structured synthetic test data for e-commerce micro-tasks (no external APIs).

Values are drawn from fixed, realistic pools — not unstructured random noise.
"""

from __future__ import annotations

import random

_NAMES = ("Rahul Sharma", "Priya Verma", "Amit Patel")
_CITIES = ("Hyderabad, India", "Mumbai, India", "Delhi, India")
_SEARCH_TERMS = ("shirt", "shoes", "dress", "watch")


def generate_user_profile() -> dict[str, str]:
    return {
        "name": random.choice(_NAMES),
        "email": f"user{random.randint(1000, 9999)}@gmail.com",
        "phone": f"9{random.randint(100000000, 999999999)}",
        "address": random.choice(_CITIES),
    }


def generate_search_query() -> str:
    return random.choice(_SEARCH_TERMS)


def generate_coupon() -> str:
    return "TEST123"
