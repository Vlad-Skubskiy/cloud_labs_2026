import random
import uuid

from locust import HttpUser, SequentialTaskSet, between, task


class UserBehavior(SequentialTaskSet):
    created_id = None
    job_id = None
    key = None
    url = None

    @task
    def create_item(self):
        name = f"Item_{random.randint(1000, 9999)}"
        description = "Load test item"
        self.key = str(uuid.uuid4())
        self.url = f"/items?name={name}&description={description}"

        response = self.client.post(self.url, headers={"Idempotency-Key": self.key}, name="POST /items")
        if response.status_code in (200, 202):
            try:
                data = response.json()
                self.created_id = data.get("id")
                self.job_id = data.get("job_id")
            except Exception:
                pass

    @task
    def retry_same_request(self):
        if self.url is None or random.random() > 0.2:
            return
        with self.client.post(self.url, headers={"Idempotency-Key": self.key},
                              name="POST /items (retry, same key)", catch_response=True) as r:
            if r.headers.get("Idempotent-Replay") == "true":
                r.success()
            else:
                r.failure("expected Idempotent-Replay: true")

    @task
    def read_operations(self):
        for _ in range(3):
            self.client.get("/items", name="GET /items (list)")

        if self.job_id:
            self.client.get(f"/jobs/{self.job_id}", name="GET /jobs/{job_id}")

        target_id = self.created_id if self.created_id else 1
        for _ in range(4):
            self.client.get(f"/items/{target_id}", name="GET /items/{item_id}")

        for _ in range(2):
            self.client.get("/health", name="GET /health")


class ReadHeavyUser(HttpUser):
    tasks = [UserBehavior]
    wait_time = between(0.5, 1.5)
