"""跨模块共享的常量。"""
from __future__ import annotations

# 已抽取进结构化数据库表（school_admission_*）的文件，不再进 RAG 向量索引。
STRUCTURED_FILENAMES = {
    "CIT2425省内投档线.md",
    "CIT2026省内投档线.md",
    "长沙工业学院历年录取分数线汇总.md",
    "长沙工业学院2024年拟招生本科专业及人数.md",
    "长沙工业学院2025年湖南省招生计划.md",
    "长沙工业学院2025年外省分专业计划.md",
    "长沙工业学院2026年招生计划.md",
}
