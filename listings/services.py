from django.db.models import Count
from .models import RoomStat


def stats_summary():
    return {
        "total_views": RoomStat.objects.filter(stat_type="view").count(),
        "total_contacts": RoomStat.objects.filter(
            stat_type__startswith="contact"
        ).count(),
        "total_success": RoomStat.objects.filter(stat_type="success").count(),
        "city_demand": RoomStat.objects.filter(stat_type="view")
        .values("room__location")
        .annotate(count=Count("id"))
        .order_by("-count"),
    }
