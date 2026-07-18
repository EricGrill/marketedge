from src.market_adapters import (
    GenericMarketAdapter,
    WeatherMarketAdapter,
    normalize_market,
)


def test_weather_adapter_normalizes_title_and_relationship_metadata():
    market = WeatherMarketAdapter().normalize(
        {
            "ticker": "HIGHNY-26JUN18-B88.5",
            "title": "NYC Daily High above 88.5F",
            "yes_bid": 39,
            "yes_ask": 41,
            "event_ticker": "HIGHNY-26JUN18",
            "close_date": "2026-06-18T20:00:00Z",
        }
    )

    assert market.ticker == "HIGHNY-26JUN18-B88.5"
    assert market.category == "weather"
    assert market.event_type == "temp"
    assert market.location == "NYC"
    assert market.region == "northeast"
    assert market.threshold == 88.5
    assert market.relationship_group == "HIGHNY-26JUN18"
    assert market.date_bucket == "2026-06-18"


def test_generic_adapter_handles_non_weather_market_fixture():
    market = normalize_market(
        {
            "ticker": "FED-26JUL-HIKE",
            "title": "Fed rate hike in July",
            "category": "economics",
            "event_type": "rates",
            "yes_bid": 46,
            "yes_ask": 48,
            "relationship_group": "fed-july",
        },
        adapters=(GenericMarketAdapter(),),
    )

    assert market.category == "economics"
    assert market.event_type == "rates"
    assert market.relationship_group == "fed-july"
