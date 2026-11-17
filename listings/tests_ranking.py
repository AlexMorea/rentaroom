from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from listings.models import Favorite, Review, Room, RoomStat


def make_room(owner, title="R1", price=1000, **kwargs):
    data = {
        "title": title,
        "owner": owner,
        "description": "desc",
        "price": price,
        "location": "Loc",
        "suburb": "S",
        "town": "T",
        "city": "C",
        "full_address": "Addr",
        "postal_code": "0000",
        "room_type": Room.ROOM_TYPES[0][0],
        "contact_phone": "0123456",
        "total_units": 1,
        "available_units": 1,
        "availability_status": "now",
        "is_available": True,
    }
    data.update(kwargs)
    return Room.objects.create(**data)


class RankingTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username="u", password="p")
        cache.clear()
        # These tests check exact engagement arithmetic; the new-listing
        # head start is covered separately in ScoringRunsAndRanksTests.
        boost_off = mock.patch("listings.management.commands.compute_scores.NEW_LISTING_BOOST_POINTS", 0)
        boost_off.start()
        self.addCleanup(boost_off.stop)

    def test_backfill_hits_and_compute_scores(self):
        r1 = make_room(self.user, title="A", price=100)
        r2 = make_room(self.user, title="B", price=200)

        # create historical view stats
        for _ in range(5):
            RoomStat.objects.create(room=r1, stat_type="view")
        for _ in range(2):
            RoomStat.objects.create(room=r2, stat_type="view")

        # contacts and favorites
        for _ in range(1):
            RoomStat.objects.create(room=r1, stat_type="contact_email")
        Favorite.objects.create(user=self.user, room=r1)

        # backfill hits (dry-run first)
        call_command("backfill_hits")

        # apply backfill
        call_command("backfill_hits", "--force")

        r1.refresh_from_db()
        r2.refresh_from_db()

        # hits should equal view counts (composite=false default)
        self.assertGreaterEqual(r1.hits, 5)
        self.assertGreaterEqual(r2.hits, 2)

        # compute scores (apply)
        call_command("compute_scores", "--force")

        r1.refresh_from_db()
        r2.refresh_from_db()

        self.assertTrue(r1.score >= r2.score)

    def test_score_weights_review_quality_not_just_count(self):
        # Same room shape, same number of reviews - only the ratings differ.
        # Good reviews should outscore bad ones, not tie (regression for a
        # bug where compute_scores counted reviews without looking at rating).
        r_good = make_room(self.user, title="Good", price=100)
        r_bad = make_room(self.user, title="Bad", price=100)

        reviewers = [
            User.objects.create_user(username=f"reviewer{i}", password="p")
            for i in range(3)
        ]

        for reviewer in reviewers:
            Review.objects.create(room=r_good, user=reviewer, rating=5)
            Review.objects.create(room=r_bad, user=reviewer, rating=1)

        call_command("compute_scores", "--force")

        r_good.refresh_from_db()
        r_bad.refresh_from_db()

        self.assertGreater(r_good.score, r_bad.score)

    def test_score_never_goes_negative(self):
        # score is a PositiveIntegerField - a room with only bad reviews and
        # no other engagement must clamp to 0, not raise or store negative.
        room = make_room(self.user, title="OnlyBadReviews", price=100)

        for i in range(3):
            reviewer = User.objects.create_user(username=f"badreviewer{i}", password="p")
            Review.objects.create(room=room, user=reviewer, rating=1)

        call_command("compute_scores", "--force")

        room.refresh_from_db()
        self.assertEqual(room.score, 0)

    @override_settings(POPULAR_SCORE_THRESHOLD=1, USE_MATERIALIZED_SCORE=True)
    def test_room_list_popular_and_ordering(self):
        # create rooms with different scores
        r1 = make_room(self.user, title="Top")
        r2 = make_room(self.user, title="Low")

        # set scores directly
        Room.objects.filter(pk=r1.pk).update(score=500)
        Room.objects.filter(pk=r2.pk).update(score=1)

        # clear cache to ensure fresh computation
        cache.clear()

        c = Client()
        resp = c.get(reverse("room_list"))

        # view context contains popular_ids
        popular_ids = resp.context.get("popular_ids")
        self.assertIsNotNone(popular_ids)
        assert popular_ids is not None  # narrows for the type checker; assertIsNotNone above already fails the test otherwise
        self.assertIn(r1.id, popular_ids)
        self.assertNotIn(r2.id, popular_ids)

        # ordering: first room should be r1 (highest score)
        rooms = resp.context.get("rooms")
        assert rooms is not None  # narrows for the type checker; template always provides "rooms" in context
        self.assertTrue(len(rooms) > 0)
        self.assertEqual(rooms[0].id, r1.id)


