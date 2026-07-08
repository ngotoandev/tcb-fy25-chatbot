from ingest.metrics_data import METRICS

def by_id(mid):
    return next(m for m in METRICS if m["metric_id"] == mid)

def test_key_fy25_figures():
    assert by_id("pbt")["values"]["FY25"] == 32538
    assert by_id("toi")["values"]["FY25"] == 53391
    assert by_id("casa_ratio")["values"]["4Q25"] == 40.4
    assert by_id("npl")["values"]["4Q25"] == 1.13
    assert by_id("car_basel2")["values"]["4Q25"] == 14.6
    assert by_id("total_assets")["values"]["4Q25"] == 1192344

def test_schema():
    for m in METRICS:
        assert m["metric_id"] and m["name"] and m["unit"] and m["source_page"]
        assert isinstance(m["aliases"], list) and m["values"]
