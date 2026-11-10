import random
from locust import HttpUser, task, sequential_task, SequentialTaskSet, between

class UserBehavior(SequentialTaskSet):
    created_id = None

    @task
    def create_note(self):
        payload = {
            "title": f"Test note {random.randint(1000, 9999)}",
            "content": "Load testing content"
        }
        with self.client.post("/notes", json=payload, catch_response=True) as response:
            if response.status_code in (200, 201):
                try:
                    data = response.json()
                    self.create_id = data.get('id')
                except Exception:
                    pass

    @task
    def read_operations(self):
        for _ in range(3):
            self.client.get(f"/items", name="/items (list)")

        target_id = self.created_id if self.created_id else 1
        for _ in range(4):
            self.client.get(f"/items/{target_id}", name="/items/{id}")

        for _ in range(2):
            self.client.get("/user/profile", name="/user/profile")

class ReadHeavyUser(HttpUser):
    tasks = [UserBehavior]
    wait_time = between(0.5, 1.5)