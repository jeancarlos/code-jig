# SPDX-FileCopyrightText: 2026 Jean Souza
# SPDX-License-Identifier: Apache-2.0
def average(values):
    return sum(values) / len(values)


def last_n(items, n):
    return items[len(items) - n - 1:]
