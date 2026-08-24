export const navItems = [
  { href: "#services", label: "Dịch vụ" },
  { href: "#pricing", label: "Bảng giá" },
  { href: "#experience", label: "Trải nghiệm" },
  { href: "#assistant", label: "Về Kori" },
];

export const landingImages = {
  hero:
    "https://images.unsplash.com/photo-1544161515-4ab6ce6db874?auto=format&fit=crop&w=1600&q=85",
  aroma:
    "https://images.unsplash.com/photo-1600334129128-685c5582fd35?auto=format&fit=crop&w=900&q=85",
  deepRelease:
    "https://images.unsplash.com/photo-1540555700478-4be289fbecef?auto=format&fit=crop&w=900&q=85",
  foot:
    "https://images.unsplash.com/photo-1519823551278-64ac92734fb1?auto=format&fit=crop&w=900&q=85",
  hotStone:
    "https://images.unsplash.com/photo-1552693673-1bf958298935?auto=format&fit=crop&w=900&q=85",
};

export const services = [
  {
    name: "Aroma Reset",
    description:
      "Massage thư giãn với tinh dầu ấm, phù hợp khi cơ thể cần được thả lỏng nhẹ nhàng.",
    benefit: "Giúp giảm căng thẳng, làm dịu nhịp thở và hỗ trợ giấc ngủ.",
    duration: "60 phút",
    price: "Từ 650.000đ",
    featured: true,
    image: landingImages.aroma,
    perfectFor: "Căng thẳng nhẹ, ngủ chưa sâu",
  },
  {
    name: "Deep Release",
    description:
      "Kỹ thuật tác động sâu cho vùng vai, lưng và cổ bị căng do làm việc hoặc vận động nhiều.",
    benefit: "Hỗ trợ giảm mỏi cơ và phục hồi cảm giác linh hoạt.",
    duration: "75 phút",
    price: "Từ 820.000đ",
    featured: false,
    image: landingImages.deepRelease,
    perfectFor: "Vai gáy, lưng, cơ căng",
  },
  {
    name: "Foot Renewal",
    description:
      "Chăm sóc bàn chân và bắp chân bằng nhịp day ấn vừa phải, dễ chịu sau một ngày dài.",
    benefit: "Tạo cảm giác nhẹ chân, thư thái và cân bằng lại năng lượng.",
    duration: "45 phút",
    price: "Từ 420.000đ",
    featured: false,
    image: landingImages.foot,
    perfectFor: "Nhẹ chân, phục hồi sau ngày dài",
  },
  {
    name: "Hot Stone Massage",
    description:
      "Đá nóng giúp làm dịu vùng cơ căng, tạo cảm giác ấm sâu và thư giãn dài hơn.",
    benefit: "Phù hợp khi cơ thể cần được làm ấm và thả lỏng chậm rãi.",
    duration: "90 phút",
    price: "Từ 980.000đ",
    featured: false,
    image: landingImages.hotStone,
    perfectFor: "Cơ lạnh, mỏi sâu, cần thư giãn lâu",
  },
];

export const valueProps = [
  "Đặt lịch trong chưa đầy 1 phút",
  "AI hỗ trợ 24/7",
  "Không cần gọi điện",
  "Đề xuất liệu trình phù hợp",
];

export const journeySteps = [
  {
    index: "01",
    title: "Nói cho Kori biết anh/chị đang cần gì",
    description: "Mô tả vùng đau mỏi, tâm trạng hoặc khoảng thời gian mong muốn.",
  },
  {
    index: "02",
    title: "AI đề xuất liệu trình",
    description: "Kori gợi ý dịch vụ, thời lượng và thông tin giá dễ hiểu.",
  },
  {
    index: "03",
    title: "Chọn ngày và thời gian",
    description: "Chatbot hỏi tiếp các dữ liệu còn thiếu để kiểm tra lịch trống.",
  },
  {
    index: "04",
    title: "Xác nhận booking",
    description: "Thông tin cuối cùng được nhắc lại trước khi hệ thống tạo đặt lịch.",
  },
];

export const experienceItems = [
  "Kori ghi nhận nhu cầu trước buổi massage.",
  "Liệu trình được đề xuất dựa trên mục tiêu của khách.",
  "Thông tin booking được xác nhận rõ ràng.",
  "Có thể tiếp tục cuộc trò chuyện bất kỳ lúc nào.",
];

export const steps = [
  "Mở trợ lý AI Kori.",
  "Mô tả nhu cầu, thời gian hoặc dịch vụ mong muốn bằng ngôn ngữ tự nhiên.",
  "Kori kiểm tra thông tin, lịch trống và hỏi tiếp những dữ liệu còn thiếu.",
  "Anh/chị xác nhận thông tin cuối cùng trước khi hệ thống tạo booking.",
];

export const testimonials = [
  {
    quote:
      "Không gian rất yên. Kori giúp mình chọn đúng liệu trình trước khi đến.",
    author: "Annie G.",
  },
  {
    quote:
      "Mình chỉ nói vai cổ bị căng, Kori gợi ý ngay thời lượng phù hợp và nhắc lại lịch rất rõ.",
    author: "Olivia B.",
  },
  {
    quote:
      "Buổi massage nhẹ nhàng hơn vì mọi thông tin đã được chuẩn bị trước.",
    author: "Daniel K.",
  },
];

export const therapists = [
  {
    name: "Maya Le",
    specialty: "Relaxation Therapy",
    rating: "4.9",
    image: landingImages.aroma,
  },
  {
    name: "Jonah Nguyen",
    specialty: "Sports Massage",
    rating: "4.8",
    image: landingImages.deepRelease,
  },
  {
    name: "Anna Lam",
    specialty: "Aromatherapy",
    rating: "4.9",
    image: landingImages.foot,
  },
  {
    name: "Haruki Chang",
    specialty: "Thai Stretch",
    rating: "4.7",
    image: landingImages.hotStone,
  },
];

export const faqs = [
  {
    question: "Tôi nên chọn loại massage nào?",
    answer:
      "Anh/chị có thể mô tả tình trạng cơ thể cho Kori. Trợ lý sẽ gợi ý dịch vụ phù hợp dựa trên nhu cầu thư giãn, đau mỏi hoặc thời lượng mong muốn.",
  },
  {
    question: "Tôi có thể đặt lịch qua landing page không?",
    answer:
      "Landing page không có form booking riêng. Việc tư vấn, kiểm tra lịch và đặt lịch được xử lý qua chatbot để giữ đúng luồng xác nhận.",
  },
  {
    question: "Tôi có thể đổi hoặc hủy lịch không?",
    answer:
      "Anh/chị có thể trao đổi với Kori trong cùng cửa sổ chat. Chatbot sẽ hướng dẫn theo trạng thái booking hiện tại.",
  },
];
