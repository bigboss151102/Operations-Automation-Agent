# OpsPilot: Tổng quan nghiệp vụ

## Bối cảnh

**Công ty:** một công ty thương mại điện tử **DTC** (Direct-to-Consumer) hư cấu, tự bán hàng cho người tiêu dùng qua website riêng, có cả gói **subscription** (đăng ký mua định kỳ).

**Người dùng hệ thống:** đội **Customer Support và Operations**, mỗi ngày nhận rất nhiều yêu cầu từ khách:

- Đơn bị giao trễ, bị mất
- Đơn bị huỷ, muốn đổi địa chỉ
- Đòi hoàn tiền (refund)
- Lỗi subscription (thanh toán thất bại, bị tạm dừng…)

## Vấn đề nghiệp vụ

Hiện tại, với mỗi yêu cầu, nhân viên phải làm thủ công:

1. Đọc tin nhắn, hiểu khách muốn gì
2. Mở nhiều hệ thống để tra: đơn hàng, khách hàng, ticket cũ, subscription
3. Tự đánh giá mức độ nghiêm trọng (mỗi người đánh giá một kiểu)
4. Kiểm tra xem đã có ticket cho việc này chưa, để tránh tạo trùng
5. Quyết định làm gì tiếp: tạo ticket, báo đội vận hành, hoàn tiền…
6. Soạn phản hồi cho khách

Cách làm này **chậm, lặp lại, thiếu nhất quán**. Nhưng giao hẳn cho AI tự làm thì **nguy hiểm**:

- AI có thể **bịa dữ liệu**, ví dụ nói đơn đang giao trong khi đơn không tồn tại.
- AI có thể **tự hoàn tiền sai**, gây thiệt hại tài chính trực tiếp.
- AI có thể **gửi tin sai cho khách**, ví dụ hứa hoàn tiền khi chưa được duyệt.

## Giải pháp: OpsPilot

OpsPilot làm việc như **một nhân viên mới chuẩn bị hồ sơ cho sếp**: làm hết phần tra cứu và phân tích, làm các việc nhỏ an toàn, còn việc liên quan đến tiền thì **đưa lên người có thẩm quyền quyết**.

### Ví dụ một case thực tế (Scenario 2)

> Khách: *"Đơn ORD-1007 của tôi trễ 15 ngày rồi, tôi muốn hoàn tiền."*

| Bước | OpsPilot làm gì |
|---|---|
| 1. Hiểu yêu cầu | Khách báo giao trễ và muốn refund |
| 2. Tra cứu | Đơn ORD-1007 của khách Alex Johnson, $249.99, dự kiến giao 25/09, chưa giao; chưa có ticket nào |
| 3. Bằng chứng | "Đơn đang ở trạng thái trễ, đã quá ngày giao dự kiến 15 ngày" (tính từ dữ liệu, không lấy theo lời khách) |
| 4. Mức độ | **HIGH**: khách đòi refund, trễ hơn 7 ngày |
| 5. Tự làm ngay | Tạo ticket hỗ trợ, báo đội vận hành, soạn nháp thư trả lời khách |
| 6. Dừng lại xin duyệt | **Refund $249.99 → chờ quản lý duyệt** |
| 7. Trả lời khách | Chatbot trả lời: "Hi Alex, … your refund request is being reviewed by our team…" (không bao giờ hứa hoàn tiền) |
| 8. Báo cáo cho đội | Toàn bộ phân tích được gửi vào channel Slack của đội vận hành, tag người phụ trách |

Quản lý bấm **Approve** trên trang **Operation Admin** thì hệ thống mới thực hiện refund (ở dạng giả lập), kết quả được trả lời ngay trong thread Slack, và chatbot nhắn lại cho khách (kèm mã refund). Bấm **Reject** thì không hoàn tiền; chatbot báo khách là nhân viên sẽ liên hệ lại. Tin nhắn này dùng mẫu cố định, không do AI viết, vì nó nói về tiền.

## Luật nghiệp vụ (đã chốt)

| Luật | Ý nghĩa nghiệp vụ |
|---|---|
| Chỉ refund cần người duyệt | Mọi quyết định liên quan đến tiền đều do con người chịu trách nhiệm, bất kể số tiền |
| Trả lời khách an toàn | Chatbot trả lời như người thật, nhưng mọi câu trả lời đều qua bộ lọc nội dung: không bao giờ hứa hoàn tiền/bồi thường, không lộ thông tin nội bộ |
| Báo cáo mọi case cho đội | Toàn bộ phân tích được gửi vào Slack và tag người phụ trách |
| Không tạo ticket trùng | Đã có ticket đang mở thì báo lại cho đội vận hành, tránh 2 người xử lý cùng một việc |
| Thiếu thông tin thì hỏi lại | Không có mã đơn thì AI tự hỏi khách bằng lời của nó, không đoán; khách trả lời thì AI tiếp tục với đủ ngữ cảnh |
| Không bịa dữ liệu | Đơn không tồn tại thì nói thẳng "không tìm thấy"; AI không được tra cứu một mã đơn mà khách chưa từng ghi |
| Đơn giá trị cao (từ $500) | Ticket và thông báo được đặt mức `critical`, mức độ nghiêm trọng là CRITICAL; đội vận hành được báo ngay |
| Mức độ do luật quyết định | AI chỉ hiểu khách muốn gì; LOW/MEDIUM/HIGH/CRITICAL do code tính từ dữ liệu, nên nhất quán giữa các case |

Tinh thần chung của spec: **"When uncertain, do less rather than more."** Khi không chắc chắn thì làm ít đi, chứ không làm liều.

## Ai được lợi

- **Nhân viên CS:** không phải mở nhiều hệ thống, nhận sẵn hồ sơ gồm tóm tắt, bằng chứng và thư nháp.
- **Trưởng nhóm vận hành:** được cảnh báo ngay với case nghiêm trọng, chỉ phải duyệt những việc thật sự cần (refund).
- **Khách hàng:** được phản hồi nhanh hơn và nhất quán hơn.
- **Công ty:** kiểm soát rủi ro tài chính; mọi quyết định đều có log và trace trên LangSmith để truy vết.

## Bản chất của đề bài

Đây là **bài test tuyển Senior AI Developer**, làm trong 2–4 giờ. Phần business chỉ là bối cảnh. Thứ được chấm là **cách thiết kế một AI agent đáng tin cậy**:

| Tiêu chí | Tỉ trọng | Câu hỏi reviewer đặt ra |
|---|---|---|
| Architecture | 25% | Phần AI suy luận và phần luật nghiệp vụ có tách bạch không? |
| Reliability | 25% | Thiếu dữ liệu, sai mã đơn, AI trả lời lỗi thì hệ thống có xử lý an toàn không? |
| Agent Design | 20% | Agent có chọn đúng tool, suy luận đúng, trả output có cấu trúc không? |
| Guardrails | 20% | Có chặn được hành động rủi ro và có bước con người duyệt không? |
| Code Quality | 10% | Code có đơn giản, dễ đọc, dễ test không? |

Thông điệp reviewer cần thấy sau vài phút xem demo (spec §30):

> *"Developer này biết xây AI agent biết suy luận trên dữ liệu vận hành, dùng tool, đề xuất hành động, tự làm việc an toàn, và **biết dừng lại** khi việc đó rủi ro hoặc không chắc chắn."*

**Những thứ chỉ giả lập, không làm thật:** Slack, hoàn tiền thật, database thật (dùng file JSON), đăng nhập và phân quyền. Các phần này được trình bày trong [README](../README.md), mục "Production Improvements".
