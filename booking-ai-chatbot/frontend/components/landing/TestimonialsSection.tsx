import { testimonials } from "@/components/landing/data";
import { Container } from "@/components/ui/Container";

export function TestimonialsSection() {
  return (
    <section className="zen-section testimonials-section" id="reviews">
      <Container>
        <div className="section-divider-title">
          <span />
          <h2>What Our Clients Say</h2>
          <span />
        </div>

        <div className="zen-testimonial-grid">
          {testimonials.map((item) => (
            <article className="zen-testimonial-card" key={item.quote}>
              <div className="stars">★★★★★</div>
              <p>“{item.quote}”</p>
              <strong>{item.author}</strong>
            </article>
          ))}
        </div>
      </Container>
    </section>
  );
}
