import { ArrowRightIcon } from "@/components/common/Icons";
import { ChatOpenButton } from "@/components/landing/ChatOpenButton";
import { WellnessImage } from "@/components/landing/WellnessImage";
import { services } from "@/components/landing/data";
import { Container } from "@/components/ui/Container";

// Section dịch vụ hiển thị các gói nổi bật và dẫn từng gói về chatbot để tư vấn/đặt lịch.
export function ServicesSection() {
  return (
    <section className="zen-section service-showcase" id="services">
      <Container>
        <div className="section-divider-title">
          <span />
          <h2>Find Your Perfect Escape</h2>
          <span />
        </div>

        <div className="zen-service-list">
          {services.map((service, index) => (
            <article className={`zen-service-card ${index % 2 === 1 ? "reverse" : ""}`} key={service.name}>
              <WellnessImage
                src={service.image}
                alt={`Liệu trình ${service.name}`}
                className="zen-service-image"
                sizes="(max-width: 900px) 100vw, 34vw"
              />
              <div className="zen-service-copy">
                <h3>{service.name}</h3>
                <p>{service.description}</p>
                <div className="zen-service-details">
                  <div>
                    <strong>Benefits:</strong>
                    <span>{service.benefit}</span>
                  </div>
                  <div>
                    <strong>Perfect For:</strong>
                    <span>{service.perfectFor}</span>
                  </div>
                </div>
                <div className="zen-service-actions">
                  <span>{service.duration}</span>
                  <span>{service.price}</span>
                  <ChatOpenButton>
                    Book Service <ArrowRightIcon />
                  </ChatOpenButton>
                </div>
              </div>
            </article>
          ))}
        </div>

        <a className="view-all-link" href="#assistant">View All</a>
      </Container>
    </section>
  );
}
