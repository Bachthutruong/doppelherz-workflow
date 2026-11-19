# Doppelherz Content Workflow (Tiếng Việt)

[English](README.md) · **[Bản chạy thật](https://doppelherz-workflow.jiudi.cloud)** · **[Bài làm đầy đủ (PDF)](docs/report/Bai_test_QLDA_AI_Claude_Vu_Duy_Bach.pdf)**

Robot AI biến mỗi bài viết mới trên **doppelherz.vn** thành một bài Facebook và một ghim Pinterest: **Claude** viết, robot kiểm duyệt theo quy định quảng cáo thực phẩm bảo vệ sức khỏe (TPBVSK), con người duyệt, robot xếp lịch vào khung giờ vàng và lập báo cáo tuần.

Đây là sản phẩm chạy thật cho bài test vị trí **Quản lý dự án AI Claude** tại Doppelherz Việt Nam. Hệ thống chạy ở chế độ thử, không đăng lên fanpage thật, và không phải hệ thống chính thức của Doppelherz.

## Luồng xử lý 12 bước

1. WordPress đăng bài → plugin gửi webhook.
2. n8n kích hoạt (dự phòng quét mỗi 15 phút).
3. Robot đọc bài qua REST API.
4. Tra sổ XNQC — công dụng được phép của 36 sản phẩm, lấy tự động từ WooCommerce.
5. Claude viết bản Facebook + ghim Pinterest (đầu ra JSON theo schema).
6. Kiểm duyệt 2 lớp: bộ luật R1–R6 rồi AI pháp chế; câu vi phạm khóa nút Duyệt.
7. Render ảnh ghim 2:3, thẻ 1200×630, gắn UTM, đưa vào hàng chờ duyệt.
8. Biên tập viên duyệt, sửa hoặc từ chối kèm góp ý (Claude viết lại).
9. Xếp lịch: Facebook 11:30 · 20:30, Pinterest 13:00 · 21:00, tối đa 2 bài/ngày/kênh.
10. Đăng qua Graph API v27.0 và Pinterest API v5 (chế độ thử: ghi payload).
11. Thu số liệu hiển thị, tương tác, lượt nhấp.
12. 8:00 thứ Hai: n8n gọi báo cáo tuần, gửi Telegram.

## Chạy nhanh

```bash
git clone https://github.com/Bachthutruong/doppelherz-workflow.git
cd doppelherz-workflow
make install && make test   # cài đặt + 20 bài kiểm thử
make demo                   # nạp bài thật từ doppelherz.vn (chế độ thử)
make serve                  # http://127.0.0.1:8000
```

Bật Claude: điền `ANTHROPIC_API_KEY` vào `.env`. Chạy cả robot và n8n: `docker compose up -d --build`.

## Tài liệu

| Tài liệu | Nội dung |
| --- | --- |
| [docs/architecture.md](docs/architecture.md) | Kiến trúc, mô hình dữ liệu, quyết định thiết kế |
| [docs/compliance.md](docs/compliance.md) | Bộ luật tuân thủ R1–R6, sổ XNQC |
| [docs/api.md](docs/api.md) | Endpoint cho n8n, webhook WordPress |
| [docs/deployment.md](docs/deployment.md) | Triển khai Docker và VPS (systemd, nginx, n8n) |
| [docs/prompts.md](docs/prompts.md) | Bộ prompt P0–P4 |
| [docs/report/](docs/report) | Bài làm đầy đủ (PDF) |

## Tác giả

**Vu Duy Bach** · [linkedin.com/in/bachvd](https://linkedin.com/in/bachvd) · vuduybachvp@gmail.com · Giấy phép [MIT](LICENSE).
