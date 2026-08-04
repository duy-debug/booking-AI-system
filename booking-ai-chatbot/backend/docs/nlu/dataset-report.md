# Báo cáo bộ dữ liệu NLU tiếng Việt

## Inventory và taxonomy

Python `app.dialog.nlu_catalog.Intent` là contract có thẩm quyền; flow JSON vẫn sở hữu transition/action. Dataset giữ 22 label: `greeting`, `thanks`, `start_booking`, `list_shops`, `search_shops`, `select_shop`, `select_date`, `select_people`, `select_duration`, `list_services`, `list_addons`, `select_service`, `list_available_times`, `select_time`, `list_therapists`, `select_therapist`, `provide_phone`, `confirm`, `deny`, `change_info`, `faq`, `unknown`.

| Intent hiện tại | State hợp lệ chính | Entity | Handler/action family | Dữ liệu | Đề xuất |
|---|---|---|---|---|---|
| greeting, thanks, start_booking | IDLE | optional date/shop | greeting/no-op/search_shop | 40/intent | giữ |
| list_shops, search_shops, select_shop | SELECTING_SHOP | shop_name/area/index | search/resolve shop | 40/intent | candidate lookup động |
| select_date | SELECTING_DATE | booking_date/relative_date | handle_date_selection | 40 | giữ state policy |
| select_people | SELECTING_PEOPLE | number_of_people | handle_people_selection | 40 | business rule 1–3 ở domain |
| select_duration | SELECTING_DURATION | duration_minutes | handle_duration_selection | 40 | không suy diễn “6” thành 60 |
| list_services, list_addons, select_service | SELECTING_SERVICE | service/addon | search/handle service | 40/intent | POS candidates là truth |
| list_available_times, select_time | SELECTING_TIME | time/time_period | load/handle slots | 40/intent | validate latest slots |
| list_therapists, select_therapist | SELECTING_THERAPIST | therapist/ordinal/preference | list/handle therapist | 40/intent | group booking không assign cá nhân |
| provide_phone | COLLECTING_PHONE | phone_number | collect/validate phone | 40 | không đưa phone thật vào corpus |
| confirm, deny | VERIFYING_PHONE/AWAITING_CONFIRMATION | confirmation | state-specific confirmation | 40/intent | state phân biệt mutation |
| change_info | active booking states | changed slot entity | defer/change handler | 40 | confirmation khi mutation cần |
| faq | IDLE và interruptible states | optional domain entity | knowledge answer | 40 | không mutate context |
| unknown | mọi state | none | clarification/fallback | 40 | phân biệt OOS bằng dataset_label |

## Quy mô và phân phối

- Positive core: 880, đúng 40/intent; 20% biến thể không dấu/typing được lên lịch trong mỗi intent.
- Hard negatives: 330 (15 cho mỗi intent mục tiêu).
- Ambiguous: 220 (10 cho mỗi intent khi review; label runtime an toàn là `unknown`).
- Out-of-scope: 100.
- Multi-intent: 100; giữ primary/secondary, field an toàn, field cần xác nhận và thứ tự xử lý.
- Golden: 1.060, không nằm trong train; đạt các minimum theo nhóm và chứa đủ 10 câu bắt buộc.
- Core split cộng hard-negative/OOS: train 931, validation 201, test 178 (71.1% / 15.3% / 13.6%). Group-aware hashing giữ cùng `template_group` trong một split.
- Exact/normalized duplicate bị loại trước khi xuất: 0 trong bản cuối; validator xác nhận không có duplicate sau lowercase/bỏ dấu.

Entity taxonomy nằm trong `entity_catalog.yaml`. Shop/service/therapist lookup cố ý không chứa ID hoặc danh mục tĩnh; runtime Booking API/candidate list là source of truth. Entity span được tính bằng code và validator đối chiếu substring.

## Validation và evaluation

`python scripts/validate_nlu_dataset.py` pass: JSONL, ID, intent/state, offsets, normalized dedup, group leakage, split ratio, count tối thiểu và golden requirements đều hợp lệ.

Baseline minh bạch token-Jaccard trên test: intent accuracy **0.8876**, macro-F1 **0.8398**, OOS recall **1.0000**, 178 mẫu. Chi tiết per-intent, confusion matrix, accuracy theo state/tag nằm trong `data/nlu/evaluation-report.json`. Entity P/R/F1 1.0 chỉ là kiểm tra oracle đối với annotation span, không phải kết quả model extraction. Ambiguity detection chưa đo được vì chưa có classifier/threshold runtime độc lập; không được diễn giải baseline này là chất lượng production.

## Human review và giới hạn

`data/nlu/human_review.jsonl` xuất cho từng intent 20 positive, 10 hard negative, 5 ambiguous, entity và collision note. Tất cả được đánh dấu `NEEDS_EDIT`: dữ liệu synthetic chưa được tự động coi là ground truth. Các câu số hóa có hậu tố phục vụ uniqueness/evaluation phải được reviewer biên tập hoặc loại trước khi training thật.

Không có log hội thoại đã ẩn danh được phê duyệt, dữ liệu hoàn toàn synthetic. Các intent cần ưu tiên log thật: `unknown`, `change_info`, `search_shops`, `select_service`, `list_available_times`, `select_time`, và FAQ interrupt. Nhu cầu lookup/cancel/reschedule booking chỉ nên bổ sung sau khi runtime contract/handler tồn tại. Không có business logic hoặc runtime NLU nào được thay đổi trong phase này.
