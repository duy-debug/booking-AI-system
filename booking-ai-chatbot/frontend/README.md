# Booking AI Chatbot Frontend

Thư mục dành cho giao diện khách hàng bằng Next.js, React và TypeScript.

Frontend chỉ gọi Chatbot Backend qua HTTP/SSE. Frontend không gọi trực tiếp API
mutation của Booking Backend và không giữ business rule đặt lịch.

Cấu trúc dự kiến:

```text
app/
components/
├── chat/
├── booking/
└── common/
services/
stores/
schemas/
types/
```
