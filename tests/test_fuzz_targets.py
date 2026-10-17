import unittest

from fuzz.targets import TARGETS

SAMPLES = [b"", b"\x00", b"\xff\xfe", b"[1, 2", b"{\"ids\": [\"a\"]}", b"<p>hi &amp; <b>there", b"a \xe2\x80\x94 b\n# c \xe2\x80\x9cq\xe2\x80\x9d",
           b"\x1e1\x00bad\x00s\x00b\x00d"]


class Targets(unittest.TestCase):
    def test_every_target_survives_the_samples(self):
        for target in TARGETS:
            for sample in SAMPLES:
                with self.subTest(target=target.__name__, sample=sample):
                    target(sample)


if __name__ == "__main__":
    unittest.main()
