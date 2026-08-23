---
name: massage-landing
summary: Build or refactor a modern massage/spa landing page in an existing Next.js project, with reusable components and an existing AI chatbot embedded as a floating popup.
description: Use when creating or improving the public massage/spa landing page, its reusable UI/component system, or integrating the existing chatbot frontend into the landing page. The landing page is informational; chatbot is the primary customer interaction and booking channel. Do not use for booking backend, RAG, database, or LLM changes unless explicitly requested.
---

# Massage Landing Page

Build or refactor the public massage/spa landing page inside the existing Next.js project.

## Product intent

The landing page helps customers:
- understand the brand and services;
- browse massage services, durations, prices, benefits and basic information;
- understand the service experience;
- read FAQ, reviews and contact information;
- open the AI chatbot.

The chatbot is the primary interaction and booking channel.
Do not introduce a separate booking form unless explicitly requested.

## Core engineering rule: reuse first

Treat `components/` as the project's internal UI library.

Before writing any UI markup:
1. Search for an existing component with the same responsibility.
2. Reuse it if suitable.
3. If it is close but missing a small capability, extend the existing component through props/variants.
4. If no suitable component exists, create a reusable component in the correct shared or feature folder.
5. Only then consume that component from the page/section that needs it.

Never solve a missing UI need by duplicating equivalent markup directly inside a page or section.

If the same visual pattern, behavior, or interaction may be needed in multiple places, implement it once as a reusable component and call it where needed.

Read `references/component-system.md` before adding or changing reusable UI.

## Before editing

Inspect only relevant frontend files:
1. `package.json`
2. `app/` or `pages/`
3. root layout
4. global styles/design tokens
5. existing `components/`
6. current chatbot frontend/API client
7. frontend/chatbot environment variables

Determine:
- routing model;
- TypeScript/JavaScript;
- styling system;
- current component conventions;
- existing chatbot API/session contract.

Follow the project conventions before introducing new patterns.
Do not inspect unrelated backend code unless required to understand the chatbot contract.

## Next.js rules

If App Router is used:
- keep static landing sections as Server Components by default;
- add `"use client"` only to interactive boundaries such as chatbot, mobile navigation, accordion, carousel, or other stateful UI;
- do not mark the whole page as a Client Component for a small interaction;
- keep metadata in a Server Component using the Next.js Metadata API.

## Workflow

### 1. Inspect
Understand the existing project and reusable component inventory.

### 2. Plan component reuse
Before coding, classify every planned UI element as:
- existing reusable component;
- extension of an existing component;
- new shared primitive;
- new feature component;
- page/section composition only.

Do not write duplicated local versions to move faster.

### 3. Build the landing skeleton
Recommended order:

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

Read `references/structure.md`.
Sections may be merged or omitted when equivalent information already exists.

### 4. Apply visual direction
Read `references/design.md`.
Aim for a calm, clean, warm, spacious, modern wellness interface.
Do not copy another website's content or layout exactly.

### 5. Fill content
Write concise Vietnamese copy.
Use real project data when available.
Use mock data only when necessary and keep it isolated and easy to replace.

Never invent:
- awards;
- certifications;
- review scores;
- customer counts;
- medical claims;
- business achievements.

### 6. Integrate chatbot
Read `references/chatbot.md`.
Reuse the existing chatbot API contract, session logic, loading/error states and confirmation flow.
Render one floating chatbot widget on the landing page.
Do not use an iframe.
Do not create a duplicate chatbot backend.

### 7. Verify
Check:
- desktop/tablet/mobile layout;
- no horizontal overflow;
- anchors and navigation;
- chatbot open/close;
- message sending;
- loading/error states;
- accessibility basics;
- existing routes;
- component reuse with no avoidable duplication.

Run the project's existing lint/build commands when available.
Fix errors introduced by this work.

## Scope boundaries

Do not modify unless explicitly requested:
- booking backend;
- booking business rules;
- database schema;
- RAG pipeline;
- vector database behavior;
- LLM behavior;
- chatbot API contract.

## Completion criteria

The task is complete when:
1. the landing page is visually complete on desktop and mobile;
2. service information is easy to scan;
3. chatbot is easy to access without blocking content;
4. all chatbot entry points open the same widget;
5. existing chatbot behavior is preserved;
6. existing project routes still work;
7. reusable UI is implemented once and consumed through components rather than copied across pages/sections.
