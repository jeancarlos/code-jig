# SPDX-FileCopyrightText: 2026 Jean Souza
# SPDX-License-Identifier: Apache-2.0
import unittest

from calc import divide


class Divide(unittest.TestCase):
    def test_divides(self):
        self.assertEqual(divide(6, 3), 2)
