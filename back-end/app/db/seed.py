"""Dữ liệu mẫu: python -m app.db.seed [--admin]."""

import argparse
import os
import sys
from getpass import getpass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import SessionLocal, engine
from app.models import Subject, Topic, User, UserRole
from app.utils.password import hash_password
from app.validators.register_validator import validate_register_input

SAMPLE_SUBJECTS = (
    ("Toán", "THPT", (("Hàm số", "Hàm số bậc hai"), ("Đại số", "Phương trình bậc hai"))),
    ("Vật lí", "THPT", (("Cơ học", "Chuyển động thẳng đều"),)),
)

SAMPLE_USERS = (
    {
        "full_name": "Người học mẫu",
        "email": "learner@example.com",
        "password": "Learner@123",
        "role": UserRole.LEARNER.value,
    },
    {
        "full_name": "Quản trị viên mẫu",
        "email": "admin@example.com",
        "password": "Admin@123",
        "role": UserRole.ADMIN.value,
    },
)


def _seed_user(
    db: Session,
    *,
    full_name: str,
    email: str | None,
    password: str | None,
    role: str,
) -> None:
    result = validate_register_input(
        {
            "name": full_name,
            "email": email,
            "password": password,
            "confirmPassword": password,
            "consent": True,
        }
    )
    if not result.valid:
        raise ValueError(f"Thông tin {role} chưa hợp lệ: " + "; ".join(result.errors.values()))

    data = result.value
    assert data is not None
    user = db.scalar(select(User).where(User.email == data.email))
    if user is not None:
        if user.role != role:
            raise ValueError(
                f"Email {data.email} đã thuộc tài khoản có vai trò khác. Hãy dùng email khác."
            )
        return

    db.add(
        User(
            full_name=data.name,
            email=data.email,
            password_hash=hash_password(data.password),
            role=role,
        )
    )
    db.flush()


def seed_data(
    db: Session,
    *,
    admin_email: str | None = None,
    admin_password: str | None = None,
) -> None:
    for subject_name, grade_level, topics in SAMPLE_SUBJECTS:
        subject = db.scalar(
            select(Subject).where(Subject.name == subject_name, Subject.grade_level == grade_level)
        )
        if subject is None:
            subject = Subject(name=subject_name, grade_level=grade_level)
            db.add(subject)
            db.flush()

        for chapter_name, topic_name in topics:
            topic = db.scalar(
                select(Topic).where(
                    Topic.subject_id == subject.id,
                    Topic.chapter_name == chapter_name,
                    Topic.name == topic_name,
                )
            )
            if topic is None:
                db.add(Topic(subject_id=subject.id, chapter_name=chapter_name, name=topic_name))
                db.flush()

    # Seed ADMIN tự nhập trước để ưu tiên mật khẩu này nếu trùng email ADMIN mẫu.
    if admin_email is not None or admin_password is not None:
        _seed_user(
            db,
            full_name="Quản trị viên",
            email=admin_email,
            password=admin_password,
            role=UserRole.ADMIN.value,
        )

    for user_data in SAMPLE_USERS:
        _seed_user(db, **user_data)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed môn/chủ đề và tài khoản LEARNER, ADMIN mẫu.")
    parser.add_argument("--admin", action="store_true", help="Thêm ADMIN bằng thông tin tự nhập.")
    args = parser.parse_args()

    admin_email = None
    admin_password = None
    if args.admin:
        admin_email = os.environ.get("SEED_ADMIN_EMAIL", "").strip() or input("Email ADMIN: ")
        admin_password = os.environ.get("SEED_ADMIN_PASSWORD", "") or getpass("Mật khẩu ADMIN: ")

    try:
        with SessionLocal.begin() as db:
            seed_data(db, admin_email=admin_email, admin_password=admin_password)
    finally:
        engine.dispose()
    print("Đã seed dữ liệu thành công. Các bản ghi đã tồn tại được giữ nguyên.")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
