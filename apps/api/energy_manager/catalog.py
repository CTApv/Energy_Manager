from __future__ import annotations

import copy
import re
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator


DATA_TYPE_COUNTS = {
    "boolean": 1, "bit_field": 1, "int16": 1, "uint16": 1,
    "int32": 2, "uint32": 2, "float32": 2,
    "int64": 4, "uint64": 4, "float64": 4,
}
READ_FUNCTIONS = {1, 2, 3, 4}


class PointDefinition(BaseModel):
    key: str = Field(min_length=3, max_length=160)
    label: str = Field(min_length=1, max_length=160)
    function_code: int
    address: int = Field(ge=0, le=65535)
    register_count: int = Field(ge=1, le=125)
    data_type: str
    byte_order: Literal["big", "little"] = "big"
    word_order: Literal["big", "little"] = "big"
    scale: float = 1.0
    offset: float = 0.0
    unit: str = ""
    access: Literal["read"] = "read"
    polling_group: str = "normal"
    group: str = "measurements"
    enum: dict[str, str] | None = None
    bit: int | None = Field(default=None, ge=0, le=63)

    @field_validator("function_code")
    @classmethod
    def read_only_function(cls, value: int) -> int:
        if value not in READ_FUNCTIONS:
            raise ValueError("only Modbus read functions 1, 2, 3 and 4 are allowed")
        return value

    @model_validator(mode="after")
    def consistent_size(self) -> "PointDefinition":
        if self.data_type == "ascii":
            return self
        expected = DATA_TYPE_COUNTS.get(self.data_type)
        if expected is None:
            raise ValueError(f"unsupported data_type: {self.data_type}")
        if self.function_code in {1, 2} and self.data_type not in {"boolean", "bit_field"}:
            raise ValueError("coil/discrete input points must be boolean or bit_field")
        if self.function_code in {3, 4} and self.register_count != expected:
            raise ValueError(f"{self.data_type} requires {expected} register(s)")
        return self


class ProfileDefinition(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{2,99}$")
    manufacturer: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=100)
    category: str = Field(min_length=1, max_length=60)
    family: str = ""
    description: str = ""
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    protocols: list[Literal["modbus_tcp", "modbus_rtu"]]
    address_base: Literal[0, 1] = 0
    defaults: dict[str, Any] = Field(default_factory=dict)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    driver: dict[str, Any] = Field(default_factory=dict)
    documentation: dict[str, Any] = Field(default_factory=dict)
    points: list[PointDefinition] = Field(min_length=1)
    derived_points: list["DerivedPointDefinition"] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_and_non_overlapping(self) -> "ProfileDefinition":
        keys: set[str] = set()
        occupied: dict[tuple[int, int], str] = {}
        for point in self.points:
            if point.key in keys:
                raise ValueError(f"duplicate point key: {point.key}")
            keys.add(point.key)
            for address in range(point.address, point.address + point.register_count):
                slot = (point.function_code, address)
                if slot in occupied:
                    raise ValueError(f"overlap between {occupied[slot]} and {point.key} at address {address}")
                occupied[slot] = point.key
        for derived in self.derived_points:
            if derived.key in keys:
                raise ValueError(f"duplicate point key: {derived.key}")
            missing = [source for source in derived.sources if source not in keys]
            if missing:
                raise ValueError(f"derived point {derived.key} has unknown sources: {', '.join(missing)}")
            keys.add(derived.key)
        return self


class DerivedPointDefinition(BaseModel):
    key: str = Field(min_length=3, max_length=160)
    label: str = Field(min_length=1, max_length=160)
    operation: Literal["sum", "mean", "difference"]
    sources: list[str] = Field(min_length=1)
    unit: str = ""
    group: str = "derived"

    @model_validator(mode="after")
    def operation_arity(self) -> "DerivedPointDefinition":
        if self.operation == "difference" and len(self.sources) != 2:
            raise ValueError("difference requires exactly two sources")
        return self


ProfileDefinition.model_rebuild()


def parse_profile(content: str, content_type: str = "yaml") -> dict[str, Any]:
    if content_type.lower() == "json":
        import json
        raw = json.loads(content)
    else:
        raw = yaml.safe_load(content)
    if not isinstance(raw, dict):
        raise ValueError("catalog profile root must be an object")
    return raw


def validate_profile(raw: dict[str, Any]) -> tuple[ProfileDefinition | None, list[str]]:
    try:
        return ProfileDefinition.model_validate(raw), []
    except ValidationError as exc:
        errors = [f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}" for item in exc.errors()]
        return None, errors


def expand_catalog_document(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand a catalog bundle into standalone profiles without runtime inheritance."""
    if "profiles" not in raw:
        return [raw]
    point_sets = raw.get("point_sets", {})
    if not isinstance(point_sets, dict) or not isinstance(raw["profiles"], list):
        raise ValueError("invalid catalog bundle")
    expanded: list[dict[str, Any]] = []
    for source in raw["profiles"]:
        profile = copy.deepcopy(source)
        points: list[dict[str, Any]] = []
        for set_name in profile.pop("include_point_sets", []):
            if set_name not in point_sets:
                raise ValueError(f"unknown point set: {set_name}")
            points.extend(copy.deepcopy(point_sets[set_name]))
        points.extend(profile.get("points", []))
        profile["points"] = points
        expanded.append(profile)
    return expanded


def next_copy_id(profile_id: str) -> str:
    return re.sub(r"-copy(?:-\d+)?$", "", profile_id) + "-copy"
