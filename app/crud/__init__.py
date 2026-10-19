"""Tầng truy cập dữ liệu (Data Access Layer).

Quy ước:
- Chỉ làm việc với DB (query / add / commit), KHÔNG biết gì về HTTP (không raise HTTPException).
- Router gọi crud, sau đó tự quyết định trả 404 / 403 / 409 ...
"""
