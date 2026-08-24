import { ChatOpenButton } from "@/components/landing/ChatOpenButton";
import { services, therapists } from "@/components/landing/data";
import { Container } from "@/components/ui/Container";

export function ContactSection() {
  return (
    <section className="booking-section" id="pricing">
      <Container>
        <div className="section-divider-title">
          <span />
          <h2>Book Your Appointment</h2>
          <span />
        </div>

        <div className="appointment-panel" aria-label="Mẫu đặt lịch minh họa">
          <label>
            Choose a Massage Salon
            <select defaultValue="Komorebi Tân Bình">
              <option>Komorebi Tân Bình</option>
              <option>Komorebi Ba Đình</option>
              <option>Komorebi Thảo Điền</option>
            </select>
          </label>
          <label>
            Choose a Service
            <select defaultValue={services[0].name}>
              {services.map((service) => (
                <option key={service.name}>{service.name}</option>
              ))}
            </select>
          </label>
          <label>
            Choose a Specialist
            <select defaultValue={therapists[0].name}>
              {therapists.map((therapist) => (
                <option key={therapist.name}>{therapist.name}</option>
              ))}
            </select>
          </label>
          <div className="appointment-row">
            <label>
              Choose Date
              <input type="date" defaultValue="2026-08-24" />
            </label>
            <label>
              Choose Time
              <input type="time" defaultValue="14:00" />
            </label>
          </div>
          <div className="appointment-row">
            <label>
              Name
              <input placeholder="Anh/chị" />
            </label>
            <label>
              Phone number
              <input placeholder="+84" />
            </label>
          </div>
          <ChatOpenButton>Book Service</ChatOpenButton>
        </div>
      </Container>
    </section>
  );
}
