import { testimonials } from "@/components/landing/data";
import { Card } from "@/components/ui/Card";
import { Container } from "@/components/ui/Container";
import { SectionHeading } from "@/components/ui/SectionHeading";

export function TestimonialsSection() {
  return (
    <section className="landing-section" id="reviews">
      <Container>
        <SectionHeading
          eyebrow="Đánh giá"
          title="Một vài ghi chú trải nghiệm trong giai đoạn phát triển."
          description="Các nội dung này là placeholder phát triển, chưa phải review xác thực từ khách hàng thật."
        />
        <div className="testimonial-grid">
          {testimonials.map((item) => (
            <Card className="testimonial-card" key={item.quote}>
              <p>“{item.quote}”</p>
              <span>{item.author}</span>
            </Card>
          ))}
        </div>
      </Container>
    </section>
  );
}
