from django.test import Client, TestCase
from django.urls import reverse

from services.models import BakkieDriver, ServiceAnalyticsEvent


class DriverProfileAnalyticsTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_anonymous_view_records_event_with_null_user(self):
        driver = BakkieDriver.objects.create(
            full_name="Test Driver",
            email="driver@example.com",
            phone_number="+27123456789",
            vehicle_type="small",
            vehicle_registration="ABC123",
            address="123 Test St",
            city="Testville",
            province="TestProvince",
            is_verified=True,
        )

        url = reverse("services:driver_profile", args=[driver.id])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

        evt = ServiceAnalyticsEvent.objects.filter(event_type="driver_view", metadata__driver=driver.id).first()
        self.assertIsNotNone(evt)
        self.assertIsNone(evt.user)
