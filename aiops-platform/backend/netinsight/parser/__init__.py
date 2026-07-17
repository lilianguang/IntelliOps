"""网络洞察 - 配置解析器包

用法：
    from netinsight.parser import get_parser
    parser = get_parser("h3c")
    result = parser.parse(config_content)
"""

from netinsight.parser.base import BaseConfigParser, ParsingResult
from netinsight.parser.h3c import H3CParser


# 厂商 -> 解析器映射
_PARSER_REGISTRY = {
    "h3c": H3CParser,
    # 后续可扩展：huawei, cisco, nsfocus, venustech 等
}


def get_parser(vendor: str) -> BaseConfigParser:
    """根据厂商名获取解析器实例

    Args:
        vendor: 厂商标识，如 h3c/huawei/cisco

    Returns:
        BaseConfigParser: 解析器实例；未知厂商返回 BaseConfigParser 基类（空结果）
    """
    vendor_lower = (vendor or "unknown").lower()
    parser_cls = _PARSER_REGISTRY.get(vendor_lower)
    if parser_cls:
        return parser_cls()
    return BaseConfigParser()


def register_parser(vendor: str, parser_cls: type):
    """注册新的厂商解析器"""
    _PARSER_REGISTRY[vendor.lower()] = parser_cls


__all__ = [
    "BaseConfigParser",
    "ParsingResult",
    "H3CParser",
    "get_parser",
    "register_parser",
]
