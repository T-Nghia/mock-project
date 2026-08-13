import unittest
from unittest.mock import patch

from app.core.config import settings
from app.services import summary_service


class GenerateSummaryTestCase(unittest.TestCase):
    """Unit tests for MP-28 Generate Summary."""

    def setUp(self):
        self.original_gemini_key = settings.GEMINI_API_KEY
        self.original_openai_key = settings.OPENAI_API_KEY
        # Unit tests must be deterministic and never make a real network call.
        settings.GEMINI_API_KEY = ""
        settings.OPENAI_API_KEY = ""

    def tearDown(self):
        settings.GEMINI_API_KEY = self.original_gemini_key
        settings.OPENAI_API_KEY = self.original_openai_key

    def test_empty_text_returns_friendly_fallback(self):
        self.assertEqual(
            summary_service.generate_summary("   \n\t"),
            summary_service.EMPTY_SUMMARY,
        )

    def test_local_fallback_is_deterministic_and_bounded(self):
        text = (
            "Học máy là lĩnh vực nghiên cứu các thuật toán có khả năng học từ dữ liệu. "
            "Dữ liệu huấn luyện quyết định trực tiếp đến chất lượng của mô hình. "
            "Tiền xử lý giúp làm sạch dữ liệu và chuẩn hóa các thuộc tính đầu vào. "
            "Hồi quy tuyến tính là mô hình cơ bản dùng để dự đoán biến liên tục. "
            "Phân loại logistic thường được áp dụng cho bài toán nhãn rời rạc. "
            "Đánh giá mô hình cần tách dữ liệu huấn luyện và dữ liệu kiểm thử độc lập. "
            "Các độ đo như accuracy, precision và recall phản ánh các khía cạnh khác nhau. "
            "Overfitting xảy ra khi mô hình ghi nhớ dữ liệu huấn luyện nhưng tổng quát hóa kém. "
            "Regularization và cross-validation là các kỹ thuật phổ biến để giảm overfitting."
        )

        first = summary_service.generate_summary(text, title="Nhập môn học máy")
        second = summary_service.generate_summary(text, title="Nhập môn học máy")

        self.assertEqual(first, second)
        self.assertNotEqual(first, summary_service.EMPTY_SUMMARY)
        self.assertLessEqual(len(first), summary_service.MAX_SUMMARY_CHARS)

    def test_local_fallback_covers_beginning_middle_and_end_of_long_text(self):
        text = " ".join(
            [
                "Phần đầu giới thiệu mục tiêu nghiên cứu về dữ liệu giáo dục và bối cảnh của bài toán.",
                "Phần đầu mô tả nguồn dữ liệu được thu thập từ hoạt động học tập của sinh viên.",
                "Phần đầu nêu yêu cầu phải làm sạch dữ liệu trước khi phân tích.",
                "Phần giữa trình bày phương pháp huấn luyện mô hình dự đoán kết quả học tập.",
                "Phần giữa giải thích quy trình chia tập train và tập test để đánh giá khách quan.",
                "Phần giữa so sánh nhiều mô hình bằng các độ đo đánh giá phù hợp.",
                "Phần cuối báo cáo kết quả thực nghiệm và những quan sát chính từ dữ liệu.",
                "Phần cuối thảo luận hạn chế của phương pháp và các nguồn sai số còn tồn tại.",
                "Phần cuối đề xuất hướng phát triển tiếp theo dựa trên dữ liệu lớn hơn và đa dạng hơn.",
            ]
        )

        result = summary_service.generate_summary(text)

        self.assertIn("Phần đầu", result)
        self.assertIn("Phần giữa", result)
        self.assertIn("Phần cuối", result)

    def test_gemini_summary_is_used_when_provider_returns_valid_text(self):
        class FakeResponse:
            text = (
                "Tài liệu trình bày các nội dung trọng tâm của môn học và giải thích mối liên hệ giữa "
                "các khái niệm chính. Tác giả mô tả quy trình áp dụng kiến thức thông qua các bước cụ thể. "
                "Phần cuối tổng hợp kết quả và nêu những điểm cần lưu ý khi vận dụng."
            )

        class FakeModel:
            def __init__(self, _name):
                pass

            def generate_content(self, _prompt, generation_config=None):
                return FakeResponse()

        class FakeGenAI:
            @staticmethod
            def configure(api_key):
                return None

            GenerativeModel = FakeModel

        settings.GEMINI_API_KEY = "test-key"
        with patch.object(summary_service, "genai", FakeGenAI):
            result = summary_service.generate_summary(
                "Nội dung đủ dài để kiểm tra cơ chế sinh tóm tắt bằng nhà cung cấp Gemini. " * 5
            )

        self.assertTrue(result.startswith("Tài liệu trình bày"))

    def test_provider_error_falls_back_locally_instead_of_failing_job(self):
        class BrokenModel:
            def __init__(self, _name):
                pass

            def generate_content(self, _prompt, generation_config=None):
                raise RuntimeError("provider unavailable")

        class BrokenGenAI:
            @staticmethod
            def configure(api_key):
                return None

            GenerativeModel = BrokenModel

        settings.GEMINI_API_KEY = "test-key"
        with patch.object(summary_service, "genai", BrokenGenAI):
            result = summary_service.generate_summary(
                "Tài liệu mô tả phương pháp xử lý dữ liệu. "
                "Các bước gồm làm sạch, chuẩn hóa và đánh giá. "
                "Kết quả cho thấy quy trình giúp dữ liệu nhất quán hơn."
            )

        self.assertNotEqual(result, summary_service.EMPTY_SUMMARY)
        self.assertIn("Tài liệu", result)


if __name__ == "__main__":
    unittest.main()
