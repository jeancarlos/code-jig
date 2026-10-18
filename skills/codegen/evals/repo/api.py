# SPDX-FileCopyrightText: 2026 Jean Souza
# SPDX-License-Identifier: Apache-2.0
from users import get_user


def handler(request):
    return get_user(request["id"])
