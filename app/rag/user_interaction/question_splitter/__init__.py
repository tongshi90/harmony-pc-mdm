"""
问题拆分模块 (Question Splitter)

将用户复杂问题拆为多个子问题，供检索使用。

使用示例：
    from app.rag.user_interaction.question_splitter import split_question
    from app.rag.model_config import get_text_splitter_llm

    sub_questions = split_question("什么是RAG？它有哪些优势", get_text_splitter_llm())
"""

from .question_splitter import (
    QuestionSplitter,
    LLMBasedSplitter,
    get_question_splitter,
    split_question,
)

__all__ = [
    "QuestionSplitter",
    "LLMBasedSplitter",
    "get_question_splitter",
    "split_question",
]
