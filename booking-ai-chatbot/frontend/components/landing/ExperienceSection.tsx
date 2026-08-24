import { WellnessImage } from "@/components/landing/WellnessImage";
import { landingImages } from "@/components/landing/data";
import { Container } from "@/components/ui/Container";

export function ExperienceSection() {
  return (
    <section className="zen-section why-section" id="experience">
      <Container>
        <div className="section-divider-title">
          <span />
          <h2>Why Choose Kori Massage</h2>
          <span />
        </div>

        <div className="why-grid">
          <div className="why-copy">
            <h3>Peace, At Last...</h3>
            <p>
              Ở Kori, mỗi liệu trình được chuẩn bị như một khoảng nghỉ riêng: ánh sáng
              ấm, nhịp phục vụ chậm và Kori AI hỗ trợ chọn đúng dịch vụ trước khi đến.
            </p>
            <a href="#services">Read more</a>
          </div>

          <div className="why-images" aria-hidden="true">
            <WellnessImage
              src={landingImages.aroma}
              alt=""
              className="why-image large"
              sizes="(max-width: 900px) 80vw, 28vw"
            />
            <WellnessImage
              src={landingImages.hotStone}
              alt=""
              className="why-image small"
              sizes="(max-width: 900px) 54vw, 18vw"
            />
          </div>
        </div>
      </Container>
    </section>
  );
}
