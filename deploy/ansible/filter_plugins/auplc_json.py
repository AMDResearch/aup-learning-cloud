# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.

"""Strict JSON filters used by AUP Learning Cloud Ansible roles."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeAlias

from ansible.errors import AnsibleFilterError

JSONValue: TypeAlias = None | bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"]


@dataclass(frozen=True, slots=True)
class DuplicateJsonKeyError(ValueError):
    key: str

    def __str__(self) -> str:
        return f"Duplicate JSON object key: {self.key!r}"


def _reject_duplicate_keys(pairs: list[tuple[str, JSONValue]]) -> dict[str, JSONValue]:
    result: dict[str, JSONValue] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJsonKeyError(key)
        result[key] = value
    return result


def auplc_from_json_strict(value: str) -> JSONValue:
    try:
        return json.loads(value, object_pairs_hook=_reject_duplicate_keys)
    except (TypeError, DuplicateJsonKeyError, json.JSONDecodeError):
        raise AnsibleFilterError("Invalid JSON value") from None


class FilterModule:
    def filters(self) -> dict[str, Callable[[str], JSONValue]]:
        return {"auplc_from_json_strict": auplc_from_json_strict}
