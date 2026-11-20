import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

PARTITIONS = ("positive", "negative", "boundary")
FIELDS = {"title": 100, "action": 240, "expected": 240}
CASE_SHAPE = {
    "type": "object",
    "properties": {
        name: {"type": "string", "minLength": 1, "maxLength": limit}
        for name, limit in FIELDS.items()
    },
    "required": list(FIELDS),
    "additionalProperties": False,
}
DRAFT_SCHEMA = {
    "type": "object",
    "properties": dict.fromkeys(PARTITIONS, CASE_SHAPE),
    "required": list(PARTITIONS),
    "additionalProperties": False,
}


class DraftError(ValueError):
    """An input or generated draft violates the project contract."""


def _unique_keys(items):
    result = {}
    for name, value in items:
        if name in result:
            raise DraftError(f"Repeated JSON key: {name}")
        result[name] = value
    return result


def read_json(data):
    try:
        return json.loads(data, object_pairs_hook=_unique_keys)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise DraftError("Expected one valid JSON document") from exc


def load_json(path: Path, limit: int = 100_000):
    with path.open("rb") as file:
        data = file.read(limit + 1)
    if len(data) > limit:
        raise DraftError(f"JSON file exceeds {limit} bytes")
    return read_json(data)


def _text(value, name: str, limit: int) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > limit
        or any(ord(char) < 32 for char in value)
    ):
        raise DraftError(f"{name} must contain 1 to {limit} characters on one line")
    return value.strip()


@dataclass(frozen=True)
class IntegerConstraint:
    field: str
    minimum: int
    maximum: int
    accepted_result: str
    rejected_result: str

    def steps(self, partition):
        if partition == "negative":
            value = self.maximum + 1
            expected = self.rejected_result
        else:
            value = (
                (self.minimum + self.maximum) // 2
                if partition == "positive"
                else self.maximum
            )
            expected = self.accepted_result
        return {"action": f"Submit {self.field} = {value}", "expected": expected}


@dataclass(frozen=True)
class Requirement:
    id: str
    statement: str
    integer_constraint: IntegerConstraint | None = None


def _integer_constraint(value):
    if not isinstance(value, dict) or set(value) != set(
        IntegerConstraint.__annotations__
    ):
        raise DraftError(
            "Integer constraint requires field, minimum, maximum and both expected results"
        )
    field = _text(value["field"], "Constraint field", 40)
    if not re.fullmatch(r"[a-z][a-z0-9_]*", field):
        raise DraftError("Constraint field must be a lowercase identifier")
    minimum, maximum = value["minimum"], value["maximum"]
    if (
        type(minimum) is not int
        or type(maximum) is not int
        or not -1_000_000 <= minimum < maximum <= 1_000_000
    ):
        raise DraftError(
            "Integer constraint needs an ascending range within ±1,000,000"
        )
    return IntegerConstraint(
        field,
        minimum,
        maximum,
        _text(value["accepted_result"], "Accepted result", FIELDS["expected"]),
        _text(value["rejected_result"], "Rejected result", FIELDS["expected"]),
    )


def requirements_from(document) -> list[Requirement]:
    if not isinstance(document, list) or not 1 <= len(document) <= 40:
        raise DraftError("Requirements must be an array of 1 to 40 records")
    seen = set()
    rows = []
    for value in document:
        if not isinstance(value, dict) or set(value) not in (
            {"id", "statement"},
            {"id", "statement", "integer_constraint"},
        ):
            raise DraftError(
                "Each requirement needs id, statement, and optionally an integer constraint"
            )
        identifier = _text(value["id"], "Requirement ID", 30)
        if not re.fullmatch(r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*", identifier):
            raise DraftError(f"Invalid requirement ID: {identifier}")
        if identifier in seen:
            raise DraftError(f"Duplicate requirement ID: {identifier}")
        seen.add(identifier)
        constraint = (
            _integer_constraint(value["integer_constraint"])
            if "integer_constraint" in value
            else None
        )
        rows.append(
            Requirement(
                identifier, _text(value["statement"], identifier, 600), constraint
            )
        )
    return rows


class Provider(Protocol):
    label: str

    def draft(self, requirement: Requirement): ...


def generate(requirements: list[Requirement], provider: Provider) -> dict:
    cases = []
    for requirement in requirements:
        draft = provider.draft(requirement)
        if not isinstance(draft, dict) or set(draft) != set(PARTITIONS):
            raise DraftError(
                f"{requirement.id}: all three test partitions are required"
            )
        titles = set()
        for partition in PARTITIONS:
            value = draft[partition]
            if not isinstance(value, dict) or set(value) != set(FIELDS):
                raise DraftError(
                    f"{requirement.id}/{partition}: unexpected case fields"
                )
            if requirement.integer_constraint:
                value = {**value, **requirement.integer_constraint.steps(partition)}
            clean = {
                field: _text(
                    value[field], f"{requirement.id}/{partition}/{field}", maximum
                )
                for field, maximum in FIELDS.items()
            }
            if clean["title"].casefold() in titles:
                raise DraftError(f"{requirement.id}: generated duplicate case titles")
            titles.add(clean["title"].casefold())
            cases.append(
                {
                    "id": f"{requirement.id}-{partition.upper()}",
                    "requirement_id": requirement.id,
                    "category": partition,
                    "status": "draft",
                    **clean,
                }
            )
    return {
        "provider": provider.label,
        "requirements": [
            {key: value for key, value in asdict(row).items() if value is not None}
            for row in requirements
        ],
        "cases": cases,
        "counts": {partition: len(requirements) for partition in PARTITIONS},
    }
