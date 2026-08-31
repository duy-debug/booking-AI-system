import { valueProps } from "@/components/landing/data";
import { Container } from "@/components/ui/Container";

// Dải giá trị nhanh giúp người dùng nắm lợi ích chính của Kori trong một lần lướt.
export function QuickValueStrip() {
  return (
    <section className="value-strip" aria-label="Giá trị nhanh">
      <Container className="value-strip-inner">
        {valueProps.map((item) => (
          <span key={item}>{item}</span>
        ))}
      </Container>
    </section>
  );
}
