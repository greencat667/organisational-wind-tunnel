"""The transport-agnostic service and its router (used directly by the browser build)."""
import json

from windtunnel import browser
from windtunnel.service import Service


def test_dispatch_routes_like_the_http_api(tmp_path):
    events = []
    svc = Service(emit=events.append, store_path=str(tmp_path / "s.sqlite"), use_fm=False, allow_model_engines=False)
    assert svc.dispatch("GET", "/health")[0] == 200
    st, exp = svc.dispatch("GET", "/experiment")
    assert st == 200 and exp["status"]["month"] == 3
    st, it = svc.dispatch("POST", "/interpret", {"fast": "true"}, {"text": "Reduce admin by 20%"})
    assert st == 200 and it["plan"]["changes"]
    assert svc.dispatch("POST", "/run", None, {"plan": it["plan"], "text": "cut"})[0] == 200
    assert any(e["type"] == "forked" for e in events)
    st, status = svc.dispatch("POST", "/play", None, {"steps": 2})
    assert st == 200 and status["month"] == 5 and sum(e["type"] == "frame" for e in events) == 2
    assert svc.dispatch("GET", "/effects", {"min_effect": "0.5"})[0] == 200
    assert svc.dispatch("GET", "/team/intervention/finance")[1]["team"]["name"] == "Finance"
    assert svc.dispatch("GET", "/export/baseline/metrics", {"fmt": "csv"})[1].startswith("month,")
    assert svc.dispatch("GET", "/nope")[0] == 404
    assert svc.dispatch("GET", "/team/intervention/nope")[0] == 404
    # model engines are refused quietly in the browser build
    assert svc.dispatch("POST", "/experiment", None, {"engine": "laya"})[1]["status"]["engine"] == "heuristic"


def test_browser_entry_points_round_trip_json(tmp_path):
    json.loads(browser.init(str(tmp_path / "b.sqlite"), max_batch=10))
    r = json.loads(browser.request("POST", "/play", "{}", json.dumps({"steps": 1})))
    assert r["status"] == 200 and any(e["type"] == "frame" for e in r["events"])
    it = json.loads(browser.request("POST", "/interpret", json.dumps({"fast": "true"}), json.dumps({"text": "Reduce admin by 20%"})))["body"]
    browser.request("POST", "/run", "{}", json.dumps({"plan": it["plan"], "text": "cut"}))
    prep = json.loads(browser.batch_prepare(json.dumps({"n": 2, "months": 3})))["body"]
    results = [json.loads(browser.run_one(json.dumps(a))) for a in prep["args"]]
    json.loads(browser.batch_finish(prep["job_id"], json.dumps(results), "", 1.0))
    job = json.loads(browser.request("GET", f"/batch/{prep['job_id']}", "{}", "null"))["body"]
    assert job["status"] == "done" and job["result"]["summary"]["n"] == 2
