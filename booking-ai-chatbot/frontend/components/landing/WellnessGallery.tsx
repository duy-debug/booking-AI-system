import { WellnessImage } from "@/components/landing/WellnessImage";
import { landingImages } from "@/components/landing/data";
import { Container } from "@/components/ui/Container";

const galleryItems = [
  {
    src: landingImages.deepRelease,
    alt: "Không gian trị liệu vai gáy",
    label: "Bodywork",
  },
  {
    src: landingImages.aroma,
    alt: "Tinh dầu và khăn ấm",
    label: "Aroma ritual",
  },
  {
    src: landingImages.hotStone,
    alt: "Không gian spa yên tĩnh",
    label: "Quiet room",
  },
];

export function WellnessGallery() {
  return (
    <section className="gallery-section" aria-label="Không gian wellness">
      <Container className="gallery-layout">
        <div className="gallery-copy">
          <span className="eyebrow">Wellness gallery</span>
          <h2>Những khoảng lặng được chuẩn bị có chủ đích.</h2>
        </div>
        <div className="gallery-stack">
          {galleryItems.map((item, index) => (
            <figure className={`gallery-item item-${index + 1}`} key={item.src}>
              <WellnessImage src={item.src} alt={item.alt} sizes="(max-width: 900px) 90vw, 32vw" />
              <figcaption>{item.label}</figcaption>
            </figure>
          ))}
        </div>
      </Container>
    </section>
  );
}
