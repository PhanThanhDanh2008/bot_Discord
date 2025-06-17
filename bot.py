import discord
from discord.ext import commands
import sqlite3
from datetime import datetime, timedelta

# ==== CẤU HÌNH BOT ====
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents, help_command=None)

# ==== TẠO DATABASE ====
def init_database():
    conn = sqlite3.connect('finance_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance INTEGER DEFAULT 0,
            goal INTEGER DEFAULT 0,
            created_date TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount INTEGER,
            type TEXT,
            description TEXT,
            date TEXT,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    conn.commit()
    conn.close()

# ==== HÀM PHỤ ====
def format_money(amount):
    return f"{amount:,} VND".replace(",", ".")

def get_or_create_user(user_id):
    conn = sqlite3.connect('finance_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    if not user:
        cursor.execute('INSERT INTO users (user_id, balance, goal, created_date) VALUES (?, 0, 0, ?)',
                       (user_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
    conn.close()

# ==== SỰ KIỆN BOT ====
@bot.event
async def on_ready():
    print(f'{bot.user} đã online!')
    init_database()

# ==== LỆNH HELP ====
@bot.command(name='help')
async def help_command(ctx):
    embed = discord.Embed(title="🤖 Hướng dẫn sử dụng Finance Bot", color=0x00ff00)
    embed.add_field(
        name="💰 Lệnh cơ bản",
        value="`/balance` - Xem số dư\n"
              "`/add [số tiền] [mô tả]` - Thêm thu nhập\n"
              "`/spend [số tiền] [mô tả]` - Chi tiêu\n"
              "`/goal [số tiền]` - Đặt mục tiêu",
        inline=False
    )
    embed.add_field(
        name="📊 Thống kê & Lịch sử",
        value="`/history` - Lịch sử giao dịch\n"
              "`/stats` - Thống kê tuần/tháng",
        inline=False
    )
    embed.add_field(
        name="📝 Ví dụ",
        value="`/add 3000000 lương tháng 6`\n"
              "`/spend 50000 ăn sáng`\n"
              "`/goal 10000000`",
        inline=False
    )
    await ctx.send(embed=embed)

# ==== /BALANCE ====
@bot.command(name='balance')
async def balance(ctx):
    user_id = ctx.author.id
    get_or_create_user(user_id)
    conn = sqlite3.connect('finance_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT balance, goal FROM users WHERE user_id = ?', (user_id,))
    user_data = cursor.fetchone()
    conn.close()

    if not user_data:
        await ctx.send("⚠️ Không tìm thấy tài khoản. Dùng `/add` để bắt đầu.")
        return

    balance_amount, goal_amount = user_data
    progress = (balance_amount / goal_amount) * 100 if goal_amount else 0
    goal_text = f"{format_money(goal_amount)} ({progress:.1f}%)" if goal_amount else "Chưa đặt mục tiêu"

    embed = discord.Embed(
        title=f"💰 Tài chính của {ctx.author.display_name}",
        color=0x00ff00
    )
    embed.add_field(name="Số dư", value=format_money(balance_amount), inline=False)
    embed.add_field(name="Mục tiêu", value=goal_text, inline=False)
    await ctx.send(embed=embed)

# ==== /ADD ====
@bot.command(name='add')
async def add(ctx, amount: int, *, description="Không có mô tả"):
    if amount <= 0:
        await ctx.send("❌ Số tiền phải lớn hơn 0!")
        return

    user_id = ctx.author.id
    get_or_create_user(user_id)
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    conn = sqlite3.connect('finance_bot.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
    cursor.execute('INSERT INTO transactions (user_id, amount, type, description, date) VALUES (?, ?, "income", ?, ?)',
                   (user_id, amount, description, now))
    cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
    new_balance = cursor.fetchone()[0]
    conn.commit()
    conn.close()

    embed = discord.Embed(title="✅ Đã thêm thu nhập", color=0x00ff00)
    embed.add_field(name="Số tiền", value=f"+{format_money(amount)}", inline=True)
    embed.add_field(name="Mô tả", value=description, inline=True)
    embed.add_field(name="Số dư mới", value=format_money(new_balance), inline=False)
    await ctx.send(embed=embed)

# ==== /SPEND ====
@bot.command(name='spend')
async def spend(ctx, amount: int, *, description="Không có mô tả"):
    if amount <= 0:
        await ctx.send("❌ Số tiền phải lớn hơn 0!")
        return

    user_id = ctx.author.id
    get_or_create_user(user_id)

    conn = sqlite3.connect('finance_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
    current_balance = cursor.fetchone()[0]

    if current_balance < amount:
        await ctx.send(f"❌ Không đủ tiền! Số dư: {format_money(current_balance)}")
        conn.close()
        return

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('UPDATE users SET balance = balance - ? WHERE user_id = ?', (amount, user_id))
    cursor.execute('INSERT INTO transactions (user_id, amount, type, description, date) VALUES (?, ?, "expense", ?, ?)',
                   (user_id, amount, description, now))
    cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
    new_balance = cursor.fetchone()[0]
    conn.commit()
    conn.close()

    embed = discord.Embed(title="💸 Chi tiêu ghi nhận", color=0xff6b6b)
    embed.add_field(name="Số tiền", value=f"-{format_money(amount)}", inline=True)
    embed.add_field(name="Mô tả", value=description, inline=True)
    embed.add_field(name="Số dư còn lại", value=format_money(new_balance), inline=False)
    await ctx.send(embed=embed)

# ==== /GOAL ====
@bot.command(name='goal')
async def goal(ctx, amount: int = None):
    user_id = ctx.author.id
    get_or_create_user(user_id)

    conn = sqlite3.connect('finance_bot.db')
    cursor = conn.cursor()

    if amount is None:
        cursor.execute('SELECT balance, goal FROM users WHERE user_id = ?', (user_id,))
        balance, goal_amt = cursor.fetchone()
        if goal_amt == 0:
            await ctx.send("❌ Bạn chưa đặt mục tiêu.")
        else:
            progress = min((balance / goal_amt) * 100, 100)
            remain = max(goal_amt - balance, 0)
            embed = discord.Embed(title="🎯 Mục tiêu của bạn", color=0x4ecdc4)
            embed.add_field(name="Mục tiêu", value=format_money(goal_amt), inline=True)
            embed.add_field(name="Đã có", value=format_money(balance), inline=True)
            embed.add_field(name="Tiến độ", value=f"{progress:.1f}%", inline=True)
            embed.add_field(name="Còn thiếu", value=format_money(remain), inline=False)
            await ctx.send(embed=embed)
    else:
        if amount <= 0:
            await ctx.send("❌ Mục tiêu phải lớn hơn 0!")
            return
        cursor.execute('UPDATE users SET goal = ? WHERE user_id = ?', (amount, user_id))
        conn.commit()
        embed = discord.Embed(title="🎯 Đã đặt mục tiêu mới", description=f"{format_money(amount)}", color=0x4ecdc4)
        await ctx.send(embed=embed)

    conn.close()

# ==== /HISTORY ====
@bot.command(name='history')
async def history(ctx, days: int = 7):
    user_id = ctx.author.id
    get_or_create_user(user_id)

    conn = sqlite3.connect('finance_bot.db')
    cursor = conn.cursor()
    limit_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    cursor.execute('''
        SELECT amount, type, description, date 
        FROM transactions 
        WHERE user_id = ? AND date >= ? 
        ORDER BY date DESC LIMIT 10
    ''', (user_id, limit_date))
    records = cursor.fetchall()
    conn.close()

    if not records:
        await ctx.send(f"📭 Không có giao dịch nào trong {days} ngày qua.")
        return

    embed = discord.Embed(title=f"📋 Giao dịch {days} ngày", color=0x3498db)
    for amt, ttype, desc, date in records:
        symbol = "+" if ttype == "income" else "-"
        line = f"{symbol}{format_money(amt)} | {desc} | {date}"
        embed.add_field(name="💵" if ttype == "income" else "💸", value=line, inline=False)
    await ctx.send(embed=embed)

# ==== /STATS ====
@bot.command(name='stats')
async def stats(ctx):
    user_id = ctx.author.id
    get_or_create_user(user_id)
    conn = sqlite3.connect('finance_bot.db')
    cursor = conn.cursor()

    current_month = datetime.now().strftime('%Y-%m')
    week_start = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

    cursor.execute('SELECT type, SUM(amount) FROM transactions WHERE user_id = ? AND date LIKE ? GROUP BY type',
                   (user_id, f'{current_month}%'))
    month_stats = dict(cursor.fetchall())

    cursor.execute('SELECT type, SUM(amount) FROM transactions WHERE user_id = ? AND date >= ? GROUP BY type',
                   (user_id, week_start))
    week_stats = dict(cursor.fetchall())

    embed = discord.Embed(title="📊 Thống kê", color=0x6c5ce7)
    embed.add_field(
        name="Tháng này",
        value=f"Thu: +{format_money(month_stats.get('income', 0))}\n"
              f"Chi: -{format_money(month_stats.get('expense', 0))}",
        inline=True
    )
    embed.add_field(
        name="Tuần này",
        value=f"Thu: +{format_money(week_stats.get('income', 0))}\n"
              f"Chi: -{format_money(week_stats.get('expense', 0))}",
        inline=True
    )
    await ctx.send(embed=embed)
    conn.close()

# ==== XỬ LÝ LỖI ====
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("❌ Thiếu tham số. Dùng `/help` để xem hướng dẫn.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❌ Lỗi định dạng! Số tiền phải là số.")
    else:
        await ctx.send("❌ Có lỗi xảy ra! Vui lòng thử lại.")

# ==== CHẠY BOT ====
if __name__ == "__main__":
    bot.run('')  # 🔁 Dán token bot của bạn vào đây!
