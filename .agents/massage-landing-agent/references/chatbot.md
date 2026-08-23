# Chatbot Integration

## Goal
Embed the existing customer chatbot as a floating interaction layer on the landing page.
Do not change the chatbot backend.

## Inspect existing implementation
Before building the widget, identify:
- chat API endpoint;
- request payload;
- response payload;
- session ID;
- conversation state;
- loading behavior;
- errors;
- booking confirmation behavior.

Reuse the existing contract. Do not infer or redesign it.

## Target flow

```text
Landing Page
    |
ChatWidget
    |
Chatbot API
    |
    +-- LLM
    +-- Qdrant
    +-- Booking Backend
```

Do not use an iframe.

## Component boundary
Prefer a small reusable set:

```text
components/chatbot/
├── ChatWidget
├── ChatWindow
├── ChatMessage
└── ChatInput
```

If equivalent components already exist, reuse/extend them instead of creating duplicates.
Split further only when complexity requires it.

## Ownership
`ChatWidget` should own or coordinate:
- open/closed state;
- conversation state;
- session state;
- API interaction.

Static landing sections should not depend on chatbot internals.

## Entry points
The following may open the same chatbot instance:
- floating button;
- hero CTA;
- service consultation CTA;
- AI assistant CTA.

Never mount multiple independent chat sessions simply because several CTAs exist.

## Closed state
Show one unobtrusive floating chat control.
It must:
- remain accessible on mobile;
- not cover essential content;
- have a clear accessible label.

## Open state
Provide:
- assistant identity;
- close control;
- scrollable conversation;
- loading feedback;
- error feedback;
- message input;
- send control.

Size responsively rather than relying on one fixed desktop size.
On mobile, keep reading space usable and close control reachable.

## Quick prompts
Optional starting prompts:
- `Tư vấn dịch vụ`
- `Xem giá dịch vụ`
- `Kiểm tra lịch trống`
- `Tôi muốn đặt lịch`

Send through the existing chat contract unless the backend already defines a specific action format.

## Error handling
Handle:
- failed request;
- empty response;
- unavailable service;
- duplicate submission while sending.

Do not silently discard user input.

## Preserve backend behavior
Do not alter:
- intent handling;
- RAG behavior;
- session semantics;
- booking confirmation logic;
- backend response structure.

The frontend adapts to the existing chatbot service.