class ComputeScoresAggregationTests(TestCase):
    """
    Regression coverage for a real bug caught during development: annotating
    Count() over multiple different reverse relations (roomstat AND
    favorited_by AND reviews) in one query silently inflates every count by
    the other relations' row counts, via ordinary SQL JOIN fan-out - a room
    with 1 real favorite but 4 RoomStat rows read back favorites_count=4.
    Verified against raw SQL during development; compute_scores.py now
    isolates the Sum(reviews__rating) query (Sum can't safely use
    distinct=True - it would collapse duplicate rating *values*, not rows)
    and uses distinct=True on every Count sharing a query with another
    relation.
    """

    def setUp(self):
        self.owner = User.objects.create_user(username="owner", password="p")
        # These tests check exact engagement arithmetic; the new-listing
        # head start is covered separately in ScoringRunsAndRanksTests.
        boost_off = mock.patch("listings.management.commands.compute_scores.NEW_LISTING_BOOST_POINTS", 0)
        boost_off.start()
        self.addCleanup(boost_off.stop)

    def test_favorites_not_inflated_by_unrelated_roomstat_rows(self):
        room = make_room(self.owner, title="Fanout")
        tenant = User.objects.create_user(username="tenant", password="p")

        # Multiple RoomStat rows (a different relation) - these should
        # never affect the favorites count computed in the same query.
        for _ in range(5):
            RoomStat.objects.create(room=room, stat_type="view")
        RoomStat.objects.create(room=room, stat_type="contact_email")
        Favorite.objects.create(user=tenant, room=room)

        call_command("compute_scores", "--force")
        room.refresh_from_db()

        # +8 (1 contact) + 5 (5 views * 1) + 2 (1 favorite * 2) = 15.
        # Would be 15 + (4 extra phantom favorites * 2) = 23 if favorites
        # fanned out against the 6 roomstat rows.
        self.assertEqual(room.score, 15)

    def test_review_sum_not_inflated_by_other_relations(self):
        room = make_room(self.owner, title="ReviewFanout")
        reviewer = User.objects.create_user(username="reviewer", password="p")
        Review.objects.create(room=room, user=reviewer, rating=5)

        for _ in range(3):
            RoomStat.objects.create(room=room, stat_type="view")

        call_command("compute_scores", "--force")
        room.refresh_from_db()

        # review_quality = 5 - (1 * 3) = 2, weighted *3 = 6; +3 views = 9.
        # A fanned-out Sum would multiply the rating sum by the roomstat
        # row count instead of leaving it at the true value of 5.
        self.assertEqual(room.score, 9)

    def test_stale_listing_is_penalized(self):
        fresh = make_room(self.owner, title="Fresh")
        stale = make_room(self.owner, title="Stale")

        tenant = User.objects.create_user(username="tenant2", password="p")
        for room in (fresh, stale):
            Favorite.objects.create(user=tenant, room=room)
            RoomStat.objects.create(room=room, stat_type="contact_email")

        with override_settings(LISTING_STALE_DAYS=14):
            Room.objects.filter(pk=stale.pk).update(
                last_confirmed_at=timezone.now() - timezone.timedelta(days=20)
            )
            call_command("compute_scores", "--force")

        fresh.refresh_from_db()
        stale.refresh_from_db()

        self.assertLess(stale.score, fresh.score)

    def test_unavailable_room_is_never_penalized_as_stale(self):
        # An occupied room that hasn't been "confirmed" in ages isn't
        # stale - it's correctly not-available. Score should reflect
        # engagement only, no staleness penalty applied.
        room = make_room(self.owner, title="Occupied", is_available=False, available_units=0)
        Room.objects.filter(pk=room.pk).update(
            last_confirmed_at=timezone.now() - timezone.timedelta(days=100)
        )
        RoomStat.objects.create(room=room, stat_type="contact_email")

        call_command("compute_scores", "--force")
        room.refresh_from_db()

        self.assertEqual(room.score, 8)  # just the one contact, no penalty


