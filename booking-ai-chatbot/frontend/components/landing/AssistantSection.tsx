import { ArrowRightIcon } from "@/components/common/Icons";
import { ChatOpenButton } from "@/components/landing/ChatOpenButton";
import { Container } from "@/components/ui/Container";
import { SectionHeading } from "@/components/ui/SectionHeading";

const capabilities = [
  "Lắng nghe nhu cầu",
  "Gợi ý liệu trình",
  "Kiểm tra lịch trống",
  "Nhắc lại trước khi xác nhận",
];

// Section giới thiệu vai trò của Kori và dẫn người dùng mở chatbot để bắt đầu đặt lịch.
export function AssistantSection() {
  return (
    <section className="assistant-section about-kori" id="assistant">
      <Container className="about-kori-panel">
        <SectionHeading
          eyebrow="Về Kori"
          title="AI chỉ đứng phía sau để buổi chăm sóc diễn ra nhẹ hơn."
          description="Kori không thay thế trải nghiệm massage. Trợ lý chỉ giúp anh/chị mô tả nhu cầu, chọn liệu trình và hoàn tất đặt lịch tự nhiên hơn."
        />
        <div className="capability-list">
          {capabilities.map((item) => (
            <span key={item}>{item}</span>
          ))}
        </div>
        <ChatOpenButton>
          Đặt lịch với Kori <ArrowRightIcon />
        </ChatOpenButton>
      </Container>
    </section>
  );
}
