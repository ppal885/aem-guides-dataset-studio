import unittest

import blind50_score


class Blind50ScoreTests(unittest.TestCase):
    def test_self_test_passes(self) -> None:
        self.assertEqual(blind50_score.self_test(), 0)


if __name__ == "__main__":
    unittest.main()
