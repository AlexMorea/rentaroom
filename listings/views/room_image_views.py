import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from PIL import Image, UnidentifiedImageError

from accounts.utils import require_active_membership

from ..models import Room, RoomImage

logger = logging.getLogger(__name__)

# .jfif is plain JPEG - it's what Windows/Chrome save many web photos as.
ALLOWED_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".jfif", ".png", ".webp")
MAX_IMAGE_BYTES = 10 * 1024 * 1024


def is_valid_room_image(img) -> bool:
    """A real JPG/PNG/WebP photo under 10 MB. Shared by every photo upload
    (the Add Room form, the photo page and Manage Images), so a bad file
    is skipped rather than breaking the upload after the room is saved."""
    if not (img.name or "").lower().endswith(ALLOWED_IMAGE_EXTENSIONS):
        return False
    if img.size > MAX_IMAGE_BYTES:
        return False
    try:
        Image.open(img).verify()
    except (UnidentifiedImageError, OSError) as exc:
        logger.warning("Invalid image upload %s: %s", img.name, exc)
        return False
    except Exception as exc:  # noqa: BLE001 - Pillow also raises SyntaxError, DecompressionBombError, ...
        logger.warning("Unreadable image upload %s: %r", img.name, exc)
        return False
    finally:
        img.seek(0)
    return True


def skipped_images_message(skipped: int) -> str:
    return (
        f"{skipped} file{'s' if skipped != 1 else ''} couldn't be added. "
        "Please use JPG, PNG or WebP photos smaller than 10 MB."
    )


def store_room_images(room, uploads) -> tuple[int, int]:
    """
    Saves each valid photo on its own, returning (added, skipped). One bad
    file or one storage hiccup skips that photo only - previously a single
    failed upload on the photo pages raised, showed the landlord an error
    page and threw away every other photo in the batch.
    """
    added = skipped = 0
    for img in uploads:
        if not is_valid_room_image(img):
            skipped += 1
            continue
        try:
            RoomImage.objects.create(room=room, image=img)
        except Exception:  # noqa: BLE001 - e.g. Cloudinary timeout or the 10-photo limit
            logger.exception("Could not store photo %s for room %s", img.name, room.id)
            skipped += 1
            continue
        added += 1
    return added, skipped



from .helpers import is_landlord

MAX_IMAGES_PER_ROOM = 10

@login_required
@user_passes_test(is_landlord)
def upload_room_images(request, room_id):

    if not require_active_membership(request.user):
        return redirect("membership")

    room = get_object_or_404(
        Room,
        id=room_id,
        owner=request.user
    )

    if request.method == "POST":

        uploads = request.FILES.getlist("images")

        if not uploads:
            messages.error(request, "Please select images.")
            return redirect("upload_room_images", room.id)

        existing_count = room.images.count()

        remaining = max(0, 10 - existing_count)

        if remaining <= 0:
            messages.error(
                request,
                "Maximum 10 images reached."
            )
            return redirect("edit_room_images", pk=room.id)

        uploads = uploads[:remaining]

        uploaded_count, skipped = store_room_images(room, uploads)

        if skipped:
            messages.warning(request, skipped_images_message(skipped))

        if uploaded_count:
            messages.success(
                request,
                f"{uploaded_count} photo{'s' if uploaded_count != 1 else ''} added."
            )

        else:
            messages.error(
                request,
                "No photos were added."
            )

        if len(request.FILES.getlist("images")) > remaining:
            messages.warning(
                request,
                f"A listing can have up to 10 photos, so only {remaining} more could be added."
            )

        return redirect("edit_room_images", pk=room.id)

    return render(
        request,
        "listings/upload_images.html",
        {"room": room}
    )


@login_required
@require_POST
@user_passes_test(is_landlord)
def delete_room_image(request, image_id):

    image = get_object_or_404(
        RoomImage,
        id=image_id,
        room__owner=request.user
    )

    room_id = image.room.id

    with transaction.atomic():
        image.delete()

    messages.success(request, "Image deleted successfully.")

    return redirect("edit_room_images", pk=room_id)


@login_required
@user_passes_test(is_landlord)
def edit_room_images(request, pk):
    room = get_object_or_404(Room, pk=pk, owner=request.user)

    if request.method == "POST":
        # --- Delete first (frees up slots) ---
        delete_ids = request.POST.getlist("delete")
        deleted_count = 0
        if delete_ids:
            qs = RoomImage.objects.filter(room=room, id__in=delete_ids)
            deleted_count = qs.count()
            qs.delete()
            if deleted_count:
                messages.success(request, f"Deleted {deleted_count} image(s).")

        # --- Upload next (respect total max) ---
        current_count = RoomImage.objects.filter(room=room).count()
        remaining_slots = max(0, MAX_IMAGES_PER_ROOM - current_count)

        uploads = request.FILES.getlist("images")
        if uploads:
            if remaining_slots <= 0:
                messages.error(
                    request,
                    f"You already have {MAX_IMAGES_PER_ROOM} images. Delete some first to upload new ones.",
                )
            else:
                to_add = uploads[:remaining_slots]
                added, skipped = store_room_images(room, to_add)

                if added:
                    messages.success(
                        request,
                        f"Uploaded {added} image(s). ({RoomImage.objects.filter(room=room).count()}/{MAX_IMAGES_PER_ROOM})",
                    )
                if skipped:
                    messages.warning(request, skipped_images_message(skipped))

                if len(uploads) > remaining_slots:
                    messages.warning(
                        request,
                        f"Only {remaining_slots} image(s) were added (max {MAX_IMAGES_PER_ROOM} per room).",
                    )

        return redirect("edit_room_images", pk=pk)

    return render(
        request,
        "listings/edit_room_images.html",
        {"room": room, "img_count": room.images.count(), "max_images": 10},
    )


@login_required
@user_passes_test(is_landlord)
@require_POST
def reorder_room_image(request, image_id, direction):
    img = get_object_or_404(RoomImage, id=image_id, room__owner=request.user)
    room = img.room
    images = list(room.images.all())

    idx = images.index(img)

    if direction == "up" and idx > 0:
        images[idx], images[idx - 1] = images[idx - 1], images[idx]
    elif direction == "down" and idx < len(images) - 1:
        images[idx], images[idx + 1] = images[idx + 1], images[idx]

    for position, image_obj in enumerate(images):
        if image_obj.order != position:
            image_obj.order = position
            image_obj.save(update_fields=["order"])

    return redirect("edit_room_images", pk=room.id)

