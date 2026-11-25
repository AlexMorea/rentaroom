"""
Regression tests for bugs that broke (or quietly hurt) signup, login,
posting a room, photos and tenant contact. Each test names the failure it
guards against.
"""
import io
from datetime import timedelta
from unittest.mock import patch

import cloudinary
from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from accounts.push import send_web_push
from listings.forms import RoomForm, UserRegisterForm
from listings.models import PhoneOTP, Profile, Room, RoomImage
from listings.utils import parse_phone
from listings.views.room_image_views import is_valid_room_image
from placements.models import Waitlist

STRONG_PASSWORD = "Blue7Taxi!Rain"


def signup_data(**extra):
    data = {
        "role": "tenant", "persona": "worker",
        "first_name": "Thandi", "last_name": "Mokoena", "email": "thandi@example.com",
        "country_code": "+27", "phone_number": "082 123 4567",
        "terms_accepted": "on", "password1": STRONG_PASSWORD, "password2": STRONG_PASSWORD,
    }
    data.update(extra)
    return data


def make_room(owner, **extra):
    data = {
        "title": "Neat room", "owner": owner, "description": "Clean room.", "price": 1500,
        "location": "Mamelodi East, Pretoria", "suburb": "Mamelodi East", "town": "Mamelodi",
        "city": "Pretoria", "full_address": "12 Example Street", "postal_code": "0122",
        "room_type": "Single Room", "contact_phone": "+27821234567",
    }
    data.update(extra)
    return Room.objects.create(**data)


def make_landlord(email="landlord@example.com"):
    user = User.objects.create_user(email, email, STRONG_PASSWORD, first_name="Sipho")
    Profile.objects.filter(user=user).update(
        role="landlord", phone_number="+27821234567", is_email_verified=True, is_phone_verified=True,
    )
    return User.objects.get(pk=user.pk)


def png_upload(name="room.png"):
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(buf, format="PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


class SignupRoleSelectTests(TestCase):
    """The role <select> is hidden behind the role cards; rendered with
    `required`, the browser refused to submit with no visible message."""

    def setUp(self):
        cache.clear()

    def test_hidden_role_select_is_not_browser_required(self):
        html = str(UserRegisterForm()["role"])
        self.assertNotIn("required", html)

    def test_page_asks_for_a_role_next_to_the_cards(self):
        resp = self.client.get(reverse("register"))
        self.assertContains(resp, 'id="roleClientError"')

    def test_server_still_rejects_a_missing_role(self):
        resp = self.client.post(reverse("register"), signup_data(role=""))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(User.objects.filter(email="thandi@example.com").exists())


class PhoneValidationTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_common_ways_of_typing_a_number(self):
        for raw in ("082 123 4567", "0821234567", "+27 82 123 4567", "27821234567",
                    "0027 82 123 4567", "+27 (0)82 123 4567", "082-123-4567", "821234567"):
            self.assertEqual(parse_phone(raw), "+27821234567", raw)

    def test_numbers_that_cannot_be_dialled_are_rejected(self):
        for raw in ("082 123 456", "0821234567 / 0731234567", "abc", "", "08212345678"):
            self.assertIsNone(parse_phone(raw), raw)

    def test_two_numbers_in_one_box_is_a_form_error_not_a_crash(self):
        # 22 characters once normalized - over Profile.phone_number's
        # max_length, which made the save fail on Postgres.
        resp = self.client.post(reverse("register"), signup_data(phone_number="0821234567 / 0731234567"))
        self.assertContains(resp, "Please enter a valid South African number")
        self.assertFalse(User.objects.filter(email="thandi@example.com").exists())

    def test_valid_number_is_stored_normalized(self):
        self.client.post(reverse("register"), signup_data(phone_number="+27 (0)82 123 4567"))
        profile = Profile.objects.get(user__email="thandi@example.com")
        self.assertEqual(profile.phone_number, "+27821234567")

    def test_room_contact_number_must_be_diallable(self):
        landlord = make_landlord()
        form = RoomForm(data={
            "title": "Room", "description": "d", "price": "1500", "suburb": "S", "town": "T",
            "city": "C", "province": "Gauteng", "location": "S, C", "full_address": "12 Street",
            "postal_code": "0122", "room_type": "Single Room", "contact_phone": "082 123 456",
            "total_units": "1", "available_units": "1", "availability_status": "now",
        }, user=landlord)
        self.assertFalse(form.is_valid())
        self.assertIn("contact_phone", form.errors)


class SignupAccountTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_email_still_held_as_an_old_username_can_sign_up(self):
        # Someone changed their email; their old address is still their username.
        User.objects.create_user("thandi@example.com", "new-address@example.com", "x")

        resp = self.client.post(reverse("register"), signup_data())

        self.assertRedirects(resp, reverse("verify_account"), fetch_redirect_response=False)
        user = User.objects.get(email="thandi@example.com")
        self.assertNotEqual(user.username, "thandi@example.com")

    @override_settings(AUTH_PASSWORD_VALIDATORS=[{
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 20},
    }])
    def test_password_problems_show_on_the_password_field_alongside_others(self):
        form = UserRegisterForm(data=signup_data(persona=""))
        self.assertFalse(form.is_valid())
        self.assertIn("password1", form.errors)
        self.assertIn("persona", form.errors)  # the rest of clean() still ran


class LoginLockoutTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_locked_out_network_gets_a_page_not_a_redirect_loop(self):
        cache.set("login_attempts:127.0.0.1", 999, 900)

        self.assertEqual(self.client.get(reverse("login")).status_code, 200)

        resp = self.client.post(reverse("login"), {"email": "a@example.com", "password": "x"})
        self.assertEqual(resp.status_code, 429)
        self.assertContains(resp, "Too many login attempts", status_code=429)


class UnverifiedLoginTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("late@example.com", "late@example.com", STRONG_PASSWORD)

    def test_a_fresh_code_is_emailed_when_the_old_one_expired(self):
        old = PhoneOTP.objects.create(user=self.user, phone_number="email_verification", otp="111111")
        PhoneOTP.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=1))

        resp = self.client.post(reverse("login"), {"email": "late@example.com", "password": STRONG_PASSWORD})

        self.assertRedirects(resp, reverse("verify_account"), fetch_redirect_response=False)
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(PhoneOTP.objects.filter(user=self.user, created_at__gte=timezone.now() - timedelta(minutes=1)).exists())

    def test_no_extra_email_while_a_code_is_still_live(self):
        PhoneOTP.objects.create(user=self.user, phone_number="email_verification", otp="111111")

        self.client.post(reverse("login"), {"email": "late@example.com", "password": STRONG_PASSWORD})

        self.assertEqual(len(mail.outbox), 0)


class OtpInputTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("new@example.com", "new@example.com", STRONG_PASSWORD)
        session = self.client.session
        session["pending_user_id"] = self.user.id
        session.save()

    def _verify(self, typed):
        PhoneOTP.objects.create(user=self.user, phone_number="email_verification", otp="123456")
        return self.client.post(reverse("verify_account"), {"otp": typed})

    def test_pasted_code_with_spaces_is_accepted(self):
        resp = self._verify(" 123 456 ")
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Profile.objects.get(user=self.user).is_phone_verified)

    def test_other_keyboard_digits_are_accepted_not_a_500(self):
        resp = self._verify("１２３４５６")  # full-width digits
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Profile.objects.get(user=self.user).is_phone_verified)


class SignupKeepsTheRoomTests(TestCase):
    """A tenant who taps "Create account" on a listing should land back on
    that listing after entering their code, not on the generic room list."""

    def setUp(self):
        cache.clear()

    def _signup_and_verify(self, next_url):
        self.client.post(reverse("register") + f"?next={next_url}", signup_data())
        otp = PhoneOTP.objects.get(user__email="thandi@example.com").otp
        return self.client.post(reverse("verify_account"), {"otp": otp})

    def test_lands_back_on_the_room(self):
        resp = self._signup_and_verify("/rooms/5/")
        self.assertRedirects(resp, "/rooms/5/", fetch_redirect_response=False)

    def test_offsite_next_is_ignored(self):
        resp = self._signup_and_verify("https://evil.example.com/")
        self.assertRedirects(resp, reverse("room_list"), fetch_redirect_response=False)

    def test_room_page_create_account_link_carries_the_room(self):
        room = make_room(make_landlord())
        resp = self.client.get(reverse("room_detail", args=[room.id]))
        self.assertContains(resp, f'{reverse("register")}?next={reverse("room_detail", args=[room.id])}')


