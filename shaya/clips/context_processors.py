def shaya(request):
    data_saver = request.session.get("data_saver", True)
    if request.user.is_authenticated and hasattr(request.user, "profile"):
        data_saver = request.user.profile.data_saver
    return {"data_saver": data_saver}
