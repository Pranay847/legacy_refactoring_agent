"""
Locust load test for the Legacy Refactoring Agent API.
---------------------------------------------------------------------------
Python alternative to k6_smoke.js. Exercises the read-heavy, cacheable
endpoints. Mutating/expensive endpoints are deliberately excluded.

Usage:
    pip install locust
    locust -f loadtest/locustfile.py --host http://127.0.0.1:8000
    # then open http://localhost:8089 and start the test

    # headless example:
    AUTH_TOKEN=<clerk-jwt> locust -f loadtest/locustfile.py \
        --host https://api.example.com --headless -u 50 -r 10 -t 2m
"""
import os

from locust import HttpUser, between, task

AUTH_TOKEN = os.environ.get("AUTH_TOKEN", "")


class ApiUser(HttpUser):
    wait_time = between(1, 3)

    def _headers(self):
        return {"Authorization": f"Bearer {AUTH_TOKEN}"} if AUTH_TOKEN else {}

    @task(3)
    def status(self):
        self.client.get("/api/status", headers=self._headers(), name="/api/status")

    @task(2)
    def clusters(self):
        with self.client.get(
            "/api/clusters", headers=self._headers(), name="/api/clusters", catch_response=True
        ) as r:
            if r.status_code in (200, 404):
                r.success()

    @task(2)
    def graph(self):
        with self.client.get(
            "/api/graph", headers=self._headers(), name="/api/graph", catch_response=True
        ) as r:
            if r.status_code in (200, 404):
                r.success()

    @task(1)
    def services(self):
        self.client.get("/api/services", headers=self._headers(), name="/api/services")
