"""
上传文件安全测试

覆盖 PRD 开发计划 3.2 的验收标准：
- 路径穿越文件名被清洗（../a.txt 不会写出会话目录）
- 不支持格式被拒绝
- 超大文件被拒绝
- 合法文件名保留原始扩展名和中文
"""

import pytest

from app.utils.upload_security import (
    ALLOWED_EXTENSIONS,
    MAX_FILE_SIZE,
    sanitize_filename,
    validate_upload,
)


class TestSanitizeFilename:
    def test_path_traversal_stripped(self):
        assert sanitize_filename("../../etc/a.txt") == "a.txt"
        assert sanitize_filename("..\\..\\evil.md") == "evil.md"

    def test_absolute_path_stripped(self):
        assert sanitize_filename("/etc/passwd.txt") == "passwd.txt"
        assert "C:" not in sanitize_filename("C:/Users/test/报价单.xlsx")

    def test_dangerous_chars_replaced(self):
        name = sanitize_filename('quote<>:"|?*.pdf')
        assert set(name) <= set("abcdefghijklmnopqrstuvwxyz0123456789._ -") or name.endswith(".pdf")
        assert "<" not in name and ">" not in name and "|" not in name

    def test_chinese_name_preserved(self):
        assert sanitize_filename("装修报价单.xlsx") == "装修报价单.xlsx"

    def test_empty_becomes_unnamed(self):
        assert sanitize_filename("") == "unnamed_file"
        assert sanitize_filename("../../") == "unnamed_file"

    def test_long_name_truncated_keeps_extension(self):
        name = sanitize_filename("很长的文件名" * 50 + ".docx")
        assert len(name) <= 130
        assert name.endswith(".docx")


class TestValidateUpload:
    def test_allowed_extensions(self):
        for ext in [".pdf", ".docx", ".xlsx", ".xls", ".md", ".txt", ".csv"]:
            storage, extension, error = validate_upload(f"file{ext}", 1024)
            assert error == ""
            assert storage == f"file{ext}"
            assert extension == ext

    def test_rejected_extension(self):
        _, _, error = validate_upload("virus.exe", 1024)
        assert "不支持的文件格式" in error
        assert ".exe" in error or "exe" in error

    def test_no_extension_rejected(self):
        _, _, error = validate_upload("无后缀文件", 1024)
        assert "不支持的文件格式" in error

    @pytest.mark.parametrize(
        "size",
        [MAX_FILE_SIZE + 1, 2 * MAX_FILE_SIZE, 200 * 1024 * 1024],
    )
    def test_oversize_rejected(self, size):
        _, _, error = validate_upload("big.pdf", size)
        assert "过大" in error

    def test_acceptable_size_passes(self):
        storage, _, error = validate_upload("合同.docx", MAX_FILE_SIZE - 1)
        assert error == ""
        assert storage == "合同.docx"


def test_whitelist_matches_prd():
    # PRD 开发计划 3.2 规定的白名单：pdf/docx/xlsx/xls/md/txt（csv 为实现新增）
    assert {".pdf", ".docx", ".xlsx", ".xls", ".md", ".txt"} <= ALLOWED_EXTENSIONS
