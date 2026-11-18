import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

pytestmark = pytest.mark.skipif(
    not (os.getenv("DATABASE_URL") and os.getenv("REDIS_URL")),
    reason="DATABASE_URL and REDIS_URL are required",
)


@pytest.fixture()
def app_module():
    import main

    return main


@pytest.fixture()
def client(app_module):
    from fastapi.testclient import TestClient

    with TestClient(app_module.app) as c:
        yield c


def count_rows(app_module, name: str) -> int:
    with app_module.SessionLocal() as db:
        return db.query(app_module.models.Item).filter(app_module.models.Item.name == name).count()


def test_sync_same_key_one_row_two_identical_responses(client, app_module, monkeypatch):
    monkeypatch.setattr(app_module, "WRITE_MODE", "sync")
    name = f"idem-sync-{uuid.uuid4()}"
    headers = {"Idempotency-Key": str(uuid.uuid4())}

    r1 = client.post("/items", params={"name": name, "description": "d"}, headers=headers)
    r2 = client.post("/items", params={"name": name, "description": "d"}, headers=headers)
    assert r1.status_code == r2.status_code == 200
    assert r1.json() == r2.json()
    assert "idempotent-replay" not in r1.headers
    assert r2.headers["idempotent-replay"] == "true"
    assert count_rows(app_module, name) == 1


def test_without_key_every_request_writes(client, app_module, monkeypatch):
    monkeypatch.setattr(app_module, "WRITE_MODE", "sync")
    name = f"no-key-{uuid.uuid4()}"
    client.post("/items", params={"name": name})
    client.post("/items", params={"name": name})
    assert count_rows(app_module, name) == 2


def test_async_same_key_one_message_and_duplicate_delivery_is_harmless(client, app_module, monkeypatch):
    monkeypatch.setattr(app_module, "WRITE_MODE", "async")
    sent = []
    monkeypatch.setattr(app_module.jobs, "enqueue", lambda payload: sent.append(payload))
    name = f"idem-async-{uuid.uuid4()}"
    headers = {"Idempotency-Key": str(uuid.uuid4())}

    r1 = client.post("/items", params={"name": name}, headers=headers)
    r2 = client.post("/items", params={"name": name}, headers=headers)

    assert r1.status_code == r2.status_code == 202
    assert r1.json() == r2.json()
    assert r1.headers["location"] == r2.headers["location"]
    assert len(sent) == 1

    import worker

    id1, created1 = worker.process_job(sent[0])
    id2, created2 = worker.process_job(sent[0])
    assert (created1, created2) == (True, False)
    assert id1 == id2
    assert count_rows(app_module, name) == 1


def test_same_key_different_payload_is_rejected(client, app_module, monkeypatch):
    monkeypatch.setattr(app_module, "WRITE_MODE", "sync")
    headers = {"Idempotency-Key": str(uuid.uuid4())}
    assert client.post("/items", params={"name": "a"}, headers=headers).status_code == 200
    assert client.post("/items", params={"name": "b"}, headers=headers).status_code == 422


def test_concurrent_requests_with_same_key_write_once(app_module, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setattr(app_module, "WRITE_MODE", "sync")
    name = f"idem-race-{uuid.uuid4()}"
    headers = {"Idempotency-Key": str(uuid.uuid4())}

    def call(_):
        return TestClient(app_module.app).post("/items", params={"name": name}, headers=headers)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(call, range(2)))

    assert {r.status_code for r in responses} <= {200, 409}
    assert any(r.status_code == 200 for r in responses)
    assert count_rows(app_module, name) == 1
    again = TestClient(app_module.app).post("/items", params={"name": name}, headers=headers)
    assert again.status_code == 200 and again.headers["idempotent-replay"] == "true"
