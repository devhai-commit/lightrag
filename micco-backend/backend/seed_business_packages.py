"""Seed the B2B package catalogue with placeholder offers.

Run (from micco-backend/backend/, like seed_users.py):
    PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe seed_business_packages.py

IMPORTANT — the content below is a PLACEHOLDER shaped like Micco's real lines of
business (industrial explosives, blasting services, consulting). It has NOT been
signed off by sales, and no figure in it is a quote. It exists so the
recommendation path can be exercised end to end. Replace it with the real
catalogue before the portal is shown to a customer (see D2/D11 in
B2B_PORTAL_PROGRESS.md).

Idempotent: matches on `name`, updates the row if it already exists, so running
it twice does not duplicate the catalogue.
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import select  # noqa: E402

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models.business_package import BusinessPackage  # noqa: E402

PLACEHOLDER_PACKAGES = [
    {
        "name": "Cung ứng thuốc nổ công nghiệp cho mỏ lộ thiên",
        "category": "Vật liệu nổ công nghiệp",
        "summary": (
            "Cung ứng thuốc nổ và phụ kiện nổ theo tiến độ khai thác cho mỏ đá "
            "và mỏ khoáng sản lộ thiên. Bao gồm tư vấn lựa chọn loại thuốc nổ "
            "theo điều kiện đá và độ ẩm lỗ khoan."
        ),
        "target_customer": (
            "Doanh nghiệp khai thác đá xây dựng, đá vôi, quặng lộ thiên có "
            "nhu cầu cung ứng định kỳ."
        ),
        "highlights": [
            "Giao hàng theo tiến độ khai thác",
            "Tư vấn chọn loại thuốc nổ theo điều kiện lỗ khoan",
            "Hồ sơ pháp lý vật liệu nổ đầy đủ",
        ],
        "price_note": "Báo giá theo khối lượng và địa bàn, đội ngũ kinh doanh xác nhận.",
        "sort_order": 10,
    },
    {
        "name": "Dịch vụ nổ mìn trọn gói",
        "category": "Dịch vụ nổ mìn",
        "summary": (
            "Micco đảm nhận toàn bộ công tác nổ mìn: thiết kế hộ chiếu nổ, "
            "khoan, nạp nổ, giám sát an toàn và xử lý sau nổ. Khách hàng không "
            "cần tự quản lý kho vật liệu nổ."
        ),
        "target_customer": (
            "Chủ đầu tư và nhà thầu thi công không có giấy phép sử dụng vật "
            "liệu nổ, hoặc muốn chuyển toàn bộ rủi ro vận hành cho đơn vị "
            "chuyên môn."
        ),
        "highlights": [
            "Bao gồm thiết kế hộ chiếu nổ và giám sát an toàn",
            "Không cần tự quản lý kho vật liệu nổ",
            "Phù hợp công trình có tiến độ gấp",
        ],
        "price_note": "Tính theo khối lượng đá nguyên khối, khảo sát hiện trường trước khi báo giá.",
        "sort_order": 20,
    },
    {
        "name": "Nổ mìn công trình dân dụng và hạ tầng",
        "category": "Dịch vụ nổ mìn",
        "summary": (
            "Phá đá, mở tuyến và hạ cốt nền cho công trình giao thông, thuỷ "
            "điện và hạ tầng đô thị, với phương án giảm chấn và kiểm soát "
            "rung động cho khu vực có dân cư lân cận."
        ),
        "target_customer": (
            "Nhà thầu hạ tầng thi công gần khu dân cư hoặc công trình hiện hữu, "
            "cần kiểm soát rung động và đá bay."
        ),
        "highlights": [
            "Phương án giảm chấn cho khu vực có dân cư",
            "Quan trắc rung động trong quá trình thi công",
            "Hồ sơ nghiệm thu theo quy định",
        ],
        "price_note": "Phụ thuộc điều kiện mặt bằng và yêu cầu quan trắc.",
        "sort_order": 30,
    },
    {
        "name": "Tư vấn kỹ thuật và huấn luyện an toàn vật liệu nổ",
        "category": "Tư vấn và huấn luyện",
        "summary": (
            "Tư vấn tối ưu hộ chiếu nổ để giảm tiêu hao thuốc nổ trên mỗi mét "
            "khối, kèm huấn luyện an toàn cho nhân sự trực tiếp làm việc với "
            "vật liệu nổ."
        ),
        "target_customer": (
            "Doanh nghiệp đã tự vận hành nổ mìn nhưng muốn giảm chi phí tiêu "
            "hao hoặc cần hoàn thiện hồ sơ an toàn."
        ),
        "highlights": [
            "Rà soát và tối ưu hộ chiếu nổ hiện tại",
            "Huấn luyện an toàn theo quy định hiện hành",
            "Có thể triển khai theo từng đợt",
        ],
        "price_note": "Theo phạm vi khảo sát và số lượng nhân sự tham gia.",
        "sort_order": 40,
    },
]


async def seed() -> None:
    async with AsyncSessionLocal() as db:
        created = updated = 0
        for data in PLACEHOLDER_PACKAGES:
            existing = (
                await db.execute(
                    select(BusinessPackage).where(BusinessPackage.name == data["name"])
                )
            ).scalar_one_or_none()

            if existing is None:
                db.add(BusinessPackage(is_active=True, **data))
                created += 1
            else:
                for key, value in data.items():
                    setattr(existing, key, value)
                existing.is_active = True
                updated += 1

        await db.commit()

        total = len(
            (
                await db.execute(
                    select(BusinessPackage).where(BusinessPackage.is_active.is_(True))
                )
            ).scalars().all()
        )
        print(f"created={created} updated={updated} active_total={total}")


if __name__ == "__main__":
    asyncio.run(seed())
