import { BotIcon, CheckIcon, SparklesIcon } from "@/components/common/Icons";

interface LandingChatPreviewProps {
  className?: string;
  variant?: "hero" | "showcase" | "compact";
}

// Mock preview trên landing page để minh họa cách Kori tư vấn mà không gọi API thật.
export function LandingChatPreview({
  className = "",
  variant = "hero",
}: LandingChatPreviewProps) {
  return (
    <div className={`landing-chat-preview ${variant}${className ? ` ${className}` : ""}`}>
      <div className="preview-header">
        <span className="preview-avatar">
          <BotIcon />
        </span>
        <div>
          <strong>Kori AI Concierge</strong>
          <small>Đang hỗ trợ chọn liệu trình</small>
        </div>
      </div>

      <div className="preview-thread">
        <p className="preview-bubble user">
          Vai mình hơi căng và mình muốn thư giãn khoảng một tiếng.
        </p>
        <p className="preview-bubble assistant">
          Mình đề xuất Aroma Reset 60 phút. Liệu trình này giúp thả lỏng vùng vai gáy,
          làm dịu nhịp thở và phù hợp nếu anh/chị muốn phục hồi nhẹ nhàng.
        </p>
      </div>

      <div className="preview-plan">
        <div>
          <span>Service</span>
          <strong>Aroma Reset</strong>
        </div>
        <div>
          <span>Duration</span>
          <strong>60 phút</strong>
        </div>
        <div>
          <span>Price</span>
          <strong>650.000đ</strong>
        </div>
      </div>

      <div className="preview-slots" aria-label="Khung giờ gợi ý">
        <span>10:30</span>
        <span>14:00</span>
        <span>16:30</span>
      </div>

      <div className="preview-confirm">
        <span>
          <SparklesIcon /> Sẵn sàng xác nhận
        </span>
        <button type="button">
          <CheckIcon /> Xác nhận
        </button>
      </div>
    </div>
  );
}
