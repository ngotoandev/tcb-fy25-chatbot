from app.services.metrics_store import MetricsStore, extract_periods

store = MetricsStore("data/artifacts/metrics.json")

def test_extract_periods():
    assert extract_periods("pbt in fy25") == ["FY25"]
    assert extract_periods("casa in 3Q25") == ["3Q25"]
    assert extract_periods("casa in q3 2025") == ["3Q25"]
    assert extract_periods("npl in the fourth quarter of 2025") == ["4Q25"]
    assert extract_periods("total assets") == []

def test_lookup_pbt():
    hits = store.lookup("What was profit before tax in FY25?")
    assert hits and hits[0]["metric_id"] == "pbt"

def test_lookup_casa_alias():
    hits = store.lookup("current account savings account ratio")
    assert any(h["metric_id"] == "casa_ratio" for h in hits)

def test_render_contains_value_and_page():
    hits = store.lookup("profit before tax FY25")
    text = store.render(hits, "profit before tax FY25")
    assert "32,538" in text and "[p.13]" in text

def test_render_trend_lists_quarters():
    hits = store.lookup("How did the CASA ratio evolve over 2025?")
    text = store.render(hits, "How did the CASA ratio evolve over 2025?")
    for v in ("39.4", "41.1", "42.5", "40.4"):
        assert v in text

def test_lookup_plural_npl():
    hits = store.lookup("What are the NPLs in FY25?")
    assert hits and hits[0]["metric_id"] == "npl"

def test_lookup_plural_revenue():
    hits = store.lookup("What were revenues in FY25?")
    assert any(h["metric_id"] == "toi" for h in hits)

def test_lookup_card_not_car():
    # plural tolerance must NOT reopen the car-in-card false positive
    hits = store.lookup("How much were card fees in FY25?")
    assert hits and hits[0]["metric_id"] == "card_fees"
    assert all(h["metric_id"] != "car_basel2" for h in hits)
