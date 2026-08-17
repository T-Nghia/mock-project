import unittest

from app.utils.text_chunking import (
    ChunkData,
    chunk_blocks,
    chunk_text,
    chunk_text_by_tokens,
    count_local_tokens,
)
from app.utils.text_extract import ExtractedBlock


class ChunkTextTestCase(unittest.TestCase):
    def test_semantic_chunks_carry_heading_paths(self):
        blocks = [
            ExtractedBlock("heading", "5. Versions", 1),
            ExtractedBlock("heading", "5.1 Document versions", 2),
            ExtractedBlock("paragraph", "The Pro plan keeps 50 versions."),
        ]

        result = chunk_blocks(blocks, target_tokens=20, max_tokens=30, overlap_tokens=5)

        self.assertIsInstance(result[0], ChunkData)
        self.assertEqual(result[0].heading_path, ["5. Versions", "5.1 Document versions"])
        self.assertIn("The Pro plan", result[0].content)
    def test_semantic_chunks_keep_heading_context_and_do_not_mix_sections(self):
        blocks = [
            ExtractedBlock("heading", "5. Versions", 1),
            ExtractedBlock("paragraph", "The Pro plan keeps 50 versions."),
            ExtractedBlock("heading", "6. Sharing", 1),
            ExtractedBlock("paragraph", "Restricted documents require login."),
        ]

        result = chunk_blocks(blocks, target_tokens=20, max_tokens=30, overlap_tokens=5)

        self.assertIn("5. Versions", result[0].content)
        self.assertIn("The Pro plan", result[0].content)
        self.assertIn("6. Sharing", result[1].content)
        self.assertIn("Restricted documents", result[1].content)
        self.assertNotIn("Restricted documents", result[0].content)

    def test_local_token_counter_handles_words_and_punctuation(self):
        self.assertEqual(count_local_tokens("Hello, world!"), 4)
        self.assertEqual(count_local_tokens("  \n\t"), 0)

    def test_token_chunks_pack_words_with_overlap(self):
        result = chunk_text_by_tokens(
            "one two three four five six seven eight nine",
            max_tokens=4,
            overlap_tokens=1,
        )
        self.assertEqual(
            result,
            ["one two three four", "four five six seven", "seven eight nine"],
        )

    def test_token_chunk_validation_and_empty_input(self):
        self.assertEqual(chunk_text_by_tokens("  \n\t"), [])
        for max_tokens, overlap_tokens in ((0, 0), (-1, 0), (4, -1), (4, 4)):
            with self.subTest(max_tokens=max_tokens, overlap_tokens=overlap_tokens):
                with self.assertRaises(ValueError):
                    chunk_text_by_tokens(
                        "some text",
                        max_tokens=max_tokens,
                        overlap_tokens=overlap_tokens,
                    )

    def test_rejects_invalid_size_and_overlap(self):
        cases = (
            {"max_chars": 0, "overlap_chars": 0},
            {"max_chars": -1, "overlap_chars": 0},
            {"max_chars": 10, "overlap_chars": -1},
            {"max_chars": 10, "overlap_chars": 10},
            {"max_chars": 10, "overlap_chars": 11},
        )
        for options in cases:
            with self.subTest(options=options):
                with self.assertRaises(ValueError):
                    chunk_text("Noi dung", **options)

    def test_empty_input_returns_empty_list(self):
        self.assertEqual(chunk_text("  \n\n "), [])

    def test_short_text_preserves_blank_line_boundaries(self):
        result = chunk_text(
            "Doan mot.\n\nDoan hai.",
            max_chars=40,
            overlap_chars=0,
        )

        self.assertEqual(result, ["Doan mot.\n\nDoan hai."])

    def test_packs_paragraphs_without_exceeding_limit(self):
        result = chunk_text(
            "AAAAA\n\nBBBBB\n\nCCCCC",
            max_chars=12,
            overlap_chars=0,
        )

        self.assertEqual(result, ["AAAAA\n\nBBBBB", "CCCCC"])

    def test_oversized_paragraph_splits_and_packs_complete_sentences(self):
        result = chunk_text(
            "Mot hai. Ba bon. Nam sau.",
            max_chars=17,
            overlap_chars=0,
        )

        self.assertEqual(result, ["Mot hai. Ba bon.", "Nam sau."])

    def test_oversized_sentence_splits_on_words(self):
        result = chunk_text(
            "alpha beta gamma delta",
            max_chars=11,
            overlap_chars=0,
        )

        self.assertEqual(result, ["alpha beta", "gamma delta"])

    def test_single_oversized_word_is_hard_sliced(self):
        result = chunk_text(
            "abcdefghijk",
            max_chars=5,
            overlap_chars=0,
        )

        self.assertEqual(result, ["abcde", "fghij", "k"])
        self.assertTrue(all(len(chunk) <= 5 for chunk in result))

    def test_long_table_splits_by_row_and_repeats_marker(self):
        text = (
            "[TABLE 1]\n"
            "Mon: Python; Diem: 8\n"
            "Mon: Database; Diem: 9\n"
            "Mon: AI; Diem: 10"
        )

        result = chunk_text(text, max_chars=40, overlap_chars=0)

        self.assertEqual(
            result,
            [
                "[TABLE 1]\nMon: Python; Diem: 8",
                "[TABLE 1]\nMon: Database; Diem: 9",
                "[TABLE 1]\nMon: AI; Diem: 10",
            ],
        )
        self.assertTrue(all(chunk.startswith("[TABLE 1]\n") for chunk in result))
        self.assertTrue(all(len(chunk) <= 40 for chunk in result))

    def test_table_rows_are_grouped_when_they_fit(self):
        text = "[TABLE 2]\nA: 1\nB: 2\nC: 3"

        result = chunk_text(text, max_chars=20, overlap_chars=0)

        self.assertEqual(result, ["[TABLE 2]\nA: 1\nB: 2", "[TABLE 2]\nC: 3"])

    def test_oversized_table_row_is_split_and_each_fragment_keeps_marker(self):
        text = "[TABLE 3]\nNoi dung: alpha beta gamma delta"

        result = chunk_text(text, max_chars=27, overlap_chars=0)

        self.assertEqual(
            result,
            [
                "[TABLE 3]\nNoi dung: alpha",
                "[TABLE 3]\nbeta gamma delta",
            ],
        )
        self.assertTrue(all(len(chunk) <= 27 for chunk in result))

    def test_marker_with_no_content_budget_falls_back_to_bounded_ordinary_units(self):
        result = chunk_text("[TABLE 123456]\nA: 1", max_chars=8, overlap_chars=0)

        self.assertTrue(all(len(chunk) <= 8 for chunk in result))
        reconstructed = "".join(result).replace(" ", "")
        self.assertEqual(reconstructed, "[TABLE123456]A:1")

    def test_overlap_repeats_complete_trailing_unit(self):
        result = chunk_text(
            "AAAAA\n\nBBBBB\n\nCCCCC",
            max_chars=12,
            overlap_chars=5,
        )

        self.assertEqual(result, ["AAAAA\n\nBBBBB", "BBBBB\n\nCCCCC"])

    def test_overlap_zero_does_not_repeat_units(self):
        result = chunk_text(
            "AAAAA\n\nBBBBB\n\nCCCCC",
            max_chars=12,
            overlap_chars=0,
        )

        self.assertEqual(result, ["AAAAA\n\nBBBBB", "CCCCC"])

    def test_unit_larger_than_overlap_target_is_not_repeated(self):
        result = chunk_text(
            "AAAAAAAA\n\nBBBBBBBB",
            max_chars=10,
            overlap_chars=3,
        )

        self.assertEqual(result, ["AAAAAAAA", "BBBBBBBB"])

    def test_overlap_is_dropped_when_it_would_overflow_next_chunk(self):
        result = chunk_text(
            "AAAA\n\nBBBB\n\nCCCCCCCC",
            max_chars=10,
            overlap_chars=4,
        )

        self.assertEqual(result, ["AAAA\n\nBBBB", "CCCCCCCC"])

    def test_all_chunks_are_non_empty_and_bounded(self):
        text = (
            "Doan dau rat ngan.\n\n"
            "Mot cau dai hon de tach. Cau thu hai cung can tach.\n\n"
            "[TABLE 4]\nA: alpha beta\nB: gamma delta\nC: epsilon zeta"
        )

        result = chunk_text(text, max_chars=35, overlap_chars=10)

        self.assertTrue(result)
        self.assertTrue(all(chunk.strip() == chunk for chunk in result))
        self.assertTrue(all(0 < len(chunk) <= 35 for chunk in result))


if __name__ == "__main__":
    unittest.main()
