<article>
URL: {{url}}
Tiêu đề: {{title}}
Chuyên mục: {{categories}}
Tóm tắt: {{excerpt}}
Các đề mục: {{headings}}
Nội dung:
{{content}}
</article>

<approved_claims>
{{approved_claims}}
</approved_claims>

Hãy tạo gói nội dung mạng xã hội từ bài viết trên và trả về đúng JSON theo schema.

1. analysis
- topic: chủ đề bài, tối đa 12 từ.
- audience: nhóm người đọc chính (ví dụ: "ba mẹ có con 1–6 tuổi").
- key_points: đúng 3 ý quan trọng nhất của bài gốc, mỗi ý tối đa 20 từ.
- suitable_for_social, reason: bài có phù hợp đăng mạng xã hội không và vì sao.

2. facebook
- hook: 1 câu mở đầu tối đa 15 từ, chạm vào mối quan tâm thực tế của người đọc (câu hỏi hoặc tình huống quen thuộc).
- body: 80–150 từ theo thứ tự: nêu vấn đề → 3 ý chính, mỗi ý một dòng bắt đầu bằng "✅" → 1 câu dẫn dắt đọc tiếp. Không chèn đường link (hệ thống tự chèn link có UTM). Nếu bài nhắc sản phẩm, chỉ dùng công dụng trong <approved_claims> và kết thúc bằng câu cảnh báo bắt buộc.
- cta: 1 câu mời đọc bài đầy đủ trên website.
- hashtags: 3–5 hashtag tiếng Việt không dấu, viết liền, luôn có #Doppelherz.

3. pinterest
- title: tối đa 90 ký tự, chứa cụm từ người Việt hay tìm kiếm (ví dụ "cách tăng sức đề kháng cho trẻ"), không emoji.
- description: 250–450 ký tự, 2–3 câu tự nhiên chứa 2–3 từ khóa, kết bằng lời mời xem hướng dẫn chi tiết. Không hashtag.
- alt_text: tối đa 300 ký tự, mô tả khách quan ảnh minh họa cho người khiếm thị dựa trên chủ đề; không bịa chi tiết không chắc chắn.
- overlay_headline: tối đa 8 từ để in lên ảnh ghim.
- board: chọn đúng 1 bảng trong danh sách: {{boards}}.
