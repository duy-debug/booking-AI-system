# Landing Page Structure

Use this as the default information architecture. Adapt or merge sections when the current project already communicates the same information.

## Recommended hierarchy

```text
Navbar
Hero
Services
Trust / Experience
How It Works
Testimonials
AI Assistant
FAQ
Contact
Footer
ChatWidget
```

## Navbar
Include useful anchors such as:
- Trang chủ
- Dịch vụ
- Trải nghiệm
- Đánh giá
- Liên hệ

Optional CTA: `Trò chuyện với trợ lý`.
It opens the existing chatbot.
Do not add a traditional booking flow if booking is intentionally handled through chat.

## Hero
Answer quickly:
- What is this service?
- What value does it provide?
- What should the visitor do next?

Recommended structure:

```text
eyebrow
H1
short supporting text
primary chatbot CTA
secondary services anchor
visual
```

Keep copy concise and avoid exaggerated claims.

## Services
Each service may include:
- name;
- short description;
- key benefit;
- duration;
- price;
- image.

Optional CTA: `Tư vấn dịch vụ này` -> opens the same chatbot instance.
Render services from structured data rather than repeating markup.

## Trust / Experience
Use one or both depending on available content.
Possible topics:
- therapist quality;
- privacy;
- hygiene;
- environment;
- consultation process;
- service consistency.

Do not make unverifiable trust claims.

## How It Works
Reflect the actual AI-first booking flow:
1. Mở trợ lý AI.
2. Mô tả nhu cầu hoặc dịch vụ mong muốn.
3. Trợ lý kiểm tra thông tin và lịch phù hợp.
4. Khách hàng xác nhận booking.

## Testimonials
Use real reviews if available.
If none exist, use development placeholders isolated as mock data.
Never present fabricated reviews as verified customer reviews.

## AI Assistant
Explain chatbot capabilities such as:
- tư vấn dịch vụ;
- hỏi giá;
- kiểm tra lịch;
- đặt lịch;
- đổi lịch;
- hủy lịch.

CTA opens the existing chatbot widget.

## FAQ
Use relevant questions only.
Potential topics:
- loại massage phù hợp;
- thời lượng;
- lựa chọn kỹ thuật viên;
- cách đặt lịch;
- đổi hoặc hủy lịch;
- thời gian nên đến trước buổi hẹn.

Implement accordion accessibly with native button, `aria-expanded`, `aria-controls` and keyboard-focusable headers.

## Contact
Present available business information:
- address;
- phone;
- email;
- opening hours.

Do not fabricate missing business details.

## Footer
Keep it compact:
- brand;
- useful links;
- contact;
- policies if available.
