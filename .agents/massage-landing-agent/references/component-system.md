# Component System and Reuse Policy

## Goal

Treat reusable components as an internal library.
Pages and sections should compose components, not recreate their implementation.

## Required decision order

Whenever a UI need appears, follow this order:

```text
Need UI/behavior
    |
    v
Does a suitable component already exist?
    | yes -> reuse it
    |
    no
    v
Can an existing component support it with a small prop/variant extension?
    | yes -> extend once, then reuse
    |
    no
    v
Is it generic across features/pages?
    | yes -> create in components/ui
    |
    no
    v
Create a feature component in the appropriate feature folder
    |
    v
Import and use it from the section/page
```

Do not skip directly to inline duplicated JSX.

## Reuse hierarchy

Prefer:

```text
Page
  -> Section
      -> Feature Component
          -> Shared UI Primitive
```

Example:

```text
HomePage
├── HeroSection
│   ├── Container
│   └── Button
├── ServicesSection
│   └── ServiceCard
│       ├── Badge
│       └── Button
├── FAQSection
│   └── Accordion
└── ChatWidget
    ├── IconButton
    ├── ChatMessage
    └── ChatInput
```

## Shared UI primitives

Typical reusable primitives may include:

```text
components/ui/
├── Button.tsx
├── IconButton.tsx
├── Container.tsx
├── SectionHeading.tsx
├── Badge.tsx
├── Card.tsx
└── Accordion.tsx
```

Do not create all of these automatically. Create only what the project needs.
If a suitable equivalent already exists, reuse it.

## Feature components

Feature-specific components belong with their feature, for example:

```text
components/services/
├── ServiceCard.tsx
└── ServiceGrid.tsx

components/chatbot/
├── ChatWidget.tsx
├── ChatWindow.tsx
├── ChatMessage.tsx
└── ChatInput.tsx
```

## Missing component rule

When a page or section needs a component that does not exist:

- do not write a one-off local version inside the page just to finish the page;
- create the component in the appropriate shared/feature location;
- design a small reusable API with props;
- consume it from every place that needs it;
- migrate obvious duplicate markup to the reusable component when encountered in the same task.

Example: if a section needs a new button variant, prefer extending:

```tsx
<Button variant="secondary">Tư vấn dịch vụ</Button>
```

instead of writing a separate styled `<button>` in that section.

If `ServiceCard` needs to support an optional consultation action, extend it once:

```tsx
<ServiceCard
  service={service}
  onConsult={() => openChat(service.name)}
/>
```

instead of duplicating a second card implementation.

## Avoid premature abstraction

Do not create a component merely because an element appears once.

Extract when at least one is true:
- the same UI appears in multiple places;
- behavior is meaningful or stateful;
- multiple variants are needed;
- the parent becomes substantially clearer;
- the component is a stable design-system primitive.

Avoid meaningless wrapper chains such as:

```text
HeroWrapper
HeroInner
HeroContentWrapper
HeroTextWrapper
```

unless they encapsulate real reusable behavior.

## Page responsibility

A page should mostly compose sections.

Prefer:

```tsx
export default function HomePage() {
  return (
    <>
      <Navbar />
      <main>
        <HeroSection />
        <ServicesSection />
        <ExperienceSection />
        <FAQSection />
        <ContactSection />
      </main>
      <Footer />
      <ChatWidget />
    </>
  );
}
```

Avoid large duplicated presentation markup in `page.tsx`.

## Consistency rule

When adding a new reusable component:
- follow the existing naming convention;
- reuse existing design tokens/classes;
- support existing theme behavior;
- keep API minimal;
- add variants only when currently needed;
- do not add a new dependency solely for one component if existing tools are sufficient.
