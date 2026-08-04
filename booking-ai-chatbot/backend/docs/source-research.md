# Nghiên cứu nguồn cho bộ dữ liệu NLU

Ngày truy cập: 2026-08-03. Các nguồn chỉ được dùng để nhận diện nhóm nhu cầu, thuật ngữ và cách tổ chức dữ liệu; utterance trong dataset là câu tổng hợp/viết lại, không sao chép hàng loạt.

| Nguồn | URL | Nội dung tham khảo | Nhóm được bổ sung |
|---|---|---|---|
| Rasa training data format | https://rasa.com/docs/reference/primitives/training-data-format/ | Cấu trúc intent example, entity span, synonym và lookup | schema, entity annotation, synonym/lookup |
| Rasa intents and entities | https://rasa.com/docs/reference/primitives/intents-and-entities/ | Lookup cho giá trị hữu hạn và yêu cầu ví dụ entity có ngữ cảnh | shop/service/therapist candidate resolution |
| Dialogflow CX intents | https://docs.cloud.google.com/dialogflow/cx/docs/concept/intent | Training phrase, parameter và intent matching | taxonomy và phrase diversity |
| Dialogflow ES training phrases | https://docs.cloud.google.com/dialogflow/es/docs/intents-training-phrases | Annotation span và entity example/reference value | entity offsets và synonym |
| CLINC150 | https://arxiv.org/abs/1909.02027 | Thiết kế intent classification có lớp out-of-scope | OOS và hard-negative evaluation |
| MASSIVE | https://arxiv.org/abs/2204.08582 | Dataset đa ngôn ngữ kết hợp intent và slot | intent + entity schema, split/evaluation |
| Hygge Spa – chính sách hoàn/hủy | https://hygge.com.vn/vi/chinh-sach-hoan-huy-dich-vu/ | Nhóm câu hỏi hủy, đổi, hoàn và xác nhận lịch | FAQ policy, change/cancel collision |
| Hasaki Clinic & Spa | https://hasaki.vn/dist/clinic.html | Thuật ngữ “đặt hẹn”, dịch vụ/liệu trình và chi nhánh | booking synonym, service FAQ |
| Thera Healing Spa | https://therahealingspa.vn/ve-thera-healing/ | Thuật ngữ body/Thai/foot/couple, kỹ thuật viên | service và therapist vocabulary |
| VietPOS spa/massage | https://vietpos.vn/phan-mem-quan-ly-spa-massage/ | Slot trống, dịch vụ, kỹ thuật viên, đặt lịch online | availability và booking vocabulary |
| Reservio – giảm hủy hẹn spa | https://www.reservio.com/vi/blog/meo/giam-huy-hen-spa | Ngôn ngữ lịch hẹn, xác nhận, hủy/no-show | confirmation, denial, policy FAQ |

Không có corpus tần suất đáng tin cậy trong các nguồn trên, vì vậy báo cáo không tuyên bố biến thể nào là “phổ biến nhất”. Không phát hiện conversation log đã ẩn danh và được phê duyệt để huấn luyện; `.runtime-smoke` chỉ là log vận hành, không được nhập vào dataset.
