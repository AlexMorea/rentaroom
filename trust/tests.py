from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from listings.models import Room

from .models import FraudReport


def make_room(owner, **kwargs):
    data = {
        "title": "R1",
        "owner": owner,
        "description": "desc",
        "price": 1000,
        "location": "Loc",
        "suburb": "S",
        "town": "T",
        "city": "C",
        "full_address": "Addr",
        "postal_code": "0000",
        "room_type": Room.ROOM_TYPES[0][0],
        "contact_phone": "0123456",
    }
    data.update(kwargs)
    return Room.objects.create(**data)


class ReportRoomTests(TestCase):
    def setUp(self):
        self.landlord = User.objects.create_user(username="landlord", password="p")
        self.tenant = User.objects.create_user(username="tenant", password="p")
        self.room = make_room(self.landlord)

    def test_report_room_persists_a_fraud_report(self):
        self.client.login(username="tenant", password="p")
        resp = self.client.post(
            reverse("report_room", args=[self.room.id]),
            {"reason": "scam", "detail": "asked for a deposit before viewing"},
        )
        self.assertRedirects(resp, reverse("room_detail", args=[self.room.id]))

        report = FraudReport.objects.get()
        self.assertEqual(report.category, FraudReport.CATEGORY_SCAM)
        self.assertEqual(report.room, self.room)
        self.assertEqual(report.reported_user, self.landlord)
        self.assertEqual(report.reporter, self.tenant)
        self.assertEqual(report.status, FraudReport.STATUS_NEW)

    def test_report_room_requires_a_reason(self):
        self.client.login(username="tenant", password="p")
        self.client.post(reverse("report_room", args=[self.room.id]), {"detail": "x"})
        self.assertEqual(FraudReport.objects.count(), 0)

    def test_report_room_unknown_reason_falls_back_to_other(self):
        self.client.login(username="tenant", password="p")
        self.client.post(
            reverse("report_room", args=[self.room.id]),
            {"reason": "not-a-real-category", "detail": "x"},
        )
        report = FraudReport.objects.get()
        self.assertEqual(report.category, FraudReport.CATEGORY_OTHER)


class ReportFraudPageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="reporter", password="p")

    def test_submitting_the_form_creates_a_report_and_shows_reference(self):
        self.client.login(username="reporter", password="p")
        resp = self.client.post(
            reverse("trust:report_fraud"),
            {
                "category": FraudReport.CATEGORY_FAKE_LANDLORD,
                "detail": "someone asked for cash via WhatsApp",
                "reporter_contact": "reporter@example.com",
                "listing_reference": "rooms4you.co.za/rooms/99/",
            },
            follow=True,
        )
        report = FraudReport.objects.get()
        self.assertEqual(report.category, FraudReport.CATEGORY_FAKE_LANDLORD)
        self.assertEqual(report.reporter, self.user)
        self.assertIn("rooms4you.co.za/rooms/99/", report.detail)
        self.assertContains(resp, report.reference_code)

    def test_anonymous_report_has_no_reporter(self):
        resp = self.client.post(
            reverse("trust:report_fraud"),
            {
                "category": FraudReport.CATEGORY_OTHER,
                "detail": "suspicious message",
                "reporter_contact": "someone@example.com",
            },
        )
        self.assertEqual(resp.status_code, 302)
        report = FraudReport.objects.get()
        self.assertIsNone(report.reporter)
        self.assertEqual(report.reporter_contact, "someone@example.com")

    def test_trust_home_publishes_transparency_counts(self):
        FraudReport.objects.create(category=FraudReport.CATEGORY_SCAM, status=FraudReport.STATUS_RESOLVED)
        FraudReport.objects.create(category=FraudReport.CATEGORY_SPAM, status=FraudReport.STATUS_NEW)

        resp = self.client.get(reverse("trust:home"))
        self.assertEqual(resp.context["reports_received_count"], 2)
        self.assertEqual(resp.context["reports_resolved_count"], 1)


