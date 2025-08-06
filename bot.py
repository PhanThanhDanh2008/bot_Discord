import discord
from discord.ext import commands, tasks
import sqlite3
import asyncio
import json
import matplotlib.pyplot as plt
import io
import base64
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import logging

# ==== CẤU HÌNH BOT ====
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
bot = commands.Bot(command_prefix=['/', '!'], intents=intents, help_command=None)

# ==== LOGGING ====
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==== CẤU HÌNH ====
CONFIG = {
    'CURRENCY': 'VND',
    'BACKUP_INTERVAL': 3600,  # 1 giờ
    'MAX_TRANSACTIONS_DISPLAY': 15,
    'CHART_WIDTH': 12,
    'CHART_HEIGHT': 8
}

# ==== TẠO DATABASE NÂNG CẤP ====
def init_database():
    conn = sqlite3.connect('finance_bot.db')
    cursor = conn.cursor()
    
    # Bảng users nâng cấp
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            balance INTEGER DEFAULT 0,
            goal INTEGER DEFAULT 0,
            monthly_budget INTEGER DEFAULT 0,
            savings_goal INTEGER DEFAULT 0,
            currency TEXT DEFAULT 'VND',
            timezone TEXT DEFAULT 'Asia/Ho_Chi_Minh',
            notifications BOOLEAN DEFAULT 1,
            created_date TEXT,
            last_active TEXT
        )
    ''')
    
    # Bảng transactions nâng cấp
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount INTEGER,
            type TEXT,
            category TEXT,
            description TEXT,
            date TEXT,
            recurring BOOLEAN DEFAULT 0,
            recurring_interval INTEGER DEFAULT 0,
            tags TEXT,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    # Bảng categories
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            type TEXT,
            color TEXT,
            icon TEXT,
            budget_limit INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    # Bảng budgets
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            category TEXT,
            amount INTEGER,
            period TEXT,
            start_date TEXT,
            end_date TEXT,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    # Bảng savings_goals
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS savings_goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            target_amount INTEGER,
            current_amount INTEGER DEFAULT 0,
            deadline TEXT,
            description TEXT,
            created_date TEXT,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    # Bảng notifications
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            message TEXT,
            type TEXT,
            read BOOLEAN DEFAULT 0,
            created_date TEXT,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    # Thêm categories mặc định
    cursor.execute('SELECT COUNT(*) FROM categories')
    if cursor.fetchone()[0] == 0:
        default_categories = [
            ('🍔', 'Ăn uống', 'expense', '#FF6B6B'),
            ('🚗', 'Giao thông', 'expense', '#4ECDC4'),
            ('🏠', 'Nhà cửa', 'expense', '#45B7D1'),
            ('💊', 'Y tế', 'expense', '#96CEB4'),
            ('🎮', 'Giải trí', 'expense', '#FFEAA7'),
            ('👕', 'Quần áo', 'expense', '#DDA0DD'),
            ('📚', 'Giáo dục', 'expense', '#98D8C8'),
            ('💰', 'Lương', 'income', '#00B894'),
            ('💼', 'Kinh doanh', 'income', '#FDCB6E'),
            ('🎁', 'Quà tặng', 'income', '#E17055')
        ]
        for icon, name, cat_type, color in default_categories:
            cursor.execute('INSERT INTO categories (user_id, name, type, color, icon) VALUES (0, ?, ?, ?, ?)',
                         (name, cat_type, color, icon))
    
    conn.commit()
    conn.close()

# ==== HÀM PHỤ NÂNG CÂP ====
def format_money(amount, currency='VND'):
    if currency == 'VND':
        return f"{amount:,} ₫".replace(",", ".")
    return f"{amount:,} {currency}"

def get_or_create_user(user_id, username=None):
    conn = sqlite3.connect('finance_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    if not user:
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('''INSERT INTO users 
                         (user_id, username, balance, goal, created_date, last_active) 
                         VALUES (?, ?, 0, 0, ?, ?)''',
                       (user_id, username, now, now))
        conn.commit()
    else:
        # Cập nhật last_active
        cursor.execute('UPDATE users SET last_active = ? WHERE user_id = ?',
                       (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user_id))
        conn.commit()
    conn.close()

def get_categories(user_id, cat_type=None):
    conn = sqlite3.connect('finance_bot.db')
    cursor = conn.cursor()
    if cat_type:
        cursor.execute('SELECT * FROM categories WHERE (user_id = ? OR user_id = 0) AND type = ?', (user_id, cat_type))
    else:
        cursor.execute('SELECT * FROM categories WHERE user_id = ? OR user_id = 0', (user_id,))
    categories = cursor.fetchall()
    conn.close()
    return categories

async def create_chart(data, chart_type='bar', title='Biểu đồ'):
    """Tạo biểu đồ thống kê"""
    try:
        plt.style.use('dark_background')
        fig, ax = plt.subplots(figsize=(CONFIG['CHART_WIDTH'], CONFIG['CHART_HEIGHT']))
        
        if chart_type == 'pie' and data:
            labels = [item[0] for item in data]
            sizes = [item[1] for item in data]
            colors = plt.cm.Set3(range(len(labels)))
            
            wedges, texts, autotexts = ax.pie(sizes, labels=labels, autopct='%1.1f%%', colors=colors)
            for autotext in autotexts:
                autotext.set_color('white')
                autotext.set_fontweight('bold')
        
        elif chart_type == 'bar' and data:
            labels = [item[0] for item in data]
            values = [item[1] for item in data]
            colors = plt.cm.viridis(range(len(labels)))
            
            bars = ax.bar(labels, values, color=colors)
            ax.set_ylabel('Số tiền (₫)')
            plt.xticks(rotation=45, ha='right')
            
            # Thêm giá trị trên cột
            for bar, value in zip(bars, values):
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height,
                       f'{value:,.0f}₫', ha='center', va='bottom')
        
        ax.set_title(title, fontsize=16, fontweight='bold', color='white')
        plt.tight_layout()
        
        # Lưu vào buffer
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight', facecolor='#2C2F33')
        buffer.seek(0)
        plt.close()
        
        return discord.File(buffer, filename='chart.png')
    except Exception as e:
        logger.error(f"Error creating chart: {e}")
        return None

def create_progress_bar(current, target, length=20):
    """Tạo thanh tiến trình"""
    if target <= 0:
        return "▱" * length + " 0%"
    
    progress = min(current / target, 1.0)
    filled = int(progress * length)
    bar = "▰" * filled + "▱" * (length - filled)
    percentage = progress * 100
    return f"{bar} {percentage:.1f}%"

# ==== SỰ KIỆN BOT ====
@bot.event
async def on_ready():
    print(f'🚀 {bot.user} đã online với {len(bot.guilds)} servers!')
    init_database()
    daily_summary.start()
    backup_database.start()

@bot.event 
async def on_guild_join(guild):
    logger.info(f"Bot joined guild: {guild.name} ({guild.id})")

# ==== TASKS ĐỊNH KỲ ====
@tasks.loop(hours=24)
async def daily_summary():
    """Gửi tóm tắt hàng ngày"""
    await bot.wait_until_ready()
    # Implement daily summary logic here

@tasks.loop(seconds=CONFIG['BACKUP_INTERVAL'])
async def backup_database():
    """Backup database định kỳ"""
    await bot.wait_until_ready()
    # Implement backup logic here

# ==== LỆNH HELP NÂNG CÂP ====
@bot.command(name='help')
async def help_command(ctx):
    embeds = []
    
    # Trang 1: Lệnh cơ bản
    embed1 = discord.Embed(
        title="🤖 Finance Bot - Hướng Dẫn Sử Dụng", 
        description="Bot quản lý tài chính cá nhân toàn diện",
        color=0x00ff41
    )
    embed1.add_field(
        name="💰 **Lệnh Cơ Bản**",
        value="`/balance` - Xem số dư và tổng quan\n"
              "`/add [số tiền] [danh mục] [mô tả]` - Thêm thu nhập\n"
              "`/spend [số tiền] [danh mục] [mô tả]` - Ghi nhận chi tiêu\n"
              "`/transfer [số tiền] [@user]` - Chuyển tiền",
        inline=False
    )
    embed1.add_field(
        name="🎯 **Mục Tiêu & Ngân Sách**",
        value="`/goal [số tiền]` - Đặt mục tiêu tiết kiệm\n"
              "`/budget [danh mục] [số tiền]` - Đặt ngân sách\n"
              "`/savings [tên] [số tiền] [deadline]` - Tạo mục tiêu tiết kiệm",
        inline=False
    )
    embed1.set_footer(text="Trang 1/3 • Dùng /help2 để xem tiếp")
    embeds.append(embed1)
    
    # Trang 2: Thống kê và báo cáo
    embed2 = discord.Embed(
        title="📊 Thống Kê & Báo Cáo",
        color=0x3498db
    )
    embed2.add_field(
        name="📈 **Phân Tích**",
        value="`/stats` - Thống kê chi tiết\n"
              "`/chart [type]` - Biểu đồ (pie/bar)\n"
              "`/report [period]` - Báo cáo (week/month/year)\n"
              "`/compare [period1] [period2]` - So sánh",
        inline=False
    )
    embed2.add_field(
        name="📋 **Lịch Sử**",
        value="`/history [days]` - Lịch sử giao dịch\n"
              "`/search [keyword]` - Tìm kiếm giao dịch\n"
              "`/category` - Quản lý danh mục",
        inline=False
    )
    embed2.set_footer(text="Trang 2/3 • Dùng /help3 để xem tiếp")
    embeds.append(embed2)
    
    # Trang 3: Nâng cao
    embed3 = discord.Embed(
        title="⚙️ Tính Năng Nâng Cao",
        color=0x9b59b6
    )
    embed3.add_field(
        name="🔔 **Thông Báo & Cài Đặt**",
        value="`/notify [on/off]` - Bật/tắt thông báo\n"
              "`/settings` - Cài đặt cá nhân\n"
              "`/export` - Xuất dữ liệu\n"
              "`/import` - Nhập dữ liệu",
        inline=False
    )
    embed3.add_field(
        name="🎮 **Gamification**",
        value="`/achievements` - Thành tích\n"
              "`/leaderboard` - Bảng xếp hạng\n"
              "`/challenge` - Thử thách tiết kiệm",
        inline=False
    )
    embed3.add_field(
        name="📝 **Ví Dụ**",
        value="`/add 5000000 Lương Lương tháng 12`\n"
              "`/spend 150000 Ăn uống Trà sữa với bạn`\n"
              "`/goal 20000000`\n"
              "`/budget Ăn uống 2000000`",
        inline=False
    )
    embed3.set_footer(text="Trang 3/3 • Cảm ơn bạn đã sử dụng!")
    embeds.append(embed3)
    
    await ctx.send(embed=embeds[0])

@bot.command(name='help2')
async def help2_command(ctx):
    embed = discord.Embed(title="📊 Thống Kê & Báo Cáo", color=0x3498db)
    embed.add_field(
        name="📈 **Phân Tích**",
        value="`/stats` - Thống kê chi tiết\n"
              "`/chart [type]` - Biểu đồ (pie/bar)\n"
              "`/report [period]` - Báo cáo (week/month/year)",
        inline=False
    )
    embed.add_field(
        name="📋 **Lịch Sử**",
        value="`/history [days]` - Lịch sử giao dịch\n"
              "`/search [keyword]` - Tìm kiếm giao dịch\n"
              "`/category` - Quản lý danh mục",
        inline=False
    )
    await ctx.send(embed=embed)

# ==== LỆNH BALANCE NÂNG CÂP ====
@bot.command(name='balance', aliases=['bal', 'b'])
async def balance(ctx):
    user_id = ctx.author.id
    get_or_create_user(user_id, ctx.author.display_name)
    
    conn = sqlite3.connect('finance_bot.db')
    cursor = conn.cursor()
    
    # Lấy thông tin user
    cursor.execute('SELECT balance, goal, monthly_budget FROM users WHERE user_id = ?', (user_id,))
    user_data = cursor.fetchone()
    
    # Thống kê tháng hiện tại
    current_month = datetime.now().strftime('%Y-%m')
    cursor.execute('''
        SELECT type, SUM(amount) 
        FROM transactions 
        WHERE user_id = ? AND date LIKE ? 
        GROUP BY type
    ''', (user_id, f'{current_month}%'))
    month_stats = dict(cursor.fetchall())
    
    # Lấy savings goals
    cursor.execute('SELECT name, target_amount, current_amount FROM savings_goals WHERE user_id = ?', (user_id,))
    savings_goals = cursor.fetchall()
    
    conn.close()

    balance_amount, goal_amount, monthly_budget = user_data
    monthly_income = month_stats.get('income', 0)
    monthly_expense = month_stats.get('expense', 0)
    monthly_net = monthly_income - monthly_expense
    
    # Tạo embed chính
    embed = discord.Embed(
        title=f"💎 Tổng Quan Tài Chính - {ctx.author.display_name}",
        color=0x00ff41 if balance_amount >= 0 else 0xff4757
    )
    
    # Số dư chính
    embed.add_field(
        name="💰 **Số Dư Hiện Tại**",
        value=f"**{format_money(balance_amount)}**",
        inline=True
    )
    
    # Mục tiêu
    if goal_amount > 0:
        progress = min((balance_amount / goal_amount) * 100, 100)
        progress_bar = create_progress_bar(balance_amount, goal_amount)
        embed.add_field(
            name="🎯 **Mục Tiêu**",
            value=f"{format_money(goal_amount)}\n{progress_bar}",
            inline=True
        )
    
    # Thống kê tháng
    embed.add_field(
        name="📊 **Tháng Này**",
        value=f"Thu: +{format_money(monthly_income)}\n"
              f"Chi: -{format_money(monthly_expense)}\n"
              f"Ròng: {format_money(monthly_net)}",
        inline=True
    )
    
    # Ngân sách
    if monthly_budget > 0:
        budget_used = (monthly_expense / monthly_budget) * 100
        budget_bar = create_progress_bar(monthly_expense, monthly_budget)
        embed.add_field(
            name="💳 **Ngân Sách Tháng**",
            value=f"{format_money(monthly_budget)}\n{budget_bar}\n"
                  f"Đã dùng: {budget_used:.1f}%",
            inline=False
        )
    
    # Mục tiêu tiết kiệm
    if savings_goals:
        savings_text = ""
        for name, target, current in savings_goals[:3]:  # Hiển thị tối đa 3
            progress = (current / target) * 100 if target > 0 else 0
            savings_text += f"**{name}**: {format_money(current)}/{format_money(target)} ({progress:.1f}%)\n"
        embed.add_field(
            name="🏦 **Mục Tiêu Tiết Kiệm**",
            value=savings_text,
            inline=False
        )
    
    # Footer với thời gian
    embed.set_footer(
        text=f"Cập nhật: {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        icon_url=ctx.author.avatar.url if ctx.author.avatar else None
    )
    
    await ctx.send(embed=embed)

# ==== LỆNH ADD NÂNG CÂP ====
@bot.command(name='add', aliases=['income', '+'])
async def add(ctx, amount: int, category: str = "Khác", *, description: str = "Không có mô tả"):
    if amount <= 0:
        await ctx.send("❌ Số tiền phải lớn hơn 0!")
        return

    user_id = ctx.author.id
    get_or_create_user(user_id, ctx.author.display_name)
    
    # Kiểm tra category có tồn tại không
    categories = get_categories(user_id, 'income')
    category_names = [cat[2] for cat in categories]  # cat[2] là tên category
    
    if category not in category_names and category != "Khác":
        category = "Khác"  # Fallback to default
    
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    conn = sqlite3.connect('finance_bot.db')
    cursor = conn.cursor()
    
    # Cập nhật số dư
    cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
    
    # Thêm transaction
    cursor.execute('''
        INSERT INTO transactions (user_id, amount, type, category, description, date) 
        VALUES (?, ?, "income", ?, ?, ?)
    ''', (user_id, amount, category, description, now))
    
    # Lấy số dư mới
    cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
    new_balance = cursor.fetchone()[0]
    
    conn.commit()
    conn.close()

    # Tạo embed đẹp
    embed = discord.Embed(
        title="✅ Thu Nhập Đã Được Ghi Nhận",
        description="Giao dịch được thêm thành công!",
        color=0x00ff41
    )
    
    embed.add_field(name="💵 **Số Tiền**", value=f"+{format_money(amount)}", inline=True)
    embed.add_field(name="📂 **Danh Mục**", value=category, inline=True)
    embed.add_field(name="📝 **Mô Tả**", value=description, inline=True)
    embed.add_field(name="💰 **Số Dư Mới**", value=format_money(new_balance), inline=False)
    
    embed.set_footer(text=f"ID: {ctx.author.id} • {now}")
    embed.set_thumbnail(url="https://cdn-icons-png.flaticon.com/512/1828/1828884.png")
    
    await ctx.send(embed=embed)

# ==== LỆNH SPEND NÂNG CÂP ====
@bot.command(name='spend', aliases=['expense', 'pay', '-'])
async def spend(ctx, amount: int, category: str = "Khác", *, description: str = "Không có mô tả"):
    if amount <= 0:
        await ctx.send("❌ Số tiền phải lớn hơn 0!")
        return

    user_id = ctx.author.id
    get_or_create_user(user_id, ctx.author.display_name)

    conn = sqlite3.connect('finance_bot.db')
    cursor = conn.cursor()
    
    # Kiểm tra số dư
    cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
    current_balance = cursor.fetchone()[0]

    if current_balance < amount:
        embed = discord.Embed(
            title="❌ Không Đủ Số Dư",
            description=f"Bạn cần thêm {format_money(amount - current_balance)}",
            color=0xff4757
        )
        embed.add_field(name="Số dư hiện tại", value=format_money(current_balance), inline=True)
        embed.add_field(name="Số tiền cần", value=format_money(amount), inline=True)
        await ctx.send(embed=embed)
        return

    # Kiểm tra category và budget warning
    categories = get_categories(user_id, 'expense')
    category_names = [cat[2] for cat in categories]
    
    if category not in category_names and category != "Khác":
        category = "Khác"
    
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Cập nhật số dư
    cursor.execute('UPDATE users SET balance = balance - ? WHERE user_id = ?', (amount, user_id))
    
    # Thêm transaction
    cursor.execute('''
        INSERT INTO transactions (user_id, amount, type, category, description, date) 
        VALUES (?, ?, "expense", ?, ?, ?)
    ''', (user_id, amount, category, description, now))
    
    # Lấy số dư mới
    cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
    new_balance = cursor.fetchone()[0]
    
    # Kiểm tra ngân sách category
    current_month = datetime.now().strftime('%Y-%m')
    cursor.execute('''
        SELECT SUM(amount) FROM transactions 
        WHERE user_id = ? AND category = ? AND type = "expense" AND date LIKE ?
    ''', (user_id, category, f'{current_month}%'))
    category_spent = cursor.fetchone()[0] or 0
    
    conn.commit()
    conn.close()

    # Tạo embed
    embed = discord.Embed(
        title="💸 Chi Tiêu Đã Được Ghi Nhận",
        description="Giao dịch được ghi nhận thành công!",
        color=0xff6b6b
    )
    
    embed.add_field(name="💰 **Số Tiền**", value=f"-{format_money(amount)}", inline=True)
    embed.add_field(name="📂 **Danh Mục**", value=category, inline=True)
    embed.add_field(name="📝 **Mô Tả**", value=description, inline=True)
    embed.add_field(name="💳 **Số Dư Còn Lại**", value=format_money(new_balance), inline=False)
    
    # Warning nếu chi tiêu nhiều
    if category_spent > 1000000:  # 1M VND
        embed.add_field(
            name="⚠️ **Cảnh Báo**",
            value=f"Bạn đã chi {format_money(category_spent)} cho **{category}** trong tháng này!",
            inline=False
        )
    
    embed.set_footer(text=f"ID: {ctx.author.id} • {now}")
    embed.set_thumbnail(url="https://cdn-icons-png.flaticon.com/512/1611/1611179.png")
    
    await ctx.send(embed=embed)

# ==== LỆNH CHART ====
@bot.command(name='chart', aliases=['graph'])
async def chart(ctx, chart_type: str = 'pie', period: str = 'month'):
    user_id = ctx.author.id
    get_or_create_user(user_id, ctx.author.display_name)
    
    conn = sqlite3.connect('finance_bot.db')
    cursor = conn.cursor()
    
    # Lấy dữ liệu theo period
    if period == 'month':
        current_period = datetime.now().strftime('%Y-%m')
        period_filter = f'{current_period}%'
        title = f"Chi Tiêu Theo Danh Mục - Tháng {current_period}"
    elif period == 'week':
        week_start = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        period_filter = None
        title = "Chi Tiêu Theo Danh Mục - 7 Ngày Qua"
    else:
        current_year = datetime.now().year
        period_filter = f'{current_year}%'
        title = f"Chi Tiêu Theo Danh Mục - Năm {current_year}"
    
    if period == 'week':
        cursor.execute('''
            SELECT category, SUM(amount) 
            FROM transactions 
            WHERE user_id = ? AND type = "expense" AND date >= ?
            GROUP BY category 
            ORDER BY SUM(amount) DESC
        ''', (user_id, week_start))
    else:
        cursor.execute('''
            SELECT category, SUM(amount) 
            FROM transactions 
            WHERE user_id = ? AND type = "expense" AND date LIKE ?
            GROUP BY category 
            ORDER BY SUM(amount) DESC
        ''', (user_id, period_filter))
    
    data = cursor.fetchall()
    conn.close()
    
    if not data:
        await ctx.send("📭 Không có dữ liệu để tạo biểu đồ.")
        return
    
    # Tạo biểu đồ
    chart_file = await create_chart(data, chart_type, title)
    
    if chart_file:
        embed = discord.Embed(
            title=f"📊 {title}",
            color=0x3498db
        )
        embed.set_image(url="attachment://chart.png")
        embed.set_footer(text=f"Tạo bởi {ctx.author.display_name}")
        await ctx.send(embed=embed, file=chart_file)
    else:
        await ctx.send("❌ Không thể tạo biểu đồ. Vui lòng thử lại sau.")

# ==== LỆNH STATS NÂNG CÂP ====
@bot.command(name='stats', aliases=['statistics'])
async def stats(ctx, period: str = 'month'):
    user_id = ctx.author.id
    get_or_create_user(user_id, ctx.author.display_name)
    
    conn = sqlite3.connect('finance_bot.db')
    cursor = conn.cursor()
    
    # Xác định khoảng thời gian
    if period == 'week':
        start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        title = "📊 Thống Kê 7 Ngày Qua"
        date_filter = "date >= ?"
        params = (user_id, start_date)
    elif period == 'year':
        current_year = datetime.now().year
        title = f"📊 Thống Kê Năm {current_year}"
        date_filter = "date LIKE ?"
        params = (user_id, f'{current_year}%')
    else:  # month
        current_month = datetime.now().strftime('%Y-%m')
        title = f"📊 Thống Kê Tháng {current_month}"
        date_filter = "date LIKE ?"
        params = (user_id, f'{current_month}%')
    
    # Lấy tổng thu chi
    cursor.execute(f'''
        SELECT type, SUM(amount), COUNT(*) 
        FROM transactions 
        WHERE user_id = ? AND {date_filter}
        GROUP BY type
    ''', params)
    summary = cursor.fetchall()
    
    # Lấy top categories
    cursor.execute(f'''
        SELECT category, SUM(amount), COUNT(*) 
        FROM transactions 
        WHERE user_id = ? AND type = "expense" AND {date_filter}
        GROUP BY category 
        ORDER BY SUM(amount) DESC 
        LIMIT 5
    ''', params)
    top_expenses = cursor.fetchall()
    
    cursor.execute(f'''
        SELECT category, SUM(amount), COUNT(*) 
        FROM transactions 
        WHERE user_id = ? AND type = "income" AND {date_filter}
        GROUP BY category 
        ORDER BY SUM(amount) DESC 
        LIMIT 5
    ''', params)
    top_income = cursor.fetchall()
    
    # Lấy giao dịch lớn nhất
    cursor.execute(f'''
        SELECT amount, category, description, date 
        FROM transactions 
        WHERE user_id = ? AND {date_filter}
        ORDER BY amount DESC 
        LIMIT 3
    ''', params)
    biggest_transactions = cursor.fetchall()
    
    conn.close()
    
    # Tạo embed
    embed = discord.Embed(title=title, color=0x6c5ce7)
    
    # Tóm tắt chung
    total_income = sum(row[1] for row in summary if row[0] == 'income')
    total_expense = sum(row[1] for row in summary if row[0] == 'expense')
    total_transactions = sum(row[2] for row in summary)
    net_amount = total_income - total_expense
    
    summary_text = f"""
    💰 **Thu nhập**: {format_money(total_income)}
    💸 **Chi tiêu**: {format_money(total_expense)}
    📈 **Ròng**: {format_money(net_amount)}
    🔢 **Giao dịch**: {total_transactions} lần
    """
    embed.add_field(name="💼 **Tổng Quan**", value=summary_text, inline=False)
    
    # Top chi tiêu
    if top_expenses:
        expense_text = ""
        for cat, amount, count in top_expenses[:3]:
            expense_text += f"**{cat}**: {format_money(amount)} ({count} lần)\n"
        embed.add_field(name="🔥 **Top Chi Tiêu**", value=expense_text, inline=True)
    
    # Top thu nhập
    if top_income:
        income_text = ""
        for cat, amount, count in top_income[:3]:
            income_text += f"**{cat}**: {format_money(amount)} ({count} lần)\n"
        embed.add_field(name="💎 **Top Thu Nhập**", value=income_text, inline=True)
    
    # Giao dịch lớn nhất
    if biggest_transactions:
        big_text = ""
        for amount, cat, desc, date in biggest_transactions[:2]:
            big_text += f"**{format_money(amount)}** - {cat}\n_{desc[:30]}..._\n"
        embed.add_field(name="🏆 **Giao Dịch Lớn Nhất**", value=big_text, inline=False)
    
    # Phân tích
    if total_income > 0:
        savings_rate = ((total_income - total_expense) / total_income) * 100
        if savings_rate > 20:
            analysis = "🎉 Tuyệt vời! Bạn tiết kiệm được nhiều."
        elif savings_rate > 10:
            analysis = "👍 Khá tốt! Tiếp tục duy trì."
        elif savings_rate > 0:
            analysis = "⚠️ Nên tiết kiệm nhiều hơn."
        else:
            analysis = "🚨 Chi tiêu vượt thu nhập!"
        
        embed.add_field(
            name="🔍 **Phân Tích**",
            value=f"Tỷ lệ tiết kiệm: {savings_rate:.1f}%\n{analysis}",
            inline=False
        )
    
    embed.set_footer(text=f"Cập nhật: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    await ctx.send(embed=embed)

# ==== LỆNH BUDGET ====
@bot.command(name='budget')
async def budget(ctx, category: str = None, amount: int = None):
    user_id = ctx.author.id
    get_or_create_user(user_id, ctx.author.display_name)
    
    conn = sqlite3.connect('finance_bot.db')
    cursor = conn.cursor()
    
    if category is None:
        # Hiển thị tất cả budgets
        current_month = datetime.now().strftime('%Y-%m')
        cursor.execute('''
            SELECT b.category, b.amount, COALESCE(SUM(t.amount), 0) as spent
            FROM budgets b
            LEFT JOIN transactions t ON b.category = t.category 
                AND t.user_id = b.user_id 
                AND t.type = "expense" 
                AND t.date LIKE ?
            WHERE b.user_id = ? AND b.period = "monthly"
            GROUP BY b.category, b.amount
        ''', (f'{current_month}%', user_id))
        budgets = cursor.fetchall()
        
        if not budgets:
            await ctx.send("📭 Bạn chưa đặt ngân sách nào. Dùng `/budget [danh mục] [số tiền]`")
            return
        
        embed = discord.Embed(title="💳 Ngân Sách Tháng Này", color=0x3498db)
        for cat, budget_amt, spent in budgets:
            percentage = (spent / budget_amt) * 100 if budget_amt > 0 else 0
            remaining = budget_amt - spent
            
            if percentage > 100:
                status = "🚨 Vượt ngân sách!"
                color_emoji = "🔴"
            elif percentage > 80:
                status = "⚠️ Sắp hết"
                color_emoji = "🟡"
            else:
                status = "✅ An toàn"
                color_emoji = "🟢"
            
            progress_bar = create_progress_bar(spent, budget_amt, 15)
            embed.add_field(
                name=f"{color_emoji} **{cat}**",
                value=f"Ngân sách: {format_money(budget_amt)}\n"
                      f"Đã chi: {format_money(spent)} ({percentage:.1f}%)\n"
                      f"Còn lại: {format_money(remaining)}\n"
                      f"{progress_bar}\n{status}",
                inline=True
            )
    
    elif amount is None:
        await ctx.send("❌ Vui lòng nhập số tiền ngân sách: `/budget [danh mục] [số tiền]`")
        return
    
    else:
        # Đặt budget mới
        if amount <= 0:
            await ctx.send("❌ Ngân sách phải lớn hơn 0!")
            return
        
        # Kiểm tra xem đã có budget cho category này chưa
        cursor.execute('SELECT amount FROM budgets WHERE user_id = ? AND category = ? AND period = "monthly"', 
                      (user_id, category))
        existing = cursor.fetchone()
        
        if existing:
            cursor.execute('UPDATE budgets SET amount = ? WHERE user_id = ? AND category = ? AND period = "monthly"', 
                          (amount, user_id, category))
            action = "cập nhật"
        else:
            start_date = datetime.now().replace(day=1).strftime('%Y-%m-%d')
            end_date = (datetime.now().replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
            cursor.execute('''
                INSERT INTO budgets (user_id, category, amount, period, start_date, end_date) 
                VALUES (?, ?, ?, "monthly", ?, ?)
            ''', (user_id, category, amount, start_date, end_date.strftime('%Y-%m-%d')))
            action = "đặt"
        
        conn.commit()
        
        embed = discord.Embed(
            title=f"💳 Đã {action} ngân sách",
            description=f"**{category}**: {format_money(amount)}/tháng",
            color=0x00ff41
        )
        
        # Kiểm tra chi tiêu hiện tại
        current_month = datetime.now().strftime('%Y-%m')
        cursor.execute('''
            SELECT COALESCE(SUM(amount), 0) 
            FROM transactions 
            WHERE user_id = ? AND category = ? AND type = "expense" AND date LIKE ?
        ''', (user_id, category, f'{current_month}%'))
        current_spent = cursor.fetchone()[0]
        
        if current_spent > 0:
            percentage = (current_spent / amount) * 100
            embed.add_field(
                name="📊 Tình hình hiện tại",
                value=f"Đã chi: {format_money(current_spent)} ({percentage:.1f}%)\n"
                      f"Còn lại: {format_money(amount - current_spent)}",
                inline=False
            )
    
    conn.close()
    await ctx.send(embed=embed)

# ==== LỆNH SAVINGS GOALS ====
@bot.command(name='savings', aliases=['save', 'goal_save'])
async def savings(ctx, action: str = "list", name: str = None, target: int = None, *, deadline: str = None):
    user_id = ctx.author.id
    get_or_create_user(user_id, ctx.author.display_name)
    
    conn = sqlite3.connect('finance_bot.db')
    cursor = conn.cursor()
    
    if action == "list" or action is None:
        # Hiển thị tất cả savings goals
        cursor.execute('SELECT * FROM savings_goals WHERE user_id = ? ORDER BY deadline ASC', (user_id,))
        goals = cursor.fetchall()
        
        if not goals:
            await ctx.send("📭 Bạn chưa có mục tiêu tiết kiệm nào. Dùng `/savings add [tên] [số tiền] [deadline]`")
            return
        
        embed = discord.Embed(title="🏦 Mục Tiêu Tiết Kiệm", color=0x27ae60)
        
        for goal in goals:
            goal_id, _, name, target_amt, current_amt, deadline, desc, created = goal
            progress = (current_amt / target_amt) * 100 if target_amt > 0 else 0
            remaining = target_amt - current_amt
            
            # Tính số ngày còn lại
            if deadline:
                try:
                    deadline_date = datetime.strptime(deadline, '%Y-%m-%d')
                    days_left = (deadline_date - datetime.now()).days
                    if days_left > 0:
                        deadline_text = f"⏰ Còn {days_left} ngày"
                    elif days_left == 0:
                        deadline_text = "⏰ Hôm nay!"
                    else:
                        deadline_text = f"⏰ Trễ {abs(days_left)} ngày"
                except:
                    deadline_text = f"⏰ {deadline}"
            else:
                deadline_text = "⏰ Không thời hạn"
            
            progress_bar = create_progress_bar(current_amt, target_amt, 15)
            
            embed.add_field(
                name=f"💎 **{name}**",
                value=f"Mục tiêu: {format_money(target_amt)}\n"
                      f"Đã có: {format_money(current_amt)} ({progress:.1f}%)\n"
                      f"Còn thiếu: {format_money(remaining)}\n"
                      f"{progress_bar}\n"
                      f"{deadline_text}",
                inline=True
            )
    
    elif action == "add":
        if not all([name, target, deadline]):
            await ctx.send("❌ Thiếu thông tin: `/savings add [tên] [số tiền] [deadline YYYY-MM-DD]`")
            return
        
        if target <= 0:
            await ctx.send("❌ Số tiền mục tiêu phải lớn hơn 0!")
            return
        
        # Validate deadline
        try:
            deadline_date = datetime.strptime(deadline, '%Y-%m-%d')
            if deadline_date <= datetime.now():
                await ctx.send("❌ Thời hạn phải là ngày trong tương lai!")
                return
        except ValueError:
            await ctx.send("❌ Format ngày không đúng! Dùng YYYY-MM-DD (ví dụ: 2024-12-31)")
            return
        
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('''
            INSERT INTO savings_goals (user_id, name, target_amount, current_amount, deadline, created_date) 
            VALUES (?, ?, ?, 0, ?, ?)
        ''', (user_id, name, target, deadline, now))
        
        conn.commit()
        
        embed = discord.Embed(
            title="🎯 Mục Tiêu Tiết Kiệm Mới",
            description=f"Đã tạo mục tiêu **{name}**",
            color=0x27ae60
        )
        embed.add_field(name="💰 Số tiền", value=format_money(target), inline=True)
        embed.add_field(name="📅 Thời hạn", value=deadline, inline=True)
        
        days_left = (deadline_date - datetime.now()).days
        embed.add_field(name="⏰ Thời gian", value=f"{days_left} ngày", inline=True)
        
    elif action == "deposit":
        if not all([name, target]):  # target được dùng làm amount deposit
            await ctx.send("❌ Thiếu thông tin: `/savings deposit [tên] [số tiền]`")
            return
        
        amount = target  # Rename for clarity
        if amount <= 0:
            await ctx.send("❌ Số tiền phải lớn hơn 0!")
            return
        
        # Kiểm tra goal có tồn tại không
        cursor.execute('SELECT * FROM savings_goals WHERE user_id = ? AND name = ?', (user_id, name))
        goal = cursor.fetchone()
        
        if not goal:
            await ctx.send(f"❌ Không tìm thấy mục tiêu tiết kiệm '{name}'")
            return
        
        goal_id, _, goal_name, target_amt, current_amt, deadline, desc, created = goal
        
        # Kiểm tra số dư
        cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
        balance = cursor.fetchone()[0]
        
        if balance < amount:
            await ctx.send(f"❌ Không đủ số dư! Số dư hiện tại: {format_money(balance)}")
            return
        
        # Cập nhật số dư và savings goal
        cursor.execute('UPDATE users SET balance = balance - ? WHERE user_id = ?', (amount, user_id))
        cursor.execute('UPDATE savings_goals SET current_amount = current_amount + ? WHERE id = ?', (amount, goal_id))
        
        # Thêm transaction
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('''
            INSERT INTO transactions (user_id, amount, type, category, description, date) 
            VALUES (?, ?, "expense", "Tiết kiệm", ?, ?)
        ''', (user_id, amount, f"Gửi tiết kiệm: {name}", now))
        
        conn.commit()
        
        # Lấy thông tin mới
        cursor.execute('SELECT current_amount FROM savings_goals WHERE id = ?', (goal_id,))
        new_amount = cursor.fetchone()[0]
        progress = (new_amount / target_amt) * 100
        
        embed = discord.Embed(
            title="🏦 Đã Gửi Tiết Kiệm",
            description=f"Gửi {format_money(amount)} vào **{name}**",
            color=0x27ae60
        )
        embed.add_field(name="💰 Số dư mới", value=format_money(new_amount), inline=True)
        embed.add_field(name="🎯 Tiến độ", value=f"{progress:.1f}%", inline=True)
        embed.add_field(name="📈 Còn thiếu", value=format_money(target_amt - new_amount), inline=True)
        
        if new_amount >= target_amt:
            embed.add_field(
                name="🎉 Chúc Mừng!",
                value=f"Bạn đã hoàn thành mục tiêu **{name}**!",
                inline=False
            )
    
    conn.close()
    await ctx.send(embed=embed)

# ==== LỆNH HISTORY NÂNG CÂP ====
@bot.command(name='history', aliases=['hist', 'h'])
async def history(ctx, days: int = 7, category: str = None):
    user_id = ctx.author.id
    get_or_create_user(user_id, ctx.author.display_name)
    
    conn = sqlite3.connect('finance_bot.db')
    cursor = conn.cursor()
    
    limit_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    
    if category:
        cursor.execute('''
            SELECT amount, type, category, description, date 
            FROM transactions 
            WHERE user_id = ? AND date >= ? AND category = ?
            ORDER BY date DESC 
            LIMIT ?
        ''', (user_id, limit_date, category, CONFIG['MAX_TRANSACTIONS_DISPLAY']))
        title = f"📋 Lịch sử {category} ({days} ngày)"
    else:
        cursor.execute('''
            SELECT amount, type, category, description, date 
            FROM transactions 
            WHERE user_id = ? AND date >= ? 
            ORDER BY date DESC 
            LIMIT ?
        ''', (user_id, limit_date, CONFIG['MAX_TRANSACTIONS_DISPLAY']))
        title = f"📋 Lịch sử giao dịch ({days} ngày)"
    
    records = cursor.fetchall()
    conn.close()
    
    if not records:
        await ctx.send(f"📭 Không có giao dịch nào trong {days} ngày qua.")
        return
    
    # Tạo embed với pagination
    embeds = []
    items_per_page = 8
    
    for i in range(0, len(records), items_per_page):
        embed = discord.Embed(title=title, color=0x3498db)
        page_records = records[i:i+items_per_page]
        
        for amt, ttype, cat, desc, date in page_records:
            # Icon theo type
            icon = "💵" if ttype == "income" else "💸"
            symbol = "+" if ttype == "income" else "-"
            
            # Format date
            try:
                date_obj = datetime.strptime(date, '%Y-%m-%d %H:%M:%S')
                date_str = date_obj.strftime('%d/%m %H:%M')
            except:
                date_str = date
            
            # Truncate description
            if len(desc) > 30:
                desc = desc[:27] + "..."
            
            value = f"{symbol}{format_money(amt)}\n📂 {cat}\n📝 {desc}\n🕐 {date_str}"
            embed.add_field(name=f"{icon} Giao dịch", value=value, inline=True)
        
        # Footer
        page_num = (i // items_per_page) + 1
        total_pages = (len(records) - 1) // items_per_page + 1
        embed.set_footer(text=f"Trang {page_num}/{total_pages} • Tổng {len(records)} giao dịch")
        
        embeds.append(embed)
    
    # Gửi embed đầu tiên
    await ctx.send(embed=embeds[0])
    
    # Nếu có nhiều trang, thêm reactions để navigate
    if len(embeds) > 1:
        # Implement pagination logic here if needed
        pass

# ==== LỆNH TRANSFER ====
@bot.command(name='transfer', aliases=['send', 'tf'])
async def transfer(ctx, amount: int, recipient: discord.Member, *, description: str = "Chuyển tiền"):
    if amount <= 0:
        await ctx.send("❌ Số tiền phải lớn hơn 0!")
        return
    
    if recipient.id == ctx.author.id:
        await ctx.send("❌ Không thể chuyển tiền cho chính mình!")
        return
    
    user_id = ctx.author.id
    recipient_id = recipient.id
    
    get_or_create_user(user_id, ctx.author.display_name)
    get_or_create_user(recipient_id, recipient.display_name)
    
    conn = sqlite3.connect('finance_bot.db')
    cursor = conn.cursor()
    
    # Kiểm tra số dư
    cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
    sender_balance = cursor.fetchone()[0]
    
    if sender_balance < amount:
        embed = discord.Embed(
            title="❌ Không Đủ Số Dư",
            description=f"Bạn cần thêm {format_money(amount - sender_balance)}",
            color=0xff4757
        )
        embed.add_field(name="Số dư hiện tại", value=format_money(sender_balance))
        await ctx.send(embed=embed)
        return
    
    # Thực hiện chuyển tiền
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    cursor.execute('UPDATE users SET balance = balance - ? WHERE user_id = ?', (amount, user_id))
    cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, recipient_id))
    
    # Ghi lại transactions
    cursor.execute('''
        INSERT INTO transactions (user_id, amount, type, category, description, date) 
        VALUES (?, ?, "expense", "Chuyển tiền", ?, ?)
    ''', (user_id, amount, f"Chuyển cho {recipient.display_name}: {description}", now))
    
    cursor.execute('''
        INSERT INTO transactions (user_id, amount, type, category, description, date) 
        VALUES (?, ?, "income", "Chuyển tiền", ?, ?)
    ''', (recipient_id, amount, f"Nhận từ {ctx.author.display_name}: {description}", now))
    
    conn.commit()
    conn.close()
    
    # Tạo embed thông báo
    embed = discord.Embed(
        title="💸 Chuyển Tiền Thành Công",
        description=f"Đã chuyển {format_money(amount)} cho {recipient.mention}",
        color=0x00ff41
    )
    embed.add_field(name="📝 Mô tả", value=description, inline=True)
    embed.add_field(name="⏰ Thời gian", value=now, inline=True)
    
    await ctx.send(embed=embed)
    
    # Gửi thông báo cho người nhận
    try:
        recipient_embed = discord.Embed(
            title="💰 Nhận Tiền",
            description=f"Bạn nhận được {format_money(amount)} từ {ctx.author.display_name}",
            color=0x00ff41
        )
        recipient_embed.add_field(name="📝 Mô tả", value=description)
        await recipient.send(embed=recipient_embed)
    except:
        pass  # Không thể gửi DM

# ==== LỆNH CATEGORY ====
@bot.command(name='category', aliases=['cat'])
async def category(ctx, action: str = "list", *, name: str = None):
    user_id = ctx.author.id
    get_or_create_user(user_id, ctx.author.display_name)
    
    if action == "list":
        categories = get_categories(user_id)
        
        income_cats = [cat for cat in categories if cat[3] == 'income']
        expense_cats = [cat for cat in categories if cat[3] == 'expense']
        
        embed = discord.Embed(title="📂 Danh Mục", color=0x3498db)
        
        if income_cats:
            income_text = ""
            for cat in income_cats[:10]:  # Limit display
                icon = cat[5] if cat[5] else "💰"
                income_text += f"{icon} {cat[2]}\n"
            embed.add_field(name="💵 Thu Nhập", value=income_text, inline=True)
        
        if expense_cats:
            expense_text = ""
            for cat in expense_cats[:10]:
                icon = cat[5] if cat[5] else "💸"
                expense_text += f"{icon} {cat[2]}\n"
            embed.add_field(name="💸 Chi Tiêu", value=expense_text, inline=True)
        
        await ctx.send(embed=embed)
    
    # Implement add/remove category logic here if needed

# ==== LỆNH EXPORT/IMPORT ====
@bot.command(name='export')
async def export_data(ctx, format_type: str = "json"):
    user_id = ctx.author.id
    get_or_create_user(user_id, ctx.author.display_name)
    
    conn = sqlite3.connect('finance_bot.db')
    cursor = conn.cursor()
    
    # Lấy tất cả dữ liệu
    cursor.execute('SELECT * FROM transactions WHERE user_id = ? ORDER BY date DESC', (user_id,))
    transactions = cursor.fetchall()
    
    cursor.execute('SELECT * FROM savings_goals WHERE user_id = ?', (user_id,))
    goals = cursor.fetchall()
    
    conn.close()
    
    if format_type.lower() == "csv":
        # CSV export
        csv_content = "Date,Amount,Type,Category,Description\n"
        for trans in transactions:
            csv_content += f"{trans[6]},{trans[2]},{trans[3]},{trans[4]},{trans[5]}\n"
        
        with io.StringIO(csv_content) as buffer:
            file = discord.File(buffer, filename=f"finance_data_{user_id}.csv")
    else:
        # JSON export
        data = {
            "user_id": user_id,
            "export_date": datetime.now().isoformat(),
            "transactions": [
                {
                    "date": trans[6],
                    "amount": trans[2],
                    "type": trans[3],
                    "category": trans[4],
                    "description": trans[5]
                } for trans in transactions
            ],
            "savings_goals": [
                {
                    "name": goal[2],
                    "target": goal[3],
                    "current": goal[4],
                    "deadline": goal[5]
                } for goal in goals
            ]
        }
        
        json_content = json.dumps(data, ensure_ascii=False, indent=2)
        buffer = io.StringIO(json_content)
        file = discord.File(buffer, filename=f"finance_data_{user_id}.json")
    
    embed = discord.Embed(
        title="📤 Xuất Dữ Liệu",
        description=f"Dữ liệu tài chính của bạn ({len(transactions)} giao dịch)",
        color=0x27ae60
    )
    
    await ctx.send(embed=embed, file=file)

# ==== LỆNH SETTINGS ====
@bot.command(name='settings', aliases=['config'])
async def settings(ctx, setting: str = None, *, value: str = None):
    user_id = ctx.author.id
    get_or_create_user(user_id, ctx.author.display_name)
    
    conn = sqlite3.connect('finance_bot.db')
    cursor = conn.cursor()
    
    if setting is None:
        # Hiển thị tất cả settings
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user_data = cursor.fetchone()
        
        embed = discord.Embed(title="⚙️ Cài Đặt Cá Nhân", color=0x9b59b6)
        embed.add_field(name="💰 Tiền tệ", value=user_data[5] or "VND", inline=True)
        embed.add_field(name="🌍 Múi giờ", value=user_data[6] or "Asia/Ho_Chi_Minh", inline=True)
        embed.add_field(name="🔔 Thông báo", value="Bật" if user_data[7] else "Tắt", inline=True)
        embed.add_field(name="💳 Ngân sách tháng", value=format_money(user_data[4]) if user_data[4] else "Chưa đặt", inline=True)
        
        embed.add_field(
            name="📝 Cách sử dụng",
            value="`/settings currency VND` - Đổi tiền tệ\n"
                  "`/settings notifications on/off` - Bật/tắt thông báo\n"
                  "`/settings budget [số tiền]` - Đặt ngân sách tháng",
            inline=False
        )
        
    elif setting == "currency":
        if value and value.upper() in ['VND', 'USD', 'EUR']:
            cursor.execute('UPDATE users SET currency = ? WHERE user_id = ?', (value.upper(), user_id))
            conn.commit()
            embed = discord.Embed(title="✅ Đã cập nhật tiền tệ", color=0x00ff41)
            embed.add_field(name="Tiền tệ mới", value=value.upper())
        else:
            embed = discord.Embed(title="❌ Tiền tệ không hợp lệ", color=0xff4757)
            embed.add_field(name="Hỗ trợ", value="VND, USD, EUR")
    
    elif setting == "notifications":
        if value and value.lower() in ['on', 'off', 'bật', 'tắt']:
            notify_on = value.lower() in ['on', 'bật']
            cursor.execute('UPDATE users SET notifications = ? WHERE user_id = ?', (notify_on, user_id))
            conn.commit()
            status = "bật" if notify_on else "tắt"
            embed = discord.Embed(title=f"✅ Đã {status} thông báo", color=0x00ff41)
        else:
            embed = discord.Embed(title="❌ Giá trị không hợp lệ", color=0xff4757)
            embed.add_field(name="Sử dụng", value="on/off hoặc bật/tắt")
    
    elif setting == "budget":
        try:
            budget_amount = int(value) if value else 0
            if budget_amount < 0:
                raise ValueError
            cursor.execute('UPDATE users SET monthly_budget = ? WHERE user_id = ?', (budget_amount, user_id))
            conn.commit()
            embed = discord.Embed(title="✅ Đã cập nhật ngân sách tháng", color=0x00ff41)
            embed.add_field(name="Ngân sách mới", value=format_money(budget_amount) if budget_amount else "Không giới hạn")
        except ValueError:
            embed = discord.Embed(title="❌ Số tiền không hợp lệ", color=0xff4757)
    
    else:
        embed = discord.Embed(title="❌ Cài đặt không tồn tại", color=0xff4757)
        embed.add_field(name="Có sẵn", value="currency, notifications, budget")
    
    conn.close()
    await ctx.send(embed=embed)

# ==== LỆNH SEARCH ====
@bot.command(name='search', aliases=['find'])
async def search(ctx, *, keyword: str):
    user_id = ctx.author.id
    get_or_create_user(user_id, ctx.author.display_name)
    
    conn = sqlite3.connect('finance_bot.db')
    cursor = conn.cursor()
    
    # Tìm kiếm trong description và category
    cursor.execute('''
        SELECT amount, type, category, description, date 
        FROM transactions 
        WHERE user_id = ? AND (
            LOWER(description) LIKE LOWER(?) OR 
            LOWER(category) LIKE LOWER(?)
        )
        ORDER BY date DESC 
        LIMIT 20
    ''', (user_id, f'%{keyword}%', f'%{keyword}%'))
    
    results = cursor.fetchall()
    conn.close()
    
    if not results:
        await ctx.send(f"🔍 Không tìm thấy giao dịch nào với từ khóa '{keyword}'")
        return
    
    embed = discord.Embed(
        title=f"🔍 Kết Quả Tìm Kiếm: '{keyword}'",
        description=f"Tìm thấy {len(results)} giao dịch",
        color=0x3498db
    )
    
    for amt, ttype, cat, desc, date in results[:10]:  # Hiển thị tối đa 10
        icon = "💵" if ttype == "income" else "💸"
        symbol = "+" if ttype == "income" else "-"
        
        try:
            date_obj = datetime.strptime(date, '%Y-%m-%d %H:%M:%S')
            date_str = date_obj.strftime('%d/%m/%Y')
        except:
            date_str = date
        
        embed.add_field(
            name=f"{icon} {symbol}{format_money(amt)}",
            value=f"📂 {cat}\n📝 {desc}\n📅 {date_str}",
            inline=True
        )
    
    if len(results) > 10:
        embed.set_footer(text=f"... và {len(results) - 10} kết quả khác")
    
    await ctx.send(embed=embed)

# ==== LỆNH ACHIEVEMENTS ====
@bot.command(name='achievements', aliases=['achieve'])
async def achievements(ctx):
    user_id = ctx.author.id
    get_or_create_user(user_id, ctx.author.display_name)
    
    conn = sqlite3.connect('finance_bot.db')
    cursor = conn.cursor()
    
    # Lấy thống kê để tính achievements
    cursor.execute('SELECT COUNT(*) FROM transactions WHERE user_id = ?', (user_id,))
    total_transactions = cursor.fetchone()[0]
    
    cursor.execute('SELECT SUM(amount) FROM transactions WHERE user_id = ? AND type = "income"', (user_id,))
    total_income = cursor.fetchone()[0] or 0
    
    cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
    current_balance = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(DISTINCT DATE(date)) FROM transactions WHERE user_id = ?', (user_id,))
    active_days = cursor.fetchone()[0]
    
    conn.close()
    
    # Tính achievements
    achievements = []
    
    if total_transactions >= 1:
        achievements.append(("🌱", "Bước đầu tiên", "Thực hiện giao dịch đầu tiên"))
    if total_transactions >= 50:
        achievements.append(("📊", "Chuyên gia ghi chép", "50 giao dịch đã ghi"))
    if total_transactions >= 100:
        achievements.append(("🏆", "Siêu sao tài chính", "100 giao dịch đã ghi"))
    
    if total_income >= 10000000:  # 10M
        achievements.append(("💰", "Triệu phú nhỏ", "Tổng thu nhập 10M+"))
    if total_income >= 100000000:  # 100M
        achievements.append(("💎", "Đại gia", "Tổng thu nhập 100M+"))
    
    if current_balance >= 5000000:  # 5M
        achievements.append(("🏦", "Tiết kiệm giỏi", "Số dư 5M+"))
    if current_balance >= 50000000:  # 50M
        achievements.append(("👑", "Vua tiết kiệm", "Số dư 50M+"))
    
    if active_days >= 7:
        achievements.append(("🔥", "Streak 7 ngày", "Hoạt động 7 ngày"))
    if active_days >= 30:
        achievements.append(("⭐", "Người bền bỉ", "Hoạt động 30 ngày"))
    
    embed = discord.Embed(title="🏆 Thành Tích", color=0xf39c12)
    
    if achievements:
        for icon, name, desc in achievements:
            embed.add_field(name=f"{icon} **{name}**", value=desc, inline=True)
    else:
        embed.add_field(name="🌱 Chưa có thành tích", value="Hãy bắt đầu sử dụng bot để mở khóa!", inline=False)
    
    # Progress đến achievement tiếp theo
    next_achievements = []
    if total_transactions < 50:
        next_achievements.append(f"📊 {50 - total_transactions} giao dịch nữa → Chuyên gia ghi chép")
    if current_balance < 5000000:
        need = 5000000 - current_balance
        next_achievements.append(f"🏦 {format_money(need)} nữa → Tiết kiệm giỏi")
    
    if next_achievements:
        embed.add_field(
            name="🎯 Mục tiêu tiếp theo",
            value="\n".join(next_achievements[:3]),
            inline=False
        )
    
    await ctx.send(embed=embed)

# ==== LỆNH REPORT ====
@bot.command(name='report')
async def report(ctx, period: str = "month"):
    user_id = ctx.author.id
    get_or_create_user(user_id, ctx.author.display_name)
    
    conn = sqlite3.connect('finance_bot.db')
    cursor = conn.cursor()
    
    # Xác định period
    if period == "week":
        start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        title = "📋 Báo Cáo Tuần"
        date_filter = "date >= ?"
        params = (user_id, start_date)
    elif period == "year":
        current_year = datetime.now().year
        title = f"📋 Báo Cáo Năm {current_year}"
        date_filter = "date LIKE ?"
        params = (user_id, f'{current_year}%')
    else:  # month
        current_month = datetime.now().strftime('%Y-%m')
        title = f"📋 Báo Cáo Tháng {current_month}"
        date_filter = "date LIKE ?"
        params = (user_id, f'{current_month}%')
    
    # Lấy dữ liệu tổng hợp
    cursor.execute(f'''
        SELECT 
            SUM(CASE WHEN type = "income" THEN amount ELSE 0 END) as total_income,
            SUM(CASE WHEN type = "expense" THEN amount ELSE 0 END) as total_expense,
            COUNT(*) as total_transactions,
            AVG(CASE WHEN type = "expense" THEN amount ELSE NULL END) as avg_expense
        FROM transactions 
        WHERE user_id = ? AND {date_filter}
    ''', params)
    
    summary = cursor.fetchone()
    total_income, total_expense, total_trans, avg_expense = summary
    total_income = total_income or 0
    total_expense = total_expense or 0
    avg_expense = avg_expense or 0
    
    # Top categories
    cursor.execute(f'''
        SELECT category, SUM(amount), COUNT(*) 
        FROM transactions 
        WHERE user_id = ? AND type = "expense" AND {date_filter}
        GROUP BY category 
        ORDER BY SUM(amount) DESC 
        LIMIT 5
    ''', params)
    top_expenses = cursor.fetchall()
    
    # Lấy trends (so sánh với period trước)
    if period == "month":
        prev_month = (datetime.now().replace(day=1) - timedelta(days=1)).strftime('%Y-%m')
        cursor.execute('''
            SELECT 
                SUM(CASE WHEN type = "income" THEN amount ELSE 0 END),
                SUM(CASE WHEN type = "expense" THEN amount ELSE 0 END)
            FROM transactions 
            WHERE user_id = ? AND date LIKE ?
        ''', (user_id, f'{prev_month}%'))
        prev_data = cursor.fetchone()
        prev_income, prev_expense = prev_data[0] or 0, prev_data[1] or 0
    
    conn.close()
    
    # Tạo embed báo cáo
    embed = discord.Embed(title=title, color=0x2ecc71)
    
    # Tóm tắt tài chính
    net_amount = total_income - total_expense
    embed.add_field(
        name="💰 Tổng Quan",
        value=f"Thu nhập: {format_money(total_income)}\n"
              f"Chi tiêu: {format_money(total_expense)}\n"
              f"**Ròng: {format_money(net_amount)}**\n"
              f"Giao dịch: {total_trans} lần",
        inline=True
    )
    
    # Phân tích
    if total_income > 0:
        savings_rate = (net_amount / total_income) * 100
        expense_rate = (total_expense / total_income) * 100
        
        embed.add_field(
            name="📊 Phân Tích",
            value=f"Tỷ lệ tiết kiệm: {savings_rate:.1f}%\n"
                  f"Tỷ lệ chi tiêu: {expense_rate:.1f}%\n"
                  f"Chi tiêu TB: {format_money(avg_expense)}",
            inline=True
        )
    
    # Trends (chỉ cho month)
    if period == "month" and prev_income > 0:
        income_change = ((total_income - prev_income) / prev_income) * 100
        expense_change = ((total_expense - prev_expense) / prev_expense) * 100 if prev_expense > 0 else 0
        
        income_trend = "📈" if income_change > 0 else "📉" if income_change < 0 else "➡️"
        expense_trend = "📈" if expense_change > 0 else "📉" if expense_change < 0 else "➡️"
        
        embed.add_field(
            name="📈 Xu Hướng",
            value=f"{income_trend} Thu nhập: {income_change:+.1f}%\n"
                  f"{expense_trend} Chi tiêu: {expense_change:+.1f}%",
            inline=True
        )
    
    # Top chi tiêu
    if top_expenses:
        expense_text = ""
        for cat, amount, count in top_expenses[:5]:
            percentage = (amount / total_expense) * 100 if total_expense > 0 else 0
            expense_text += f"**{cat}**: {format_money(amount)} ({percentage:.1f}%)\n"
        embed.add_field(name="🔥 Top Chi Tiêu", value=expense_text, inline=False)
    
    # Lời khuyên
    advice = []
    if total_expense > total_income:
        advice.append("⚠️ Chi tiêu vượt thu nhập!")
    elif net_amount > 0:
        advice.append("🎉 Bạn đã tiết kiệm được tiền!")
    
    if avg_expense > 500000:  # 500k
        advice.append("💡 Hãy theo dõi chi tiêu hàng ngày")
    
    if advice:
        embed.add_field(name="💭 Lời Khuyên", value="\n".join(advice), inline=False)
    
    embed.set_footer(text=f"Báo cáo tạo lúc {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    
    await ctx.send(embed=embed)

# ==== LỆNH GOAL NÂNG CẤP ====
@bot.command(name='goal', aliases=['target'])
async def goal(ctx, amount: int = None):
    user_id = ctx.author.id
    get_or_create_user(user_id, ctx.author.display_name)

    conn = sqlite3.connect('finance_bot.db')
    cursor = conn.cursor()

    if amount is None:
        # Hiển thị mục tiêu hiện tại
        cursor.execute('SELECT balance, goal FROM users WHERE user_id = ?', (user_id,))
        balance, goal_amt = cursor.fetchone()
        
        if goal_amt == 0:
            embed = discord.Embed(
                title="🎯 Mục Tiêu Của Bạn",
                description="Bạn chưa đặt mục tiêu tiết kiệm nào",
                color=0x95a5a6
            )
            embed.add_field(
                name="💡 Hướng dẫn",
                value="Dùng `/goal [số tiền]` để đặt mục tiêu\nVí dụ: `/goal 50000000`",
                inline=False
            )
        else:
            progress = min((balance / goal_amt) * 100, 100)
            remain = max(goal_amt - balance, 0)
            
            # Tính thời gian dự kiến
            current_month = datetime.now().strftime('%Y-%m')
            cursor.execute('''
                SELECT AVG(monthly_saving) FROM (
                    SELECT SUM(CASE WHEN type="income" THEN amount ELSE -amount END) as monthly_saving
                    FROM transactions 
                    WHERE user_id = ? AND date LIKE ?
                    GROUP BY substr(date, 1, 7)
                ) WHERE monthly_saving > 0
            ''', (user_id, f'{current_month[:4]}%'))
            avg_monthly_saving = cursor.fetchone()[0] or 0
            
            embed = discord.Embed(title="🎯 Mục Tiêu Tiết Kiệm", color=0x4ecdc4)
            embed.add_field(name="🎯 Mục tiêu", value=format_money(goal_amt), inline=True)
            embed.add_field(name="💰 Hiện tại", value=format_money(balance), inline=True)
            embed.add_field(name="📊 Tiến độ", value=f"{progress:.1f}%", inline=True)
            
            progress_bar = create_progress_bar(balance, goal_amt, 25)
            embed.add_field(name="📈 Thanh tiến độ", value=f"`{progress_bar}`", inline=False)
            
            if remain > 0:
                embed.add_field(name="💸 Còn thiếu", value=format_money(remain), inline=True)
                
                if avg_monthly_saving > 0:
                    months_needed = remain / avg_monthly_saving
                    embed.add_field(
                        name="⏰ Dự kiến",
                        value=f"{months_needed:.1f} tháng nữa",
                        inline=True
                    )
            else:
                embed.add_field(
                    name="🎉 Chúc mừng!",
                    value="Bạn đã đạt được mục tiêu!",
                    inline=False
                )
    else:
        # Đặt mục tiêu mới
        if amount <= 0:
            await ctx.send("❌ Mục tiêu phải lớn hơn 0!")
            return
        
        cursor.execute('UPDATE users SET goal = ? WHERE user_id = ?', (amount, user_id))
        conn.commit()
        
        cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
        current_balance = cursor.fetchone()[0]
        
        embed = discord.Embed(
            title="🎯 Đã Đặt Mục Tiêu Mới",
            description=f"Mục tiêu: **{format_money(amount)}**",
            color=0x4ecdc4
        )
        
        if current_balance > 0:
            progress = min((current_balance / amount) * 100, 100)
            embed.add_field(name="📊 Tiến độ hiện tại", value=f"{progress:.1f}%", inline=True)
            embed.add_field(name="💰 Số dư hiện tại", value=format_money(current_balance), inline=True)
        
        remaining = max(amount - current_balance, 0)
        if remaining > 0:
            embed.add_field(name="🎯 Còn cần", value=format_money(remaining), inline=True)

    conn.close()
    await ctx.send(embed=embed)

# ==== XỬ LÝ LỖI NÂNG CẤP ====
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        embed = discord.Embed(
            title="❌ Thiếu Tham Số",
            description="Vui lòng kiểm tra lại cú pháp lệnh",
            color=0xff4757
        )
        embed.add_field(name="💡 Gợi ý", value="Dùng `/help` để xem hướng dẫn chi tiết")
        await ctx.send(embed=embed)
        
    elif isinstance(error, commands.BadArgument):
        embed = discord.Embed(
            title="❌ Lỗi Định Dạng",
            description="Kiểm tra lại định dạng số tiền hoặc tham số",
            color=0xff4757
        )
        embed.add_field(name="💡 Lưu ý", value="Số tiền phải là số nguyên (ví dụ: 50000)")
        await ctx.send(embed=embed)
        
    elif isinstance(error, commands.CommandNotFound):
        # Không làm gì cho command không tồn tại
        pass
        
    elif isinstance(error, commands.CommandOnCooldown):
        embed = discord.Embed(
            title="⏰ Vui Lòng Chờ",
            description=f"Thử lại sau {error.retry_after:.1f} giây",
            color=0xffa502
        )
        await ctx.send(embed=embed)
        
    else:
        # Log lỗi chi tiết
        logger.error(f"Command error in {ctx.command}: {error}", exc_info=error)
        
        embed = discord.Embed(
            title="❌ Có Lỗi Xảy Ra",
            description="Đã xảy ra lỗi không mong muốn",
            color=0xff4757
        )
        embed.add_field(name="🔧 Giải pháp", value="Vui lòng thử lại hoặc liên hệ admin")
        await ctx.send(embed=embed)

# ==== LỆNH ADMIN (Nếu cần) ====
@bot.command(name='admin_stats')
@commands.has_permissions(administrator=True)
async def admin_stats(ctx):
    conn = sqlite3.connect('finance_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM transactions')
    total_transactions = cursor.fetchone()[0]
    
    cursor.execute('SELECT SUM(balance) FROM users')
    total_balance = cursor.fetchone()[0] or 0
    
    cursor.execute('SELECT COUNT(*) FROM users WHERE last_active >= ?', 
                   ((datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'),))
    active_users = cursor.fetchone()[0]
    
    conn.close()
    
    embed = discord.Embed(title="📊 Thống Kê Bot", color=0xe74c3c)
    embed.add_field(name="👥 Tổng users", value=total_users, inline=True)
    embed.add_field(name="💳 Tổng giao dịch", value=total_transactions, inline=True)
    embed.add_field(name="💰 Tổng số dư", value=format_money(total_balance), inline=True)
    embed.add_field(name="🔥 Users hoạt động (7d)", value=active_users, inline=True)
    
    await ctx.send(embed=embed)

# ==== SLASH COMMANDS (Nếu muốn) ====
from discord import app_commands

@bot.tree.command(name="balance", description="Xem số dư và tổng quan tài chính")
async def slash_balance(interaction: discord.Interaction):
    # Chuyển đổi interaction thành context-like object
    ctx = await bot.get_context(interaction)
    await balance(ctx)

@bot.tree.command(name="quick_add", description="Thêm thu nhập nhanh")
async def slash_quick_add(interaction: discord.Interaction, amount: int, description: str = "Thu nhập"):
    ctx = await bot.get_context(interaction)
    await add(ctx, amount, "Khác", description=description)

# ==== CHẠY BOT ====
if __name__ == "__main__":
    # Khởi tạo database khi start
    init_database()
    
    # Sync slash commands
    @bot.event
    async def setup_hook():
        try:
            synced = await bot.tree.sync()
            print(f"✅ Đồng bộ {len(synced)} slash commands")
        except Exception as e:
            print(f"❌ Lỗi đồng bộ slash commands: {e}")
    
    # Chạy bot
    try:
        bot.run('YOUR_BOT_TOKEN')  # 🔑 Thay YOUR_BOT_TOKEN bằng token thực của bạn
    except Exception as e:
        print(f"❌ Lỗi khởi động bot: {e}")
        print("💡 Kiểm tra lại BOT_TOKEN và kết nối internet")
