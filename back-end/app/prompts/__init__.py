"""Prompt độc lập với nhà cung cấp/model; không gọi mạng hoặc đọc tài khoản."""

from app.prompts.socratic import (
    PROMPT_VERSION,
    SOCRATIC_SYSTEM_PROMPT,
    SocraticTopic,
    build_first_turn_messages,
)

__all__ = ["PROMPT_VERSION", "SOCRATIC_SYSTEM_PROMPT", "SocraticTopic", "build_first_turn_messages"]
