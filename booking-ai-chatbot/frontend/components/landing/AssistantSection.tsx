import { MessageCircleIcon } from "@/components/common/Icons";
import { ChatOpenButton } from "@/components/landing/ChatOpenButton";
import { Container } from "@/components/ui/Container";
import { SectionHeading } from "@/components/ui/SectionHeading";

const capabilities = [
  "Tư vấn dịch vụ",
  "Hỏi giá và thời lượng",
  "Kiểm tra lịch trống",
  "Đặt lịch qua hội thoại",
  "Hỗ trợ đổi hoặc hủy lịch",
];

export function AssistantSection() {
  return (
    <section className="assistant-section" id="assistant">
      <Container className="assistant-panel">
        <div className="assistant-icon"><MessageCircleIcon /></div>
        <SectionHeading
          eyebrow="Kori AI Concierge"
          title="Một cửa sổ chat cho toàn bộ hành trình."
          description="Bạn có thể bắt đầu bằng một câu tự nhiên như “Tôi muốn massage thư giãn chiều mai”. Kori sẽ hỏi tiếp những thông tin còn thiếu."
        />
        <div className="capability-list">
          {capabilities.map((item) => <span key={item}>{item}</span>)}
        </div>
        <ChatOpenButton>Trò chuyện với Kori</ChatOpenButton>
      </Container>
    </section>
  );
}
