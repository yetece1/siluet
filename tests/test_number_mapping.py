import random

import pytest

from siluet.mapping_store import MappingStore, split_phone
from siluet.normalization import digits


def _store() -> MappingStore:
    return MappingStore(b"k" * 32)


def _random_tckn(rng: random.Random) -> str:
    while True:
        first9 = [rng.randint(1, 9)] + [rng.randint(0, 9) for _ in range(8)]
        d10 = (sum(first9[0:9:2]) * 7 - sum(first9[1:8:2])) % 10
        d11 = (sum(first9) + d10) % 10
        value = "".join(map(str, first9)) + str(d10) + str(d11)
        if MappingStore._valid_tckn(value):
            return value


def _same_positions(a: str, b: str) -> int:
    return sum(x == y for x, y in zip(a, b))


@pytest.mark.parametrize("raw, expected", [
    ("05321234567", ("0", "5", "321234567")),
    ("905321234567", ("90", "5", "321234567")),
    ("00905321234567", ("0090", "5", "321234567")),
    ("5321234567", ("", "5", "321234567")),
    ("2125551234", ("", "2", "125551234")),
    ("4915112345678", ("", "4", "915112345678")),
])
def test_split_phone(raw, expected):
    assert split_phone(raw) == expected


def test_phone_body_fully_replaced():
    rng = random.Random(7)
    store = _store()
    same = []
    for _ in range(200):
        source = "05" + "".join(str(rng.randint(0, 9)) for _ in range(9))
        out = digits(store.phone(source))
        assert len(out) == len(source)
        assert out[:2] == "05"
        assert out[2:] != source[2:]
        same.append(_same_positions(out[2:], source[2:]))
    assert sum(same) / len(same) < 2.0


def test_phone_keeps_format_and_consistency():
    store = _store()
    first = store.phone("0532 123 45 67")
    assert [i for i, c in enumerate(first) if c == " "] == [4, 8, 11]
    assert first.startswith("05")
    assert store.phone("0532 123 45 67") == first
    international = digits(store.phone("+90 532 123 4567"))
    assert international.startswith("905")
    assert international[2:] != "5321234567"


def test_short_service_numbers_unchanged():
    store = _store()
    assert store.phone("112") == "112"
    assert store.phone("1555") == "1555"


def test_tc_fully_replaced_and_invalid():
    rng = random.Random(11)
    store = _store()
    same = []
    for _ in range(200):
        source = _random_tckn(rng)
        out = digits(store.tc(source))
        assert len(out) == 11 and out[0] != "0"
        assert MappingStore._valid_tckn(out) is False
        same.append(_same_positions(out[:10], source[:10]))
    assert sum(same) / len(same) < 2.0


def test_no_collisions():
    store = _store()
    sources = [f"0532{n:07d}" for n in range(5000)]
    outputs = {store.phone(s) for s in sources}
    assert len(outputs) == 5000


def test_same_subscriber_in_different_formats_maps_to_same_body():
    store = _store()
    forms = ["05321234567", "905321234567", "+90 532 123 45 67", "00905321234567", "5321234567", "0 (532) 123 45 67"]
    bodies = set()
    for form in forms:
        out = digits(store.phone(form))
        prefix, class_digit, body = split_phone(out)
        assert class_digit == "5"
        bodies.add(body)
    assert len(bodies) == 1
    assert bodies.pop() != "321234567"


def test_landline_formats_share_body_and_foreign_numbers_stay_separate():
    store = _store()
    a = split_phone(digits(store.phone("02125551234")))[2]
    b = split_phone(digits(store.phone("902125551234")))[2]
    assert a == b
    foreign = digits(store.phone("4915112345678"))
    assert len(foreign) == 13 and foreign[0] == "4"