class PostingSurvivesEmailOutageTests(TestCase):
    def setUp(self):
        cache.clear()
        self.landlord = make_landlord()
        self.client.force_login(self.landlord)

    def test_room_is_published_even_if_the_live_email_fails(self):
        # execute=True: in production on_commit runs inside the view (no
        # surrounding transaction), so the email failure hit the landlord.
        with patch("listings.views.room_views.send_template_email", side_effect=RuntimeError("brevo down")) as send, \
                self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post(reverse("create_room"), {
                "title": "Neat room", "description": "Clean room.", "price": "1600", "suburb": "Mabopane",
                "town": "Mabopane", "city": "Pretoria", "province": "Gauteng", "location": "Mabopane, Pretoria",
                "full_address": "12 Example Street", "postal_code": "0190", "room_type": "Single Room",
                "contact_phone": "0821234567", "total_units": "1", "available_units": "1",
                "availability_status": "now", "is_available": "on",
            })
        send.assert_called_once()
        room = Room.objects.get(owner=self.landlord)
        self.assertRedirects(resp, reverse("upload_room_images", args=[room.id]), fetch_redirect_response=False)

    def _full_room_with_waitlist(self):
        room = make_room(self.landlord, availability_status="from", available_units=0,
                         available_from=timezone.localdate() + timedelta(days=14))
        tenant = User.objects.create_user("waiting@example.com", "waiting@example.com", "x")
        Waitlist.objects.create(tenant=tenant, room=room, landlord=self.landlord)
        return room

    def test_marking_a_full_room_available_survives_waitlist_email_failure(self):
        room = self._full_room_with_waitlist()
        with patch("placements.models.send_template_email", side_effect=RuntimeError("brevo down")):
            resp = self.client.post(reverse("toggle_room_vacancy", args=[room.id]))
        self.assertEqual(resp.status_code, 302)
        room.refresh_from_db()
        self.assertGreater(room.available_units, 0)

    def test_edit_is_not_rolled_back_by_waitlist_email_failure(self):
        room = self._full_room_with_waitlist()
        with patch("placements.models.send_template_email", side_effect=RuntimeError("brevo down")):
            resp = self.client.post(reverse("edit_room", args=[room.id]), {
                "title": "Neat room, now free", "description": "Clean room.", "price": "1500",
                "suburb": "Mamelodi East", "town": "Mamelodi", "city": "Pretoria", "province": "Gauteng",
                "location": "Mamelodi East, Pretoria", "full_address": "12 Example Street", "postal_code": "0122",
                "room_type": "Single Room", "contact_phone": "0821234567", "total_units": "1",
                "available_units": "1", "availability_status": "now", "is_available": "on",
            })
        self.assertRedirects(resp, reverse("dashboard"), fetch_redirect_response=False)
        room.refresh_from_db()
        self.assertEqual(room.title, "Neat room, now free")


