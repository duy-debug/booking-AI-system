import { therapists } from "@/components/landing/data";
import { WellnessImage } from "@/components/landing/WellnessImage";
import { ChatOpenButton } from "@/components/landing/ChatOpenButton";
import { Container } from "@/components/ui/Container";

// Section giới thiệu therapist mẫu để tăng độ tin cậy, CTA vẫn đưa về chatbot thay vì đặt trực tiếp.
export function TherapistsSection() {
  return (
    <section className="therapists-section">
      <Container>
        <div className="section-divider-title">
          <span />
          <h2>Our Master Therapists</h2>
          <span />
        </div>

        <div className="therapist-frame">
          {therapists.map((therapist) => (
            <article className="therapist-card" key={therapist.name}>
              <WellnessImage
                src={therapist.image}
                alt={`Chuyên viên ${therapist.name}`}
                className="therapist-image"
                sizes="(max-width: 900px) 45vw, 18vw"
              />
              <div className="therapist-rating">★ {therapist.rating}</div>
              <div className="therapist-copy">
                <span>Name</span>
                <strong>{therapist.name}</strong>
                <span>Specialty</span>
                <p>{therapist.specialty}</p>
                <ChatOpenButton>Book Service</ChatOpenButton>
              </div>
            </article>
          ))}
        </div>
      </Container>
    </section>
  );
}
