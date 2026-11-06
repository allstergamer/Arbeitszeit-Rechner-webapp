def user_theme(request):
    if request.user.is_authenticated:
        profil = getattr(request.user, "profil", None)

        if profil:
            return {
                "user_theme": profil.theme
            }

    return {
        "user_theme": "Dunkel"
    }