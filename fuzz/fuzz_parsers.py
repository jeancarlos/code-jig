# SPDX-FileCopyrightText: 2026 Jean Souza
# SPDX-License-Identifier: Apache-2.0
import sys

import atheris

with atheris.instrument_imports():
    from fuzz.targets import TARGETS


def one_input(data: bytes) -> None:
    if not data:
        return
    TARGETS[data[0] % len(TARGETS)](data[1:])


atheris.Setup(sys.argv, one_input)
atheris.Fuzz()
