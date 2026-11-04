"""业务卡片 · ① 获取整单状态 JSON（与 ② 解析落库解耦）.

本期仅实现企业上报 Body 取数；云→企业补偿查询预留入口，暂不调用外部。
"""

from __future__ import annotations

from typing import Any

from app.schemas.biz_card import BizCardReportIn


def from_report_body(body: BizCardReportIn | dict[str, Any]) -> dict[str, Any]:
    """从企业上报请求体取出与对接文档同构的状态 dict."""
    if isinstance(body, BizCardReportIn):
        return body.to_raw_dict()
    if not isinstance(body, dict):
        raise TypeError("上报体须为 dict 或 BizCardReportIn")
    return dict(body)


def from_enterprise_query(biz_id: str) -> dict[str, Any]:
    """预留：云→企业按 bizId 查询整单状态（与上报同构）.

    本期不实现；日后对接企业查询接口后，在此发起 HTTP 并返回 data 字段。
    """
    raise NotImplementedError(
        f"企业补偿查询尚未实现（bizId={biz_id}）；本期仅支持上报落库"
    )
