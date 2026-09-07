---
description: E2E test một tính năng vừa code xong bằng trình duyệt thật, theo đúng trải nghiệm người dùng
---

## E2E Feature Test Skill

Dùng ngay sau khi code xong 1 feature/bugfix (đặc biệt có UI), **trước khi commit**, để xác minh nó
hoạt động đúng như người dùng thật trải nghiệm — không chỉ dựa vào unit test xanh.

Không thay thế `/run-qa` (unit + integration suite) hay `/rag-test` (RAG pipeline pytest) — dùng
bổ sung, tập trung vào hành vi thấy được trên UI/API thật đang chạy.

### 1. Chuẩn bị môi trường

```bash
# Services
cd micco-backend && docker compose -f docker-compose.services.yml up -d   # Postgres :5435 + Chroma :8003

# Backend
cd micco-backend/backend && uvicorn app.main:app --reload --port 8000

# Frontend
cd micco-frontend && npm run dev   # port 5174
```

Auth cho test nhanh — set `VITE_SKIP_AUTH=true` trong `micco-frontend/.env` để bỏ qua màn login
(backend trả về user đầu tiên trong DB làm Admin), hoặc login thật bằng tài khoản seed
(`seed_users.py`, mật khẩu override qua `SEED_ADMIN_PASSWORD`/`SEED_USER_PASSWORD` nếu có):

| Role | Email | Password mặc định |
|---|---|---|
| Admin | `admin@micco.vn` | `Admin_Default_123!` |
| Nhân viên | `user1@micco.vn` | `User_Default_123!` |

### 2. Chạy trình duyệt thật

Ưu tiên Playwright (đã có sẵn trong `micco-frontend/package.json`):

```bash
cd micco-frontend
npx playwright install --with-deps chromium   # chỉ cần lần đầu
```

Nếu chưa có `playwright.config.js` + thư mục `e2e/`, tạo tối thiểu:

```js
// micco-frontend/playwright.config.js
import { defineConfig } from '@playwright/test'
export default defineConfig({
  testDir: './e2e',
  use: { baseURL: 'http://localhost:5174', screenshot: 'only-on-failure' },
})
```

Viết 1 file test riêng cho feature vừa code — `micco-frontend/e2e/<feature-name>.spec.js` — rồi chạy:

```bash
npx playwright test e2e/<feature-name>.spec.js --headed   # xem trực tiếp lần đầu
npx playwright test e2e/<feature-name>.spec.js            # chạy lại headless để xác nhận
```

Nếu môi trường không cho chạy trình duyệt Playwright thật (sandbox hạn chế), dùng công cụ trình
duyệt sẵn có (skill `webapp-testing`, hoặc Chrome DevTools) để thao tác thủ công theo đúng các
bước golden path bên dưới, chụp screenshot làm bằng chứng thay vì bỏ qua bước này.

### 3. Quy trình kiểm thử

1. **Xác định phạm vi**: đọc `git diff` / mô tả feature → liệt kê route/trang bị ảnh hưởng, role
   được phép dùng, API endpoint liên quan.
2. **Golden path**: đi đúng luồng người dùng bình thường từ đầu đến cuối (vd: đăng nhập → vào
   Documents → upload file → chờ status chuyển sang `INDEXED` → mở Chat → hỏi liên quan tài liệu →
   nhận câu trả lời kèm sources).
3. **Edge cases** — tối thiểu kiểm tra:
   - Input rỗng / sai định dạng / file quá 50MB / sai loại file (không phải PDF/DOCX/TXT)
   - Role không đủ quyền thao tác action chỉ Admin/Trưởng phòng được phép → phải bị chặn đúng
     cách (403/UI ẩn), không crash
   - Backend trả lỗi hoặc mất kết nối giữa chừng → UI phải hiện thông báo lỗi rõ ràng, không đứng
     hình trắng
   - Trạng thái loading/streaming: skeleton hiển thị đúng lúc, SSE chat không bị đứt giữa chừng
4. **Soi UI kỹ**: nếu thấy layout lệch, light/dark mode lỗi, hoặc bất kỳ chi tiết nào "nhìn là thấy
   sai" dù không liên quan trực tiếp đến feature đang test — vẫn ghi lại và sửa luôn.
5. **Console/Network**: không có lỗi console đỏ, không có request 4xx/5xx bất ngờ khi đi golden path.
6. **Regression nhanh**: nếu feature chạm vào vùng dùng chung (auth, layout, api.js), thử luôn 1-2
   tính năng liền kề để chắc chưa vỡ (vd. sửa Documents thì thử thêm Chat/Approvals).

### 4. Báo cáo kết quả

```markdown
## E2E Report — <feature-name>

### Golden path
- [ ] Bước 1 ... ✅/❌
- [ ] Bước 2 ...

### Edge cases
| Case | Kết quả | Ghi chú |
|---|---|---|

### Console/Network
- Lỗi console: ...
- Request lỗi: ...

### Bugs phát hiện
1. ...

### Kết luận
✅ Sẵn sàng commit / ❌ Cần sửa thêm
```

### 5. Sau khi PASS

Theo git workflow của dự án: commit ngay với message Conventional Commits (`feat|fix: <mô tả>`),
không gộp chung với thay đổi không liên quan.
