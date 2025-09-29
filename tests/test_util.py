from contextlib import nullcontext
import copy
from typing import Any

import pytest

from custom_components.smartcar.util import (
    hmac_sha256_hexdigest,
    key_path_get,
    key_path_pop,
    key_path_transpose,
    key_path_update,
)


def test_hmac_sha256_hexdigest():
    assert (
        hmac_sha256_hexdigest("secret", "text")
        == "2f443685592900e619f2f3b2350c3c8a5738e2e7a26bc9a244d3393c3cd6abd6"
    )


@pytest.mark.parametrize(
    ("obj", "key_path", "default_args", "expected_result", "expected_exception"),
    [
        (
            {"person": {"name": "Veda", "age": 22}},
            "person.age",
            [],
            22,
            None,
        ),
        (
            {"person": "Veda"},
            "person.age",
            [],
            ...,
            TypeError,
        ),
        (
            {"person": {}},
            "person.age",
            [],
            None,
            None,
        ),
        (
            {"person": {}},
            "person.age",
            [21],
            21,
            None,
        ),
        (
            {"person": None},
            "person.age",
            [],
            None,
            None,
        ),
    ],
    ids=[
        "person.age",
        "person.age:TypeError",
        "person.age:standard-default",
        "person.age:default",
        "person.age:null-value",
    ],
)
def test_key_path_get(
    obj: dict[str, Any],
    key_path: str,
    default_args: list[Any],
    expected_result: Any,
    expected_exception: type[Exception] | None,
):
    with pytest.raises(expected_exception) if expected_exception else nullcontext():
        assert key_path_get(obj, key_path, *default_args) == expected_result


@pytest.mark.parametrize(
    (
        "obj",
        "key_path",
        "default_args",
        "expected_result",
        "expected_obj",
        "expected_exception",
    ),
    [
        (
            {"person": {"name": "Veda", "age": 22}},
            "person.age",
            [],
            22,
            {"person": {"name": "Veda"}},
            None,
        ),
        (
            {"person": {"name": "Veda"}},
            "person.age",
            [],
            None,
            {"person": {"name": "Veda"}},
            KeyError,
        ),
        (
            {"person": {"name": "Veda"}},
            "person.age",
            [21],
            21,
            {"person": {"name": "Veda"}},
            None,
        ),
    ],
    ids=["person.age", "person.age:KeyError", "person.age:default"],
)
def test_key_path_pop(
    obj: dict[str, Any],
    key_path: str,
    default_args: list[Any],
    expected_result: Any,
    expected_obj: Any,
    expected_exception: type[Exception] | None,
):
    obj = copy.deepcopy(obj)
    with pytest.raises(expected_exception) if expected_exception else nullcontext():
        result: Any = key_path_pop(obj, key_path, *default_args)
        assert result == expected_result
        assert obj == expected_obj


@pytest.mark.parametrize(
    ("obj", "key_path", "value", "expected_result", "expected_exception"),
    [
        (
            {"person": {"name": "Veda"}},
            "person.age",
            22,
            {"person": {"name": "Veda", "age": 22}},
            None,
        ),
        (
            {"person": "Veda"},
            "person.age",
            22,
            None,
            TypeError,
        ),
        (
            {},
            "person.age",
            22,
            {"person": {"age": 22}},
            None,
        ),
        (
            {},
            "",
            22,
            {"": 22},
            None,
        ),
    ],
    ids=["person.age", "person.age:TypeError", "person.age:default", "no_key"],
)
def test_key_path_update(
    obj: dict[str, Any],
    key_path: str,
    value: Any,
    expected_result: Any,
    expected_exception: type[Exception] | None,
):
    obj = copy.deepcopy(obj)

    with pytest.raises(expected_exception) if expected_exception else nullcontext():
        key_path_update(obj, key_path, value)
        assert obj == expected_result


@pytest.mark.parametrize(
    ("obj", "transpositions", "extra_kwargs", "expected_result", "expected_exception"),
    [
        (
            {"person": {"name": "Veda"}},
            {"person.name": "person.first_name"},
            {},
            {"person": {"first_name": "Veda"}},
            None,
        ),
        (
            {"person": {"name": "Veda"}},
            {"person.name": "person.details.name"},
            {},
            {"person": {"details": {"name": "Veda"}}},
            None,
        ),
        (
            {"person": {"details": {"name": "Veda"}}},
            {"person.details.name": "person.name"},
            {},
            {"person": {"name": "Veda", "details": {}}},
            None,
        ),
        (
            {"person": {"name": "Veda"}},
            {"person.first_name": "person.given_name"},
            {},
            {"person": {"name": "Veda"}},
            None,
        ),
        (
            {"person": {"name": "Veda"}},
            {"person.first_name": "person.given_name"},
            {"strict": True},
            {"person": {"name": "Veda"}},
            KeyError,
        ),
    ],
    ids=[
        "rename_attr",
        "nest_attr",
        "unnest_attr",
        "misnamed_key",
        "misnamed_key:strict",
    ],
)
def test_key_path_transpose(
    obj: dict[str, Any],
    transpositions: dict[str, str],
    extra_kwargs: dict[str, Any],
    expected_result: Any,
    expected_exception: type[Exception] | None,
):
    obj = copy.deepcopy(obj)

    with pytest.raises(expected_exception) if expected_exception else nullcontext():
        key_path_transpose(obj, transpositions, **extra_kwargs)
        assert obj == expected_result
