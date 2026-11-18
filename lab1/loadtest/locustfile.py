"""Профіль «мало записів, багато читань».

Один цикл віртуального користувача: 1 запис і 9+ читань.
Три фази (StagesShape): 0 -> N за RAMP_UP_S, N протягом STEADY_S, N -> 0 за RAMP_DOWN_S.
Параметри можна перевизначити змінними середовища (LOAD_USERS, RAMP_UP_S, STEADY_S, RAMP_DOWN_S).
"""
import os
import random
import uuid

import gevent
from locust import HttpUser, LoadTestShape, between, task

N_USERS = int(os.getenv("LOAD_USERS", "200"))
RAMP_UP_S = int(os.getenv("RAMP_UP_S", "150"))
STEADY_S = int(os.getenv("STEADY_S", "300"))
RAMP_DOWN_S = int(os.getenv("RAMP_DOWN_S", "120"))
# Частка циклів, у яких клієнт повторює POST з тим самим Idempotency-Key (демо завдання 7). 0 = вимкнено.
RETRY_SHARE = float(os.getenv("RETRY_SHARE", "0"))
JOB_POLLS = 5


class ReadHeavyUser(HttpUser):
    host = os.getenv("URL")
    wait_time = between(2.5, 3.5)

    @task
    def write_then_read(self):
        # ---- 1 запис ----
        key = str(uuid.uuid4())
        params = {"name": f"Item_{random.randint(1000, 9999)}", "description": "Load test item"}
        item_id = job_id = None
        with self.client.post("/items", params=params, headers={"Idempotency-Key": key},
                              name="POST /items", catch_response=True) as r:
            if r.status_code in (200, 202):
                body = r.json()
                item_id, job_id = body.get("id"), body.get("job_id")
                r.success()
            else:
                r.failure(f"unexpected status {r.status_code}")

        if RETRY_SHARE and random.random() < RETRY_SHARE:
            with self.client.post("/items", params=params, headers={"Idempotency-Key": key},
                                  name="POST /items (retry, same key)", catch_response=True) as r:
                if r.headers.get("Idempotent-Replay") != "true":
                    r.failure("expected Idempotent-Replay: true")

        # ---- читання: список постів (3) ----
        recent_ids = []
        for i in range(3):
            r = self.client.get("/items", name="GET /items (list)")
            if i == 0 and r.ok:
                recent_ids = [it["id"] for it in r.json()]

        # ---- читання: статус свого запису (async: 1..JOB_POLLS опитувань) ----
        if item_id is None and job_id:
            for _ in range(JOB_POLLS):
                r = self.client.get(f"/jobs/{job_id}", name="GET /jobs/{job_id}")
                if r.ok and r.json().get("status") == "done":
                    item_id = r.json().get("item_id")
                    break
                gevent.sleep(0.2)

        # ---- читання: окремий пост (4), 2 рази щойно створений + 2 інші з першої сторінки ----
        ids = []
        if item_id is not None:
            ids += [item_id, item_id]
        while len(ids) < 4 and recent_ids:
            ids.append(random.choice(recent_ids))
        for i in ids:
            self.client.get(f"/items/{i}", name="GET /items/{item_id}")


class StagesShape(LoadTestShape):
    """Наростання -> стале навантаження -> спад, після чого тест зупиняється сам."""

    def tick(self):
        t = self.get_run_time()
        if t < RAMP_UP_S + STEADY_S:
            return N_USERS, N_USERS / RAMP_UP_S
        if t < RAMP_UP_S + STEADY_S + RAMP_DOWN_S:
            return 0, N_USERS / RAMP_DOWN_S
        return None
