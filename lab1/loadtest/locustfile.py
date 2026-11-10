import random
from locust import HttpUser, task, SequentialTaskSet, between, LoadTestShape

class UserBehavior(SequentialTaskSet):
    created_id = None

    @task
    def create_item(self):
        name = f"Item_{random.randint(1000, 9999)}"
        description = "Load test item"
        
        response = self.client.post(
            f"/items?name={name}&description={description}",
            name="POST /items"
        )
        if response.status_code == 200:
            try:
                data = response.json()
                self.created_id = data.get("id")
            except Exception:
                pass

    @task
    def read_operations(self):
        for _ in range(3):
            self.client.get(f"/items", name="GET /items (list)")

        target_id = self.created_id if self.created_id else 1
        for _ in range(4):
            self.client.get(f"/items/{target_id}", name="GET /items/{item_id}")

        for _ in range(2):
            self.client.get("/health", name="GET /health")

class ReadHeavyUser(HttpUser):
    tasks = [UserBehavior]
    wait_time = between(0.5, 1.5)