class FraudReportModelTests(TestCase):
    def test_mark_status_resolved_notifies_the_reporter(self):
        reporter = User.objects.create_user(username="reporter2", password="p")
        staff = User.objects.create_user(username="staff", password="p", is_staff=True)
        report = FraudReport.objects.create(reporter=reporter, category=FraudReport.CATEGORY_SCAM)

        with patch("accounts.push.notify_user") as mocked_notify:
            report.mark_status(FraudReport.STATUS_RESOLVED, staff_user=staff, note="fake listing removed")

        report.refresh_from_db()
        self.assertEqual(report.status, FraudReport.STATUS_RESOLVED)
        self.assertEqual(report.resolved_by, staff)
        self.assertIsNotNone(report.resolved_at)
        self.assertEqual(report.resolution_note, "fake listing removed")
        mocked_notify.assert_called_once()
        self.assertEqual(mocked_notify.call_args.args[0], reporter)

    def test_mark_status_dismissed_does_not_notify(self):
        reporter = User.objects.create_user(username="reporter3", password="p")
        report = FraudReport.objects.create(reporter=reporter, category=FraudReport.CATEGORY_SPAM)

        with patch("accounts.push.notify_user") as mocked_notify:
            report.mark_status(FraudReport.STATUS_DISMISSED)

        mocked_notify.assert_not_called()

    def test_reference_code_format(self):
        report = FraudReport.objects.create(category=FraudReport.CATEGORY_OTHER)
        self.assertEqual(report.reference_code, f"R4Y-{report.pk:06d}")


class StaffNotificationTests(TestCase):
    """
    Regression coverage for a real gap: FraudReport creation notified
    nobody - reports only ever surfaced if a staff member remembered to
    check the Django admin. This is what actually backs the Trust
    Centre's "we investigate reports" promise.
    """

    def setUp(self):
        self.landlord = User.objects.create_user(username="landlord_x", password="p")
        self.room = make_room(self.landlord)

    def test_new_report_emails_the_safety_team(self):
        with patch("trust.signals.send_template_email") as mail:
            FraudReport.objects.create(category=FraudReport.CATEGORY_SCAM, room=self.room)

        mail.assert_called_once()
        kwargs = mail.call_args.kwargs
        self.assertEqual(kwargs["to_email"], "safety@rooms4you.co.za")
        self.assertNotIn("REPEAT", kwargs["subject"])

    def test_second_open_report_on_same_room_is_flagged_as_repeat(self):
        FraudReport.objects.create(category=FraudReport.CATEGORY_SCAM, room=self.room)

        with patch("trust.signals.send_template_email") as mail:
            FraudReport.objects.create(category=FraudReport.CATEGORY_FAKE_LISTING, room=self.room)

        kwargs = mail.call_args.kwargs
        self.assertIn("REPEAT", kwargs["subject"])
        self.assertTrue(kwargs["context"]["is_repeat_offender"])
        self.assertEqual(kwargs["context"]["related_count"], 1)

    def test_resolved_reports_do_not_count_toward_repeat_flag(self):
        first = FraudReport.objects.create(category=FraudReport.CATEGORY_SCAM, room=self.room)
        first.mark_status(FraudReport.STATUS_RESOLVED)

        with patch("trust.signals.send_template_email") as mail:
            FraudReport.objects.create(category=FraudReport.CATEGORY_FAKE_LISTING, room=self.room)

        kwargs = mail.call_args.kwargs
        self.assertFalse(kwargs["context"]["is_repeat_offender"])

    def test_email_failure_does_not_prevent_report_from_saving(self):
        with patch("trust.signals.send_template_email", side_effect=RuntimeError("smtp down")):
            report = FraudReport.objects.create(category=FraudReport.CATEGORY_SCAM, room=self.room)

        self.assertIsNotNone(report.pk)
        self.assertTrue(FraudReport.objects.filter(pk=report.pk).exists())

    def test_report_via_general_report_fraud_page_also_notifies_staff(self):
        with patch("trust.signals.send_template_email") as mail:
            self.client.post(
                reverse("trust:report_fraud"),
                {"category": FraudReport.CATEGORY_OTHER, "detail": "suspicious message"},
            )
        mail.assert_called_once()


class RelatedOpenReportsTests(TestCase):
    def setUp(self):
        self.landlord = User.objects.create_user(username="landlord_y", password="p")
        self.room = make_room(self.landlord)

    def test_unsaved_report_has_no_related_reports(self):
        report = FraudReport(category=FraudReport.CATEGORY_SCAM, room=self.room)
        self.assertFalse(report.is_repeat_offender)

    def test_report_with_no_room_or_user_has_no_related_reports(self):
        report = FraudReport.objects.create(category=FraudReport.CATEGORY_OTHER)
        self.assertFalse(report.is_repeat_offender)

    def test_matches_by_reported_user_across_different_rooms(self):
        other_room = make_room(self.landlord, title="R2")
        FraudReport.objects.create(category=FraudReport.CATEGORY_SCAM, reported_user=self.landlord, room=self.room)

        second = FraudReport.objects.create(
            category=FraudReport.CATEGORY_FAKE_LANDLORD, reported_user=self.landlord, room=other_room
        )
        self.assertTrue(second.is_repeat_offender)
