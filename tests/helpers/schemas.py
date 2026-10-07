"""JSON Schemas describing the API contract. Used for contract (schema) tests."""

TIMESTAMP = {"type": "string", "format": "date-time"}

MEMBER = {
    "type": "object",
    "required": ["member_id", "full_name", "id_number", "date_of_birth", "email", "status", "created_at"],
    "properties": {
        "member_id": {"type": "string", "pattern": r"^M\d{5}$"},
        "full_name": {"type": "string", "minLength": 1},
        "id_number": {"type": "string", "pattern": r"^[1578]\d{6}\(\d\)$"},
        "date_of_birth": {"type": "string", "format": "date"},
        "email": {"type": "string"},
        "status": {"enum": ["active", "suspended", "closed"]},
        "created_at": TIMESTAMP,
    },
    "additionalProperties": False,
}

CONTRIBUTION = {
    "type": "object",
    "required": ["contribution_id", "member_id", "period", "contributor", "amount", "recorded_by", "recorded_at"],
    "properties": {
        "contribution_id": {"type": "string", "pattern": r"^C\d{6}$"},
        "member_id": {"type": "string"},
        "period": {"type": "string", "pattern": r"^\d{4}-(0[1-9]|1[0-2])$"},
        "contributor": {"enum": ["employee", "employer"]},
        "amount": {"type": "number", "exclusiveMinimum": 0, "maximum": 100000},
        "recorded_by": {"type": "string"},
        "recorded_at": TIMESTAMP,
    },
    "additionalProperties": False,
}

BALANCE = {
    "type": "object",
    "required": ["member_id", "employee_total", "employer_total", "withdrawn_total", "balance", "currency"],
    "properties": {
        "member_id": {"type": "string"},
        "employee_total": {"type": "number", "minimum": 0},
        "employer_total": {"type": "number", "minimum": 0},
        "withdrawn_total": {"type": "number", "minimum": 0},
        "balance": {"type": "number", "minimum": 0},
        "currency": {"const": "MOP"},
    },
    "additionalProperties": False,
}

RISK_SCORE = {
    "type": "object",
    "required": ["score", "flagged", "model_version"],
    "properties": {
        "score": {"type": "number", "minimum": 0, "maximum": 1},
        "flagged": {"type": "boolean"},
        "model_version": {"type": "string", "minLength": 1},
    },
    "additionalProperties": False,
}

AUDIT_ENTRY = {
    "type": "object",
    "required": ["seq", "timestamp", "event", "actor", "detail"],
    "properties": {
        "seq": {"type": "integer", "minimum": 1},
        "timestamp": TIMESTAMP,
        "event": {"type": "string"},
        "actor": {"type": ["string", "null"]},
        "detail": {"type": "string"},
    },
}

ERROR = {
    "type": "object",
    "required": ["detail"],
    "properties": {"detail": {"type": ["string", "array"]}},
}
