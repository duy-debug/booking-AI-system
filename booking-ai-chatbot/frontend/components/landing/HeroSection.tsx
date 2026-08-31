import { ArrowRightIcon } from "@/components/common/Icons";
import { ChatOpenButton } from "@/components/landing/ChatOpenButton";
import { WellnessImage } from "@/components/landing/WellnessImage";
import { landingImages } from "@/components/landing/data";
import { Container } from "@/components/ui/Container";

// Hero section tạo ấn tượng đầu tiên và đưa người dùng vào hành động đặt dịch vụ.
export function HeroSection() {
  return (
    <section className="zen-hero" id="top">
      <Container>
        <div className="zen-hero-card">
          <WellnessImage
            src={landingImages.hero}
            alt="Không gian massage thư giãn với ánh sáng ấm"
            className="zen-hero-image"
            priority
            sizes="(max-width: 900px) 100vw, 1120px"
          />
          <div className="zen-hero-overlay" />
          <div className="zen-hero-copy">
            <h1>Rebalance Your Body And Mind</h1>
            <p>Welcome to Kori Massage</p>
            <ChatOpenButton>
              Book Service <ArrowRightIcon />
            </ChatOpenButton>
          </div>
        </div>
      </Container>
    </section>
  );
}
