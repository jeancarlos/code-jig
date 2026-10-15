from users import get_user


def handler(request):
    return get_user(request["id"])
