def navigation(request):
    nav_items = [
        {"name": "Dashboard", "href": "/"},
        {"name": "Another page", "href": "/profile/"},
    ]

    return { "nav_items": nav_items }
