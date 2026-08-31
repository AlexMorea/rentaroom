import base64
import os
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import PushSubscription
from .push import generate_ephemeral_vapid_keys, notify_user, send_web_push


class VapidKeyGenerationTests(TestCase):
    def test_generate_ephemeral_vapid_keys_returns_usable_pem_and_public_key(self):
        private_pem, public_b64url = generate_ephemeral_vapid_keys()

        self.assertIn("BEGIN PRIVATE KEY", private_pem)
        self.assertTrue(public_b64url)
        # Uncompressed P-256 point is 65 bytes -> ~87 base64url chars, no padding.
        self.assertNotIn("=", public_b64url)


class PushSubscribeEndpointTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tenant", password="p")

    def test_subscribe_creates_a_subscription(self):
        self.client.login(username="tenant", password="p")
        resp = self.client.post(
            reverse("push_subscribe"),
            data='{"endpoint":"https://fcm.googleapis.com/fake","keys":{"p256dh":"abc","auth":"def"}}',
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(PushSubscription.objects.count(), 1)
        sub = PushSubscription.objects.get()
        self.assertEqual(sub.user, self.user)
        self.assertEqual(sub.endpoint, "https://fcm.googleapis.com/fake")

    def test_subscribe_requires_login(self):
        resp = self.client.post(
            reverse("push_subscribe"),
            data='{"endpoint":"https://fcm.googleapis.com/fake","keys":{"p256dh":"a","auth":"b"}}',
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 302)  # redirected to login

    def test_subscribe_rejects_malformed_payload(self):
        self.client.login(username="tenant", password="p")
        resp = self.client.post(
            reverse("push_subscribe"),
            data='{"nope": true}',
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_unsubscribe_removes_the_matching_subscription(self):
        self.client.login(username="tenant", password="p")
        PushSubscription.objects.create(
            user=self.user, endpoint="https://fcm.googleapis.com/fake", p256dh="a", auth="b"
        )
        resp = self.client.post(
            reverse("push_unsubscribe"),
            data='{"endpoint":"https://fcm.googleapis.com/fake"}',
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(PushSubscription.objects.count(), 0)


class SendWebPushTests(TestCase):
    """
    Exercises the real pywebpush/py_vapid call path (network mocked, VAPID
    key parsing NOT mocked) - this is a regression test for a real bug caught
    during development: passing the raw PEM string straight to pywebpush
    instead of a parsed Vapid instance raised ValueError deep inside
    `cryptography` instead of the WebPushException send_web_push is built to
    handle.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="tenant", password="p")

        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

        priv = ec.generate_private_key(ec.SECP256R1())
        raw_pub = priv.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
        self.p256dh = base64.urlsafe_b64encode(raw_pub).rstrip(b"=").decode()
        self.auth = base64.urlsafe_b64encode(os.urandom(16)).rstrip(b"=").decode()

    def test_send_web_push_parses_vapid_key_without_raising(self):
        sub = PushSubscription.objects.create(
            user=self.user,
            endpoint="https://fcm.googleapis.com/fake/xyz",
            p256dh=self.p256dh,
            auth=self.auth,
        )

        # No network call is mocked - a fake endpoint 404s for real, which
        # is exactly the path that should be handled gracefully (dead
        # subscription cleaned up), not raise.
        result = send_web_push(sub, title="Hi", body="test", url="/")

        self.assertFalse(result)
        self.assertFalse(PushSubscription.objects.filter(pk=sub.pk).exists())

    def test_notify_user_sends_to_every_subscription(self):
        PushSubscription.objects.create(
            user=self.user, endpoint="https://fcm.googleapis.com/a", p256dh=self.p256dh, auth=self.auth
        )
        PushSubscription.objects.create(
            user=self.user, endpoint="https://fcm.googleapis.com/b", p256dh=self.p256dh, auth=self.auth
        )

        with patch("accounts.push.send_web_push", return_value=True) as mocked:
            sent = notify_user(self.user, title="Hi", body="test")

        self.assertEqual(sent, 2)
        self.assertEqual(mocked.call_count, 2)

    def test_notify_user_with_no_subscriptions_is_a_no_op(self):
        sent = notify_user(self.user, title="Hi", body="test")
        self.assertEqual(sent, 0)
