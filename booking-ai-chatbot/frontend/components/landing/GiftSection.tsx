import { ChatOpenButton } from "@/components/landing/ChatOpenButton";
import { WellnessImage } from "@/components/landing/WellnessImage";
import { landingImages } from "@/components/landing/data";
import { Container } from "@/components/ui/Container";

export function GiftSection() {
  return (
    <section className="gift-section">
      <Container>
        <div className="section-divider-title">
          <span />
          <h2>Give the Gift of Stillness</h2>
          <span />
        </div>

        <div className="gift-grid">
          <WellnessImage
            src={landingImages.foot}
            alt="Gói quà tặng massage thư giãn"
            className="gift-image"
            sizes="(max-width: 900px) 100vw, 42vw"
          />
          <div className="gift-copy">
            <span className="eyebrow">Luxury treatment packages</span>
            <h3>Một món quà yên tĩnh cho người cần được nghỉ ngơi.</h3>
            <p>
              Gửi tặng một liệu trình massage được chuẩn bị nhẹ nhàng. Kori có thể
              hỗ trợ người nhận chọn dịch vụ, thời lượng và khung giờ phù hợp.
            </p>
            <div className="gift-packages">
              <span>60-90 Minutes</span>
              <span>Price $90-$199</span>
            </div>
            <ChatOpenButton>Explore Packages</ChatOpenButton>
          </div>
        </div>
      </Container>
    </section>
  );
}
