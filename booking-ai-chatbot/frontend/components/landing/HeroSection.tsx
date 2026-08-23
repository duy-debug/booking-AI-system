import { ArrowRightIcon, SparklesIcon } from "@/components/common/Icons";
import { ChatOpenButton } from "@/components/landing/ChatOpenButton";
import { ButtonLink } from "@/components/ui/Button";
import { Container } from "@/components/ui/Container";

export function HeroSection() {
  return (
    <section className="hero-section" id="top">
      <Container className="hero-grid">
        <div className="hero-copy">
          <span className="eyebrow">Wellness concierge for massage booking</span>
          <h1>Không gian massage thư giãn, đặt lịch bằng trợ lý AI.</h1>
          <p>
            Komorebi giúp bạn khám phá dịch vụ massage, hỏi thông tin cần thiết và đặt lịch qua
            Kori AI Concierge mà không cần điền form dài dòng.
          </p>
          <div className="hero-actions">
            <ChatOpenButton>
              Mở trợ lý AI <ArrowRightIcon />
            </ChatOpenButton>
            <ButtonLink href="#services" variant="ghost">Xem dịch vụ</ButtonLink>
          </div>
          <div className="hero-notes" aria-label="Điểm nổi bật">
            <span>Tư vấn dịch vụ</span>
            <span>Kiểm tra lịch trống</span>
            <span>Xác nhận trước khi đặt</span>
          </div>
        </div>
        <div className="hero-visual" aria-hidden="true">
          <div className="hero-orb large" />
          <div className="hero-orb small" />
          <div className="ritual-card">
            <span><SparklesIcon /></span>
            <strong>Calm ritual</strong>
            <p>Chọn dịch vụ theo nhu cầu, thời lượng và nhịp thư giãn của bạn.</p>
          </div>
          <div className="hero-image-panel">
            <div className="stone stone-one" />
            <div className="stone stone-two" />
            <div className="stone stone-three" />
          </div>
        </div>
      </Container>
    </section>
  );
}
