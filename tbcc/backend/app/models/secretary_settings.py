"""Dashboard-editable secretary / Format Engine settings (singleton row)."""

from sqlalchemy import Boolean, Column, Integer, String, Text

from .base import Base

ROW_ID = 1


class SecretarySettings(Base):
    __tablename__ = "secretary_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    format_engine_enabled = Column(Boolean, nullable=True)
    fe_verbosity = Column(String(16), nullable=True)  # compact | standard
    public_faq_enabled = Column(Boolean, nullable=True)
    llm_refine_on_phase_change = Column(Boolean, nullable=True)
    llm_provider = Column(String(32), nullable=True)  # openai | openrouter
    llm_api_key = Column(Text, nullable=True)
    llm_model = Column(String(128), nullable=True)
    llm_base_url = Column(String(256), nullable=True)
    rag_enabled = Column(Boolean, nullable=True)
    rag_top_k = Column(Integer, nullable=True)
    system_prompt = Column(Text, nullable=True)
    system_prompt_extra = Column(Text, nullable=True)
