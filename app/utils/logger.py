"""
统一日志模块

提供项目统一的 logger 工厂：格式、级别（LOG_LEVEL 环境变量，默认 INFO）。
各模块通过 get_logger(__name__) 获取，替代裸 print；
工具层面向模型返回的字符串错误不变，日志只进服务端日志。
"""

import logging
import os
import sys

_CONFIGURED = False


def _configure_root() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%H:%M:%S")
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """获取统一配置的 logger。"""
    _configure_root()
    return logging.getLogger(name)
