# Frontend Rules (React + Vite)

## Stack thực tế
- React 19 + Vite 7 (SPA, KHÔNG phải Next.js)
- Plain JS/JSX (không dùng TypeScript trong project này)
- Tailwind CSS 3 trực tiếp — KHÔNG dùng shadcn/ui
- React Router v7, Tiptap (rich text), Recharts, react-force-graph-2d

## API Calls
- Gọi thẳng FastAPI qua `src/utils/api.js` (`ragFetch`/`ragFetchV2`) — KHÔNG có route handler trung gian như Next.js
- Streaming chat: `readSSEStream()` (SSE/NDJSON parser) trong cùng file
- Error boundary cho mọi page, toast notification cho lỗi

## Chat UI
- Message format: `{role: "user"|"assistant", content: string, sources?: Source[]}`
- Luôn show loading skeleton khi đang fetch/stream

## File Upload
- Chỉ accept: PDF, DOCX, TXT — max 50MB (validate client-side)
- Show progress bar khi upload

## Reference
Chi tiết cấu trúc component/page: xem CLAUDE.md và `micco-frontend/src/`.
