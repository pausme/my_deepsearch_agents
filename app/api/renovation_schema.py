"""
装修业务接口请求/响应模型

字段与 docs/prd/home-renovation-api-design.md 和数据模型文档对齐。
"""

from pydantic import BaseModel, Field


class RenovationSessionCreate(BaseModel):
    """创建装修分析会话请求体。"""

    city: str = Field(..., min_length=1, max_length=64, description="装修所在城市")
    house_area: float = Field(..., gt=0, le=2000, description="房屋面积（平方米）")
    room_type: str = Field(..., min_length=1, max_length=64, description="房型，如三室两厅一卫")
    renovation_stage: str = Field(
        "INITIAL",
        description="装修阶段：INITIAL/QUOTE_REVIEW/CONTRACT_REVIEW/CONSTRUCTION/SOFT_FURNISH",
    )
    district: str = Field("", max_length=64, description="区县（可选）")
    budget_min: float | None = Field(None, ge=0, description="预算下限（元）")
    budget_max: float | None = Field(None, ge=0, description="预算上限（元）")
    priority_tags: list[str] = Field(default_factory=list, description="关注重点：省钱/颜值/环保/工期/耐用")
    delivery_date: str = Field("", description="期望入住时间，如 2026-12-31")


class RenovationTaskCreate(BaseModel):
    """提交装修分析任务请求体。"""

    session_id: str = Field(..., min_length=1, description="装修会话 ID")
    query: str = Field(..., min_length=1, description="分析要求或问题")
    analysis_type: str = Field(
        "FULL_REPORT",
        description=(
            "分析类型：INITIAL_DIAGNOSIS/QUOTE_REVIEW/CONTRACT_REVIEW/"
            "MATERIAL_ADVICE/BUDGET_OPTIMIZATION/FULL_REPORT"
        ),
    )
