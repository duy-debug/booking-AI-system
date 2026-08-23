import { ArrowRightIcon } from "@/components/common/Icons";
import { ChatOpenButton } from "@/components/landing/ChatOpenButton";
import { services } from "@/components/landing/data";
import { Card } from "@/components/ui/Card";
import { Container } from "@/components/ui/Container";
import { SectionHeading } from "@/components/ui/SectionHeading";

export function ServicesSection() {
  return (
    <section className="landing-section" id="services">
      <Container>
        <SectionHeading
          eyebrow="Dịch vụ"
          title="Chọn nhịp chăm sóc phù hợp với cơ thể."
          description="Thông tin dưới đây là gợi ý tổng quan. Khi cần chọn chính xác hơn, Kori sẽ hỏi thêm nhu cầu và kiểm tra lịch phù hợp."
        />
        <div className="service-grid">
          {services.map((service) => (
            <Card className="service-card" key={service.name}>
              <div>
                <span className="service-meta">{service.duration} · {service.price}</span>
                <h3>{service.name}</h3>
                <p>{service.description}</p>
              </div>
              <div className="service-footer">
                <span>{service.benefit}</span>
                <ChatOpenButton variant="ghost">
                  Tư vấn dịch vụ này <ArrowRightIcon />
                </ChatOpenButton>
              </div>
            </Card>
          ))}
        </div>
      </Container>
    </section>
  );
}
