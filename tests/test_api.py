from fastapi.testclient import TestClient

from app.main import create_app

client = TestClient(create_app(), base_url="http://127.0.0.1:8765")


def test_solar_endpoint_returns_sun_position():
    response = client.post("/api/solar", json={
        "latitude": 39.742, "longitude": -105.178,
        "timestamp": "2024-06-21T19:00:00Z",
    })
    assert response.status_code == 200
    body = response.json()
    assert 177 <= body["azimuth_deg"] <= 183
    assert body["utc_time"] == "2024-06-21T19:00:00Z"
    assert 15 <= body["tilt_deg"] <= 18


def test_day_endpoint_samples_a_utc_day():
    response = client.post("/api/day", json={
        "latitude": 34.05, "longitude": -118.25, "date": "2024-03-10",
    })
    assert response.status_code == 200
    assert len(response.json()["samples"]) == 144


def test_bad_input_is_rejected():
    bad_latitude = {"latitude": 99, "longitude": 0, "timestamp": "2024-06-21T19:00:00Z"}
    assert client.post("/api/solar", json=bad_latitude).status_code == 422
    bad_date = {"latitude": 0, "longitude": 0, "date": "not-a-date"}
    assert client.post("/api/day", json=bad_date).status_code == 422


def test_non_loopback_host_is_refused():
    other = TestClient(create_app(), base_url="http://example.com")
    assert other.post("/api/day", json={}).status_code == 403
