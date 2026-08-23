import { CalendarCheckIcon, CheckIcon, SparklesIcon } from "@/components/common/Icons";
import { experienceItems, steps } from "@/components/landing/data";
import { Card } from "@/components/ui/Card";
import { Container } from "@/components/ui/Container";
import { SectionHeading } from "@/components/ui/SectionHeading";

export function ExperienceSection() {
  return (
    <section className="landing-section experience-section" id="experience">
      <Container className="experience-grid">
        <div>
          <SectionHeading
            eyebrow="Trải nghiệm"
            title="Một buổi chăm sóc được chuẩn bị rõ ràng từ trước."
            description="Landing page chỉ giới thiệu dịch vụ. Toàn bộ tư vấn và booking đi qua chatbot để giữ đúng luồng xác nhận."
          />
          <ul className="check-list">
            {experienceItems.map((item) => (
              <li key={item}><CheckIcon />{item}</li>
            ))}
          </ul>
        </div>
        <Card className="process-card">
          <span className="process-icon"><CalendarCheckIcon /></span>
          <h3>Luồng đặt lịch AI-first</h3>
          <ol>
            {steps.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
          <div className="process-note">
            <SparklesIcon />
            <span>Không tạo booking nếu bạn chưa xác nhận thông tin cuối cùng.</span>
          </div>
        </Card>
      </Container>
    </section>
  );
}
