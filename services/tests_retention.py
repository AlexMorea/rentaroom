from datetime import timedelta
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from services.models import (
    EmergencyEvent,
    GuardianLocationPing,
    GuardianSession,
    PanicAlert,
)


class GuardianRetentionTests(TestCase):
    """purge_guardian_data: location data goes after 30 days, panic
    records after 12 months, and nothing is touched without --force."""

    def setUp(self):
        self.user = User.objects.create_user("tenant", password="x")
        self.now = timezone.now()

    def session(self, days_ago, **extra):
        session = GuardianSession.objects.create(
            user=self.user,
            destination="Viewing in Mamelodi East",
            emergency_contact_name="Mom",
            emergency_contact_phone="0710000000",
            started_at=self.now - timedelta(days=days_ago),
            latest_latitude=-25.7,
            latest_longitude=28.4,
            **extra,
        )
        return session

    def ping(self, session, days_ago):
        ping = GuardianLocationPing.objects.create(session=session, latitude=-25.7, longitude=28.4)
        # auto_now_add ignores the value passed to create(), so backdate after.
        GuardianLocationPing.objects.filter(pk=ping.pk).update(
            created_at=self.now - timedelta(days=days_ago)
        )
        return ping

    def alert(self, session, days_ago):
        alert = PanicAlert.objects.create(session=session, latitude=-25.7, longitude=28.4)
        PanicAlert.objects.filter(pk=alert.pk).update(created_at=self.now - timedelta(days=days_ago))
        return alert

    def run_purge(self, *args):
        out = StringIO()
        call_command("purge_guardian_data", *args, stdout=out)
        return out.getvalue()

    def test_report_only_without_force(self):
        session = self.session(days_ago=40)
        self.ping(session, days_ago=40)

        out = self.run_purge()

        self.assertIn("Report only", out)
        self.assertIn("1 location pings", out)
        self.assertEqual(GuardianLocationPing.objects.count(), 1)
        session.refresh_from_db()
        self.assertEqual(session.emergency_contact_phone, "0710000000")

    def test_ordinary_session_cleared_after_30_days(self):
        old = self.session(days_ago=31)
        old_ping = self.ping(old, days_ago=31)
        recent = self.session(days_ago=2)
        recent_ping = self.ping(recent, days_ago=2)

        self.run_purge("--force")

        self.assertFalse(GuardianLocationPing.objects.filter(pk=old_ping.pk).exists())
        self.assertTrue(GuardianLocationPing.objects.filter(pk=recent_ping.pk).exists())

        old.refresh_from_db()
        self.assertIsNone(old.latest_latitude)
        self.assertIsNone(old.latest_longitude)
        self.assertEqual(old.emergency_contact_name, "")
        self.assertEqual(old.emergency_contact_phone, "")
        self.assertEqual(old.destination, "Viewing in Mamelodi East")  # usage record stays

        recent.refresh_from_db()
        self.assertEqual(recent.emergency_contact_phone, "0710000000")
        self.assertIsNotNone(recent.latest_latitude)

    def test_panic_session_kept_for_12_months(self):
        session = self.session(days_ago=200, status="panic")
        ping = self.ping(session, days_ago=200)
        alert = self.alert(session, days_ago=200)

        self.run_purge("--force")

        self.assertTrue(GuardianLocationPing.objects.filter(pk=ping.pk).exists())
        self.assertTrue(PanicAlert.objects.filter(pk=alert.pk).exists())
        session.refresh_from_db()
        self.assertEqual(session.emergency_contact_phone, "0710000000")

    def test_panic_session_cleared_after_12_months(self):
        session = self.session(days_ago=370, status="panic")
        self.ping(session, days_ago=370)
        self.alert(session, days_ago=370)
        event = EmergencyEvent.objects.create(
            session=session, event_type="panic", latitude=-25.7, longitude=28.4
        )
        EmergencyEvent.objects.filter(pk=event.pk).update(created_at=self.now - timedelta(days=370))

        self.run_purge("--force")

        self.assertEqual(GuardianLocationPing.objects.count(), 0)
        self.assertEqual(PanicAlert.objects.count(), 0)
        self.assertEqual(EmergencyEvent.objects.count(), 0)
        session.refresh_from_db()
        self.assertIsNone(session.latest_latitude)
        self.assertEqual(session.emergency_contact_name, "")
