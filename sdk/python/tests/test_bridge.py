# SPDX-License-Identifier: Apache-2.0
import httpx
import pytest

from onemind_sdk.bridge import BridgePoller, emit, replay


def document(props, geometry=None):
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "id": "source-1", "properties": props, "geometry": geometry},
    ]}


@pytest.mark.parametrize(("provider", "props", "expected"), [
    ("usgs", {"title": "Earthquake", "updated": 1767225600000}, "earthquake"),
    ("nws", {"headline": "Wind alert", "sent": "2026-01-01T00:00:00Z"}, "weather"),
    ("eonet", {"title": "Wildfire", "date": "2026-01-01T00:00:00Z"}, "natural_event"),
])
def test_replay_is_deterministic_without_network(provider, props, expected):
    payload = document(props, {"type": "Point", "coordinates": [1, 2, 3]})
    first = replay(provider, payload)
    assert first == replay(provider, payload)
    assert first[0]["name"] == expected and first[0]["revision"] == 1767225600000
    assert first[0]["position"] == {"type": "Point", "coordinates": [1, 2]}


def test_fetch_backs_off_on_refusal_and_only_commits_processed_etags():
    requests = []
    now = [0.0]

    def reply(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(503)
        if len(requests) == 3:
            return httpx.Response(302, headers={"Location": "https://example.invalid"})
        if request.headers.get("If-None-Match"):
            return httpx.Response(304)
        return httpx.Response(200, headers={"ETag": '"v1"'}, content=b'{}')

    with httpx.Client(transport=httpx.MockTransport(reply), trust_env=False) as http:
        poller = BridgePoller("nws", "OneMind Atlas bridge tests", http, lambda: now[0])
        with pytest.raises(httpx.HTTPStatusError):
            poller.fetch()
        assert poller.fetch() is None
        now[0] = 60
        snapshot = poller.fetch()
        assert snapshot.body == b"{}" and poller.etag is None
        poller.commit(snapshot)
        now[0] = 120
        with pytest.raises(httpx.HTTPStatusError) as refusal:
            poller.fetch()
        assert refusal.value.response.status_code == 302
        now[0] = 180
        assert poller.fetch() is None
    assert len(requests) == 4
    assert requests[-1].headers["If-None-Match"] == '"v1"'
    assert requests[-1].headers["User-Agent"] == "OneMind Atlas bridge tests"
    assert all(request.url.host == "api.weather.gov" for request in requests)


def test_emit_respects_gateway_batch_limit_without_hiding_a_refusal():
    class Client:
        batches = []

        def call(self, request):
            self.batches.append(request.body)
            assert request.path == "/v1/bridges/test-bridge/events"
            return {"accepted": 0, "duplicates": 0, "paused": True, "rejected": []}

    gateway = Client()
    assert emit(gateway, "test-bridge", [{"id": str(i)} for i in range(201)])[0]["paused"]
    assert len(gateway.batches) == 1 and len(gateway.batches[0]["events"]) == 100
    with pytest.raises(ValueError):
        emit(gateway, "no/slash", [{"id": "one"}])
