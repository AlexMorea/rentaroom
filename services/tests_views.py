from django.contrib.auth.models import User
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
        assert evt is not None  # narrows for the type checker; assertIsNotNone above already fails the test otherwise
        self.assertIsNone(evt.user)


class DriverDashboardTests(TestCase):
    """
    Regression coverage for a bug where driver_dashboard() rendered
    "services/driver_dashboard.html" (missing the "bakkie/" prefix used by
    every other template in this view module), raising TemplateDoesNotExist
    for every verified driver visiting their own dashboard.
    """

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="dashboard_driver",
            email="dashboard_driver@example.com",
            password="password123",
        )
        self.driver = BakkieDriver.objects.create(
            user=self.user,
            full_name="Dashboard Driver",
            email="dashboard_driver@example.com",
            phone_number="+27123456789",
            vehicle_type="small",
            address="123 Test St",
            is_verified=True,
            application_status="approved",
        )

    def test_verified_driver_can_load_dashboard(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse("services:driver_dashboard"))
        self.assertEqual(resp.status_code, 200)
