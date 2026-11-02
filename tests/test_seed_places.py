def test_build_places_count_and_inactive(build_places):
    places = build_places(count=20, inactive=4)
    assert len(places) == 20
    assert sum(1 for place in places if not place.isActive) == 4
    assert sum(1 for place in places if place.isActive) == 16


def test_build_places_addresses_and_capacity(build_places):
    places = build_places(count=20, inactive=4)
    assert all(place.address.startswith("ул. ") for place in places)
    assert all(1 <= place.capacity <= 8 for place in places)


def test_build_places_validation(build_places):
    try:
        build_places(count=5, inactive=6)
    except ValueError as error:
        assert "больше" in str(error)
    else:
        raise AssertionError("Ожидалась ошибка при inactive > count")
