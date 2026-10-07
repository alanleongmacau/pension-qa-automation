"""Member registration (rules R1, R2)."""
from datetime import date, timedelta

import pytest
from jsonschema import FormatChecker, validate

from tests.helpers import schemas
from tests.helpers.data_factory import member_payload, years_ago

pytestmark = pytest.mark.api


@pytest.mark.smoke
def test_register_member_returns_201_and_matches_contract(api):
    payload = member_payload()

    resp = api.create_member(**payload)

    assert resp.status_code == 201
    body = resp.json()
    validate(body, schemas.MEMBER, format_checker=FormatChecker())
    assert {k: body[k] for k in payload} == payload
    assert body["status"] == "active"


def test_registered_member_can_be_retrieved_and_listed(api, member):
    assert api.get(f"/members/{member['member_id']}").json() == member
    assert member in api.get("/members").json()


def test_member_ids_are_unique_and_sequential(member_factory):
    ids = [member_factory()["member_id"] for _ in range(3)]

    assert len(set(ids)) == 3
    assert ids == sorted(ids)


def test_unknown_member_returns_404(api):
    resp = api.get("/members/M99999")

    assert resp.status_code == 404
    assert "M99999" in resp.json()["detail"]


def test_duplicate_id_number_is_rejected_with_409(api, member):
    resp = api.create_member(**member_payload(id_number=member["id_number"]))

    assert resp.status_code == 409


def test_full_name_is_trimmed(api):
    resp = api.create_member(**member_payload(full_name="  Chan Tai Man  "))

    assert resp.json()["full_name"] == "Chan Tai Man"


# ---------------------------------------------------------------- R1 age boundaries
@pytest.mark.parametrize(
    "dob, expected",
    [
        pytest.param(years_ago(18), 201, id="exactly-18-today"),
        pytest.param(years_ago(18, extra_days=1), 422, id="18-tomorrow"),
        pytest.param(years_ago(18, extra_days=-1), 201, id="18-yesterday"),
        pytest.param(years_ago(100), 201, id="centenarian"),
        pytest.param(date.today(), 422, id="born-today"),
        pytest.param(date.today() + timedelta(days=1), 422, id="future-dob"),
    ],
)
def test_minimum_age_boundary(api, dob, expected):
    resp = api.create_member(**member_payload(date_of_birth=dob.isoformat()))

    assert resp.status_code == expected, resp.text


# ---------------------------------------------------------------- R2 + field validation
@pytest.mark.parametrize(
    "id_number",
    ["1234567", "1234567(89)", "2234567(8)", "123456(7)", "1234567-8", "ABCDEFG(1)", "", " 1234567(8)"],
)
def test_invalid_id_number_format_is_rejected(api, id_number):
    assert api.create_member(**member_payload(id_number=id_number)).status_code == 422


@pytest.mark.parametrize("email", ["no-at-sign", "a@b", "a b@example.com", "@example.com", ""])
def test_invalid_email_is_rejected(api, email):
    assert api.create_member(**member_payload(email=email)).status_code == 422


@pytest.mark.parametrize("name", ["", "   ", "x" * 101])
def test_invalid_full_name_is_rejected(api, name):
    assert api.create_member(**member_payload(full_name=name)).status_code == 422


@pytest.mark.parametrize("missing", ["full_name", "id_number", "date_of_birth", "email"])
def test_missing_required_field_is_rejected(api, missing):
    payload = member_payload()
    del payload[missing]

    resp = api.post("/members", json=payload)

    assert resp.status_code == 422
    assert missing in resp.text


def test_rejected_registration_creates_nothing(api):
    api.create_member(**member_payload(email="bad"))

    assert api.get("/members").json() == []
