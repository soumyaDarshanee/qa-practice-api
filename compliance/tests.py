"""A few backend tests so `make test` has something to run.

Your real practice suites (Postman/Newman, Playwright API tests) belong in a
separate tests repo that calls this API from the outside.
"""

from django.core.management import call_command
from rest_framework.test import APITestCase

from .seed import DEFAULT_PASSWORD, seed_users


class ApiSmokeTests(APITestCase):
    def setUp(self):
        call_command("loaddata", "reference_data", verbosity=0)
        seed_users()

    def login(self, email):
        res = self.client.post("/api/auth/login/", {"email": email, "password": DEFAULT_PASSWORD}, format="json")
        self.assertEqual(res.status_code, 200, res.content)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {res.data['token']}")

    def test_admin_can_create_supplier(self):
        self.login("admin@qa.test")
        res = self.client.post(
            "/api/suppliers/", {"name": "Test BV", "email": "a@b.nl", "country": "NL"}, format="json"
        )
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(res.data["country_name"], "Netherlands")

    def test_viewer_cannot_create_supplier(self):
        self.login("viewer@qa.test")
        res = self.client.post("/api/suppliers/", {"name": "X", "email": "a@b.nl", "country": "NL"}, format="json")
        self.assertEqual(res.status_code, 403)

    def test_suppliers_are_isolated_per_organisation(self):
        self.login("admin@qa.test")
        self.client.post("/api/suppliers/", {"name": "Private BV", "email": "a@b.nl", "country": "NL"}, format="json")
        self.client.credentials()
        self.login("other-admin@qa.test")
        res = self.client.get("/api/suppliers/")
        self.assertEqual(res.data["count"], 0)

    def test_wrong_password_returns_401(self):
        res = self.client.post("/api/auth/login/", {"email": "admin@qa.test", "password": "nope"}, format="json")
        self.assertEqual(res.status_code, 401)