class ScoringRunsAndRanksTests(TestCase):
    """The ranking pipeline end to end: engagement -> compute_scores ->
    best-match order, plus the in-process scheduler that runs it."""

    def make_room(self, owner, title, days_old=30):
        from datetime import timedelta

        from django.utils import timezone

        room = Room.objects.create(
            owner=owner, title=title, description="d", location="Soweto", suburb="Orlando",
            town="Soweto", city="Johannesburg", full_address="1 St", postal_code="1804",
            room_type="Backroom", contact_phone="0821234567", price=1500,
        )
        Room.objects.filter(pk=room.pk).update(created_at=timezone.now() - timedelta(days=days_old))
        return Room.objects.get(pk=room.pk)

    def setUp(self):
        from django.contrib.auth.models import User

        self.owner = User.objects.create_user("owner-rank@example.com", password="x")
        self.tenant = User.objects.create_user("tenant-rank@example.com", password="x")

    def test_contacted_room_outranks_ignored_one(self):
        from django.core.management import call_command

        from listings.models import RoomStat

        quiet = self.make_room(self.owner, "Quiet room")
        wanted = self.make_room(self.owner, "Wanted room")
        RoomStat.objects.create(room=wanted, user=self.tenant, stat_type="contact_whatsapp")
        Room.objects.filter(pk=wanted.pk).update(hits=5)

        call_command("compute_scores", "--force", verbosity=0)

        quiet.refresh_from_db()
        wanted.refresh_from_db()
        self.assertGreater(wanted.score, quiet.score)
        ordered = list(Room.objects.filter(is_available=True).order_by("-score", "-created_at"))
        self.assertEqual(ordered[0].pk, wanted.pk)

    def test_new_listing_gets_a_fading_head_start(self):
        from django.core.management import call_command

        brand_new = self.make_room(self.owner, "Brand new", days_old=0)
        week_old = self.make_room(self.owner, "Week old", days_old=7)
        old = self.make_room(self.owner, "Old", days_old=30)

        call_command("compute_scores", "--force", verbosity=0)
        for r in (brand_new, week_old, old):
            r.refresh_from_db()

        self.assertGreater(brand_new.score, week_old.score)
        self.assertGreater(week_old.score, old.score)
        self.assertEqual(old.score, 0)

    def test_scheduler_runs_due_jobs_once_per_period(self):
        from unittest import mock

        from django.core.cache import cache

        from listings import scheduler

        cache.delete_many([key for key, *_ in scheduler.JOBS])
        with mock.patch("listings.scheduler.threading.Thread") as thread:
            scheduler.run_due_jobs()
            scheduler.run_due_jobs()
        commands = [c.kwargs["args"][0] for c in thread.call_args_list]
        self.assertEqual(sorted(commands), ["compute_response_stats", "compute_scores"])

    def test_middleware_is_off_in_tests_and_never_breaks_requests(self):
        from unittest import mock

        from django.test import override_settings

        with override_settings(RUN_SCHEDULED_JOBS_IN_PROCESS=True), \
             mock.patch("listings.scheduler.run_due_jobs", side_effect=RuntimeError("cache down")):
            resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
