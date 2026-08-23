import { MapPinIcon, PhoneIcon } from "@/components/common/Icons";
import { ChatOpenButton } from "@/components/landing/ChatOpenButton";
import { Container } from "@/components/ui/Container";

export function ContactSection() {
  return (
    <section className="landing-section contact-section" id="contact">
      <Container className="contact-panel">
        <div>
          <span className="eyebrow">Liên hệ</span>
          <h2>Cần tư vấn nhanh? Hãy để Kori hỏi đúng thông tin trước.</h2>
          <p>
            Thông tin cửa hàng cụ thể sẽ được lấy qua hệ thống booking khi bạn bắt đầu hội thoại.
          </p>
        </div>
        <div className="contact-actions">
          <span><MapPinIcon /> Chi nhánh được xác nhận trong luồng chat</span>
          <span><PhoneIcon /> Thông tin liên hệ dùng theo booking thực tế</span>
          <ChatOpenButton>Hỏi Kori ngay</ChatOpenButton>
        </div>
      </Container>
    </section>
  );
}
