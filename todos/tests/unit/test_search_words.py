from django.test import SimpleTestCase

from todos.views import search_words

# ギュウニュウ in normal katakana, written with code points so that no editor
# can change how its letters are stored.
GYUUNYUU = "ギュウニュウ"


class SearchWordsTests(SimpleTestCase):
    def test_search_words_adds_the_nfkc_form(self):
        cases = [
            ("ｍｉｌｋ", ["ｍｉｌｋ", "milk"]),
            ("ＭＩＬＫ", ["ＭＩＬＫ", "MILK"]),
            ("ｷﾞｭｳﾆｭｳ", ["ｷﾞｭｳﾆｭｳ", GYUUNYUU]),  # half-width katakana
            ("１２", ["１２", "12"]),
        ]
        for word, expected in cases:
            with self.subTest(word=word):
                self.assertEqual(search_words(word), expected)

    def test_search_words_once_when_nothing_changes(self):
        for word in ["milk", "牛乳", "café"]:
            with self.subTest(word=word):
                self.assertEqual(search_words(word), [word])
