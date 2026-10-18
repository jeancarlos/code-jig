# SPDX-FileCopyrightText: 2026 Jean Souza
# SPDX-License-Identifier: Apache-2.0
import os
import sys


def grade(score):
    if score > 90:
        if score > 95:
            if score > 99:
                return "A+"
            return "A"
        return "A-"
    elif score > 80:
        return "B"
    return "C"
