"""Xem prompt mẫu offline: python -m app.prompts."""

import json

from app.prompts import PROMPT_VERSION, SocraticTopic, build_first_turn_messages


def main() -> None:
    messages = build_first_turn_messages(
        topic=SocraticTopic(
            subject_name="Toán", topic_name="Phương trình bậc hai",
            grade_level="THPT", chapter_name="Đại số",
        ),
        question="Làm sao bắt đầu giải phương trình x² − 5x + 6 = 0?",
    )
    print(json.dumps({"promptVersion": PROMPT_VERSION, "messages": messages}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
