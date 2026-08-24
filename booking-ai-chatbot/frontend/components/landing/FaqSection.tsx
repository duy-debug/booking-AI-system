import { faqs } from "@/components/landing/data";
import { Container } from "@/components/ui/Container";
import { SectionHeading } from "@/components/ui/SectionHeading";

export function FaqSection() {
  return (
    <section className="landing-section faq-section" id="faq">
      <Container>
        <SectionHeading
          align="center"
          eyebrow="FAQ"
          title="Những câu hỏi thường gặp"
          description="Nếu câu hỏi của anh/chị cụ thể hơn, hãy mở Kori để chatbot tra cứu và trả lời theo ngữ cảnh."
        />
        <div className="faq-list">
          {faqs.map((item) => (
            <details key={item.question}>
              <summary>{item.question}</summary>
              <p>{item.answer}</p>
            </details>
          ))}
        </div>
      </Container>
    </section>
  );
}