class PhotoTests(TestCase):
    def setUp(self):
        cache.clear()
        self.landlord = make_landlord()
        self.room = make_room(self.landlord)

    def test_reorder_buttons_pass_csrf(self):
        # Rendering photo URLs needs a Cloudinary cloud name; CI has none.
        previous = cloudinary.config().cloud_name
        cloudinary.config(cloud_name="test-cloud")
        self.addCleanup(cloudinary.config, cloud_name=previous)

        first = RoomImage.objects.create(room=self.room, image="photo_a", order=0)
        second = RoomImage.objects.create(room=self.room, image="photo_b", order=1)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.landlord)

        page = client.get(reverse("edit_room_images", args=[self.room.id])).content.decode()
        form_start = page.index(f'id="imReorderForm{second.id}up"')
        self.assertIn("csrfmiddlewaretoken", page[form_start:page.index("</form>", form_start)])

        token = client.cookies["csrftoken"].value
        resp = client.post(reverse("reorder_room_image", args=[second.id, "up"]), {"csrfmiddlewaretoken": token})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(list(self.room.images.values_list("id", flat=True)), [second.id, first.id])

    def test_one_failed_upload_does_not_lose_the_rest(self):
        self.client.force_login(self.landlord)
        real_create = RoomImage.objects.create
        calls = {"n": 0}

        def flaky_create(**kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("cloudinary timeout")
            return real_create(room=kwargs["room"], image="stored_photo")

        with patch.object(RoomImage.objects, "create", side_effect=flaky_create):
            resp = self.client.post(
                reverse("upload_room_images", args=[self.room.id]),
                {"images": [png_upload("a.png"), png_upload("b.png")]},
            )
        self.assertRedirects(resp, reverse("edit_room_images", args=[self.room.id]), fetch_redirect_response=False)
        self.assertEqual(self.room.images.count(), 1)

    def test_manage_images_skips_a_non_image_instead_of_erroring(self):
        self.client.force_login(self.landlord)
        bad = SimpleUploadedFile("lease.pdf", b"%PDF-1.4 not an image", content_type="application/pdf")
        resp = self.client.post(reverse("edit_room_images", args=[self.room.id]), {"images": [bad]}, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "couldn&#x27;t be added")
        self.assertEqual(self.room.images.count(), 0)

    def test_unreadable_file_is_rejected_not_a_500(self):
        with patch("listings.views.room_image_views.Image.open", side_effect=SyntaxError("broken PNG")):
            self.assertFalse(is_valid_room_image(png_upload()))

    def test_jfif_photo_is_accepted(self):
        buf = io.BytesIO()
        Image.new("RGB", (8, 8), "white").save(buf, format="JPEG")
        self.assertTrue(is_valid_room_image(SimpleUploadedFile("photo.jfif", buf.getvalue())))


class ContactTests(TestCase):
    def setUp(self):
        cache.clear()
        self.landlord = make_landlord()
        self.room = make_room(self.landlord, contact_phone="0821234567")
        self.tenant = User.objects.create_user("tenant@example.com", "tenant@example.com", "x")
        self.client.force_login(self.tenant)

    def test_tapping_whatsapp_again_still_opens_whatsapp(self):
        url = reverse("track_contact", args=[self.room.id, "whatsapp"])
        first = self.client.get(url)
        second = self.client.get(url)
        for resp in (first, second):
            self.assertEqual(resp.status_code, 200)
            # Older listings stored "082..." - wa.me needs the 27 prefix.
            self.assertContains(resp, "https://wa.me/27821234567")

    def test_landlord_is_emailed_once_even_if_tenant_taps_twice(self):
        url = reverse("track_contact", args=[self.room.id, "email"])
        self.client.get(url)
        self.client.get(url)
        self.assertEqual(len(mail.outbox), 1)

    def test_inquiry_email_failure_still_opens_the_mail_link(self):
        with patch("listings.views.review_contact_views.send_template_email", side_effect=RuntimeError("down")):
            resp = self.client.get(reverse("track_contact", args=[self.room.id, "email"]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "mailto:")


class BestEffortNotificationTests(TestCase):
    def test_web_push_network_error_never_raises(self):
        from accounts.models import PushSubscription

        user = User.objects.create_user("p@example.com", "p@example.com", "x")
        sub = PushSubscription.objects.create(user=user, endpoint="https://push.example/1", p256dh="k", auth="a")
        with patch("pywebpush.webpush", side_effect=ConnectionError("unreachable")):
            self.assertFalse(send_web_push(sub, title="t", body="b"))


class GoogleAccountRecoveryTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_google_only_account_can_reset_its_password(self):
        user = User.objects.create(username="g@example.com", email="g@example.com")
        user.set_unusable_password()
        user.save()

        self.client.post(reverse("password_reset"), {"email": "g@example.com"})

        self.assertEqual(len(mail.outbox), 1)

    @override_settings(GOOGLE_OAUTH_CLIENT_ID="test-client")
    def test_deactivated_unfinished_account_is_not_let_back_in(self):
        user = User.objects.create(username="gone@example.com", email="gone@example.com", is_active=False)
        claims = {"email": "gone@example.com"}
        with patch("listings.views.auth_views._verify_google_credential", return_value=claims):
            resp = self.client.post(reverse("google_auth"), {"credential": "x"})
        self.assertRedirects(resp, reverse("login"), fetch_redirect_response=False)
        self.assertNotIn("google_pending_user_id", self.client.session)
        self.assertFalse(User.objects.get(pk=user.pk).is_active)

    @override_settings(GOOGLE_OAUTH_CLIENT_ID="test-client")
    def test_google_signup_with_an_email_held_as_an_old_username(self):
        User.objects.create_user("taken@example.com", "moved@example.com", "x")
        claims = {"email": "taken@example.com", "given_name": "Lerato"}
        with patch("listings.views.auth_views._verify_google_credential", return_value=claims):
            resp = self.client.post(reverse("google_auth"), {"credential": "x"})
        self.assertRedirects(resp, reverse("google_complete_profile"), fetch_redirect_response=False)
        self.assertTrue(User.objects.filter(email="taken@example.com").exists())


class ChangePhoneTests(TestCase):
    def test_email_outage_is_a_message_not_a_500(self):
        user = make_landlord()
        self.client.force_login(user)
        with patch("listings.views.auth_views.send_otp_email", side_effect=RuntimeError("down")):
            resp = self.client.post(reverse("change_phone"), {"phone_number": "0731234567", "country_code": "+27"})
        self.assertRedirects(resp, reverse("change_phone"), fetch_redirect_response=False)
