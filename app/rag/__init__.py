"""
企业规章制度 RAG 模块（独立于现有 MDM 业务）。

目录说明：
- models / schemas / service / api / session_service：管理台元数据、会话与接口
- lightrag_engine：进程内嵌 LightRAG（rag_project 入库壳 + MDM_RAG_SPLITTER 切分 + naive 提问/侧车回挂）
- splitter：Plan A/B 文档切分
- user_interaction/question_splitter：复杂问题拆分
- model_config / paths：轻量 LLM 与本地路径（配置见 app.config Settings，前缀 MDM_RAG_*）

本期范围：知识库分组、文件上传入库、切片查看、云侧调试提问、设备侧会话问答。
未做：切片编辑回写重向量化（见根目录 待办.txt）。
"""
