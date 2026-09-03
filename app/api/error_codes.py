"""
装修业务接口错误码规范

统一错误返回结构：HTTPException(detail={"code": ..., "message": ...})。
前端可根据 code 做结构化提示；HTTP 状态码仍遵循语义（404/403/400/409）。
"""

from fastapi import HTTPException

# 业务错误码定义
SESSION_NOT_FOUND = "SESSION_NOT_FOUND"          # 会话不存在
SESSION_FORBIDDEN = "SESSION_FORBIDDEN"          # 会话不属于当前用户
TASK_NOT_FOUND = "TASK_NOT_FOUND"                # 任务不存在
TASK_NOT_CANCELLABLE = "TASK_NOT_CANCELLABLE"    # 任务已结束，不可取消
FILE_NOT_FOUND = "FILE_NOT_FOUND"                # 文件记录不存在
FILE_FORBIDDEN = "FILE_FORBIDDEN"                # 文件不属于当前用户
FILE_PATH_INVALID = "FILE_PATH_INVALID"          # 文件路径越界
REPORT_NOT_FOUND = "REPORT_NOT_FOUND"            # 报告不存在
REPORT_FORBIDDEN = "REPORT_FORBIDDEN"            # 报告不属于当前用户
UPLOAD_REJECTED = "UPLOAD_REJECTED"              # 文件未通过安全校验


def biz_error(status_code: int, code: str, message: str) -> HTTPException:
    """构造统一结构的业务异常。"""
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})
