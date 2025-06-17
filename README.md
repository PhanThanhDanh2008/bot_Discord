# 💰 BOT QUẢN LÝ TÀI CHÍNH - DISCORD

**BOT QUẢN LÝ TÀI CHÍNH** là một chatbot hoạt động trên Discord, giúp bạn theo dõi thu chi cá nhân, đặt mục tiêu tiết kiệm và nhận thông tin tài chính theo cách trực quan nhất, ngay trong khi bạn đang chat với bạn bè.

> 👨‍💻 Dev: **Phan Thành Danh**
> 🔧 Viết bằng: Python 3 + SQLite
> 🪙 Tích hợp trực tiếp với Discord App

---

## ✨ TÍNH NĂNG

* ✅ Quản lý **thu nhập** và **chi tiêu** dễ dàng
* 📈 Đặt **mục tiêu tiết kiệm**, theo dõi tiến độ
* 📆 Xem **lịch sử giao dịch** theo ngày
* 📊 Thống kê **thu/chi theo tuần & tháng**
* 🔍 Hiển thị số dư hiện tại + % đạt được mục tiêu

---

## 🚀 CÁCH DÙNG CÁC LỆNH

| Lệnh                       | Mô tả                         |
| -------------------------- | ----------------------------- |
| `/help`                    | Xem hướng dẫn sử dụng bot     |
| `/balance`                 | Xem số dư hiện tại            |
| `/add [số tiền] [mô tả]`   | Thêm thu nhập                 |
| `/spend [số tiền] [mô tả]` | Ghi chi tiêu                  |
| `/goal [số tiền]`          | Đặt hoặc xem mục tiêu         |
| `/history`                 | Lịch sử 10 giao dịch gần nhất |
| `/stats`                   | Thống kê thu chi tuần/tháng   |

---

## 🔧 CÀI ĐẶT & CHẠY BOT

### Bước 1: Cài Python

* Tải Python từ [https://python.org](https://python.org)

### Bước 2: Cài thư viện

```bash
pip install discord.py
```

### Bước 3: Cấu hình token

* Mở file `bot.py`
* Sửa dòng cuối:

```python
bot.run('YOUR_BOT_TOKEN')
```

### Bước 4: Chạy bot

```bash
python bot.py
```

Hoặc click chuột vào file `bot.bat`

---

## 🗂 CẤU TRÚC THƯ MỤC

```
📁 Bot_TaiChinh/
├── bot.py           # Code chính
├── bot.bat          # File khởi động nhanh Windows
├── finance_bot.db   # CSDL SQLite
├── README.md        # File mô tả
```

---

## 🙋‍♂️ TÁC GIẢ & BẢN QUYỀN

**Dev:** Phan Thành Danh
✨ Mong muốn giúp bạn trẻ Việt quản lý tài chính dễ hiểu nhất
📫 Email: *[phanthanhdanh7108@gmail.com](mailto:phanthanhdanh7108@gmail.com)*

---

> ✨ *Số tiền là vô hồn. Biết quản lý mới là triệu phúc.*
