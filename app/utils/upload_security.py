"""
上传文件安全模块（纯函数，可独立测试）

上传链路的统一安全边界：
- 文件名清洗：剥离路径部分、替换危险字符、限制长度，杜绝 ../ 路径穿越
- 后缀白名单：只放行装修资料常见格式
- 大小限制：单文件上限，防止异常大文件占满磁盘/内存
"""

import re
from pathlib import Path

# 装修场景资料白名单：报价单（Excel）、合同（PDF/Word）、说明与清单（文本）
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".xls", ".md", ".txt", ".csv"}

MAX_FILE_SIZE = 20 * 1024 * 1024  # 单文件 20MB

MAX_NAME_LENGTH = 120

# 允许保留在存储文件名中的字符：中英文、数字、点、横线、下线、空格
_SAFE_NAME_PATTERN = re.compile(r"[^\w.\- ]", re.UNICODE)


def sanitize_filename(raw_name: str) -> str:
    """
    清洗用户上传的文件名

    处理内容：取路径最后一段（防 ../ 穿越）、替换非法字符、压缩空白、限制长度。
    :param raw_name: 原始文件名
    :return: 可安全落盘的存储文件名（保留原始扩展名）
    """
    name = Path(str(raw_name).replace("\\", "/")).name
    name = _SAFE_NAME_PATTERN.sub("_", name)
    name = re.sub(r"\s+", " ", name).strip("._ ")

    if not name:
        name = "unnamed_file"

    stem = Path(name).stem
    suffix = Path(name).suffix
    if len(name) > MAX_NAME_LENGTH:
        keep = max(10, MAX_NAME_LENGTH - len(suffix))
        name = stem[:keep] + suffix

    return name


def validate_upload(raw_name: str, size: int | None) -> tuple[str | None, str, str]:
    """
    校验一次上传是否可接收

    :param raw_name: 原始文件名
    :param size: 文件字节数（未知传 None）
    :return: (存储文件名, 文件后缀, 错误信息)；校验通过时错误信息为空串，失败时存储文件名为 None
    """
    storage_name = sanitize_filename(raw_name)
    extension = Path(storage_name).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        allowed = "、".join(sorted(ALLOWED_EXTENSIONS))
        return None, extension, f"不支持的文件格式 '{extension or '（无后缀）'}'，仅支持：{allowed}"

    if size is not None and size > MAX_FILE_SIZE:
        return None, extension, f"文件过大（{size / 1024 / 1024:.1f}MB），单文件上限 20MB"

    return storage_name, extension, ""
