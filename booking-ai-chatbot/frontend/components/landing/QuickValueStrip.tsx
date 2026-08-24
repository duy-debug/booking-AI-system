import { valueProps } from "@/components/landing/data";
import { Container } from "@/components/ui/Container";

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
