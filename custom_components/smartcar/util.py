from functools import reduce
import hashlib
import hmac
from typing import Any, cast, overload


def unique_id_from_entry_data(data: dict) -> str:
    return " ".join(sorted(data["vehicles"].keys())).lower()


def vins_from_entry_data(data: dict) -> str:
    return " ".join(sorted([vehicle["vin"] for vehicle in data["vehicles"].values()]))


def hmac_sha256_hexdigest(key: str, msg: str) -> str:
    return hmac.new(key.encode(), msg.encode(), hashlib.sha256).hexdigest()


def _key_path_traverse[KeyT: str, ValueT](
    dict_obj: dict[KeyT, ValueT],
    key_path: str,
    offset: int = 0,
    /,
    *,
    fill: bool = False,
) -> Any:  # noqa: ANN401
    assert offset <= 0
    try:
        return reduce(
            lambda v, key: None
            if v is None
            else v.setdefault(key, {})
            if fill
            else v[key],
            key_path.split(".")[: offset or None],
            cast("Any", dict_obj),
        )
    except KeyError as err:
        raise KeyError(key_path) from err


def key_path_get[KeyT: str, ValueT, EndValueT](
    dict_obj: dict[KeyT, ValueT], key_path: str, default: EndValueT | None = None, /
) -> EndValueT | None:
    try:
        return cast("EndValueT", _key_path_traverse(dict_obj, key_path))
    except KeyError:
        return default


@overload
def key_path_pop[KeyT: str, ValueT, EndValueT](
    dict_obj: dict[KeyT, ValueT], key_path: str, default: EndValueT | None = None, /
) -> EndValueT: ...


@overload
def key_path_pop[KeyT: str, ValueT](
    dict_obj: dict[KeyT, ValueT], key_path: str
) -> Any: ...  # noqa: ANN401


def key_path_pop(dict_obj, key_path, /, *args):
    try:
        dict_obj = _key_path_traverse(dict_obj, key_path, -1)
        return dict_obj.pop(key_path.split(".")[-1])
    except KeyError as err:
        has_default = len(args) > 0
        if has_default:
            return args[0]
        raise KeyError(key_path) from err


def key_path_update[KeyT: str, ValueT, EndValueT](
    dict_obj: dict[KeyT, ValueT], key_path: str, value: EndValueT
) -> None:
    sub_dict: Any = _key_path_traverse(dict_obj, key_path, -1, fill=True)
    sub_dict[key_path.rsplit(".", maxsplit=1)[-1]] = value


def key_path_transpose[KeyT: str, ValueT](
    dict_obj: dict[KeyT, ValueT],
    key_path_transpositions: dict[str, str],
    *,
    strict: bool = False,
) -> None:
    for from_key_path, to_key_path in key_path_transpositions.items():
        try:
            value: Any = key_path_pop(dict_obj, from_key_path)
            key_path_update(dict_obj, to_key_path, value)
        except KeyError as err:
            if strict:
                raise KeyError(from_key_path) from err
