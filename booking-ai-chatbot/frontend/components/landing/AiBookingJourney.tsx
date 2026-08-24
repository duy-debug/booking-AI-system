import { LandingChatPreview } from "@/components/landing/LandingChatPreview";
import { journeySteps } from "@/components/landing/data";
import { Container } from "@/components/ui/Container";

export function AiBookingJourney() {
  return (
    <section className="zen-section ai-booking-section" id="kori-booking">
      <Container>
        <div className="section-divider-title">
          <span />
          <h2>Booking With Kori</h2>
          <span />
        </div>

        <div className="ai-booking-grid">
          <LandingChatPreview variant="compact" />
          <div className="ai-booking-copy">
            <h3>Đặt lịch bằng một cuộc trò chuyện.</h3>
            <p>
              Kori hỏi đúng thông tin cần thiết, đề xuất liệu trình và nhắc lại
              booking trước khi xác nhận.
            </p>
            <ol>
              {journeySteps.map((step) => (
                <li key={step.index}>
                  <span>{step.index}</span>
                  {step.title}
                </li>
              ))}
            </ol>
          </div>
        </div>
      </Container>
    </section>
  );
}
