"""Test-data builders. Every call returns unique, valid data unless overridden."""
from __future__ import annotations

import itertools
from datetime import date

_counter = itertools.count(1)


def years_ago(years: int, extra_days: int = 0, today: date | None = None) -> date:
    """Date exactly `years` years before today (Feb-29 safe), shifted by extra_days."""
    from datetime import timedelta

    today = today or date.today()
    try:
        d = today.replace(year=today.year - years)
    except ValueError:  # today is 29 Feb and target year is not a leap year
        d = today.replace(year=today.year - years, day=28)
    return d + timedelta(days=extra_days)


def macao_id(n: int | None = None) -> str:
    """Synthetic ID in Macao resident format 1NNNNNN(C) — not a real person."""
    n = next(_counter) if n is None else n
    body = f"1{n:06d}"
    check = sum(int(ch) for ch in body) % 10
    return f"{body}({check})"


def member_payload(**overrides) -> dict:
    n = next(_counter)
    payload = {
        "full_name": f"Test Member {n:04d}",
        "id_number": macao_id(n),
        "date_of_birth": years_ago(35).isoformat(),
        "email": f"member{n:04d}@example.com",
    }
    payload.update(overrides)
    return payload


def current_period(today: date | None = None) -> str:
    today = today or date.today()
    return f"{today.year:04d}-{today.month:02d}"


def period_offset(months: int, today: date | None = None) -> str:
    """Period string `months` months from the current one (negative = past)."""
    today = today or date.today()
    idx = today.year * 12 + (today.month - 1) + months
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"
