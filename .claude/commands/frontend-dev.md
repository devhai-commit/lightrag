---
description: Phát triển frontend code trong micco-frontend
---

## Frontend Development Workflow

### Working Directory
```
micco-frontend
```

### Development Steps

1. **Understand Requirements**
   - Đọc yêu cầu từ user
   - Check existing component structure
   - Identify components cần modify/create

2. **Component Development**
   ```
   1. Create/update component
   2. Add error handling
   3. Add loading states
   4. Test manually (`/e2e-test` cho luồng có UI)
   ```

3. **Code Standards**
   - Functional components + hooks
   - Plain JS/JSX (project KHÔNG dùng TypeScript)
   - Tailwind CSS classes
   - camelCase naming

4. **File Structure**
   ```
   src/
   ├── components/
   │   ├── admin/
   │   ├── chat/
   │   ├── dashboard/
   │   ├── documents/
   │   ├── document-view/
   │   ├── landing/
   │   └── shared/
   ├── pages/
   ├── context/
   ├── hooks/
   ├── services/
   └── utils/
   ```

### Common Tasks

#### Create new component
```jsx
// src/components/new-component/NewComponent.jsx
import { useState } from 'react';

export function NewComponent({ prop1, onAction }) {
  const [loading, setLoading] = useState(false);

  const handleAction = async () => {
    setLoading(true);
    try {
      await onAction();
    } catch (error) {
      console.error('Error:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="...">
      {/* Component content */}
    </div>
  );
}
```

#### Add API integration
```javascript
// src/services/api.js
export const apiService = {
  async callEndpoint(data) {
    const response = await fetch('/api/v1/endpoint', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });

    if (!response.ok) {
      throw new Error('API Error');
    }

    return response.json();
  },

  async streamEndpoint(data, onChunk) {
    // Streaming implementation
  }
};
```

### Commands
```bash
cd micco-frontend
npm run dev      # dev server, port 5174
npm run build
npm run lint
```

### Testing
Project frontend chưa có test runner cấu hình (không có Jest/Vitest, không TypeScript).
Xác minh bằng cách chạy `/e2e-test` (Playwright thật hoặc thao tác trình duyệt trực tiếp) thay vì
`npm run test`.

### UI Guidelines

#### Loading States
```jsx
{loading ? (
  <div className="animate-pulse">
    <div className="h-4 bg-gray-200 rounded"></div>
  </div>
) : (
  <Content />
)}
```

#### Error Handling
```jsx
{error && (
  <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
    {error}
  </div>
)}
```

### Checklist trước khi complete task
- [ ] Component follows design system
- [ ] Error handling in place
- [ ] Loading states shown
- [ ] Responsive on all breakpoints
- [ ] No console errors
- [ ] API integration working
- [ ] ESLint passed
