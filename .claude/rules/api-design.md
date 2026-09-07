# API Design Rules

## Endpoint Structure
- Base: /api/v1/
- Tất cả response wrap trong: {"data": ..., "meta": {...}}
- Error response: {"error": {"message": "...", "code": "...", "details": {}}}

## Versioning
- Luôn có /api/v1/ prefix
- Breaking changes → tạo /api/v2/, KHÔNG xóa v1 ngay

## Request/Response
```python
# Mọi endpoint phải có schema rõ ràng
class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    document_ids: Optional[List[str]] = None
    stream: bool = True

class ChatResponse(BaseModel):
    response: str
    conversation_id: str
    sources: List[DocumentSource]
    usage: TokenUsage
```

## Auth
- JWT Bearer token cho mọi endpoint trừ /health và /docs
- Rate limiting: 60 req/min per user, 10 req/min cho /upload

## Async
- Mọi endpoint PHẢI là async def
- File upload xử lý via background task (BackgroundTasks)

## Business account convention (external B2B signup)
- Role `"Doanh nghiệp"` (external business) đăng ký công khai qua `POST /api/auth/register-business` — tạo `User` với `approval_status="pending"`, KHÔNG trả token (không auto-login).
- `POST /api/auth/login` chặn (403) tài khoản `role == "Doanh nghiệp"` khi `approval_status` không phải `"approved"` — phân biệt message `"pending"` vs `"rejected"`.
- Admin duyệt/từ chối qua `PUT /api/admin/users/{id}/approval` (chỉ áp dụng cho role Doanh nghiệp, 400 nếu không phải).
- `User.approval_status` (`"pending"/"approved"/"rejected"`, `None` cho các role nội bộ) mirror convention của `Document.approval_status`.
- `POST /api/auth/login` cũng chặn (403) tài khoản Doanh nghiệp **đã** được duyệt, và chỉ sang cổng doanh nghiệp: cổng nội bộ không phải bề mặt của khách.
- Bề mặt bên ngoài nằm dưới `/api/v1/business/...`, sau `get_current_business_user` (yêu cầu claim `scope: "business"`, từ chối token `dev-skip`):
  `POST /auth/login`, `GET /me`, `POST /chat/stream` (SSE), `GET` và `DELETE /chat/history`.
  Chỉ bề mặt này dùng envelope `{"data", "meta"}`.
- `POST /chat/stream` nhận **chỉ** `{message}` với `extra="forbid"`; workspace, phạm vi tài liệu, retrieval mode và history đều do server quyết định.
  SSE event: `status`, `sources`, `delta`, `complete`, `error`.
- Endpoint admin của portal: `PUT /api/v1/business/admin/workspaces/{id}/audience`, `GET /api/v1/business/admin/documents`, `PUT /api/v1/business/admin/documents/{id}/publish` (đều sau `require_admin`).
- **CHƯA triển khai**: catalog sản phẩm, tool gợi ý gói (`package_recommendation.py`), và chuyển lead cho sales.
