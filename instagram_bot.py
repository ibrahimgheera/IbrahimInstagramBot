import os
import threading
import schedule
import time
import requests
from datetime import datetime
from groq import Groq
import telebot

# ============ CONFIG ============
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
IBRAHIM_CHAT_ID = os.getenv("IBRAHIM_CHAT_ID")
INSTAGRAM_USERNAME = "calis_ibra"

bot = telebot.TeleBot(TELEGRAM_TOKEN)
groq_client = Groq(api_key=GROQ_API_KEY)
user_conversations = {}

# ============ BOT 1 — SMART ASSISTANT ============
SYSTEM_PROMPT = """You are Ibrahim's personal Instagram content strategist and AI assistant.

WHO IBRAHIM IS:
- Fitness coach at TK MMAfit Dubai Marina
- Building Gheera Bakery (healthy premium cookies)
- Posts on Instagram about fitness and bakery content
- Wants to grow his brand and save time

YOUR ROLE: Help Ibrahim with captions, content strategy, post ideas, hashtags, scheduling advice, and social media growth.

YOUR PERSONALITY:
- Smart and helpful
- Direct and actionable (Ibrahim is busy)
- Expert in fitness and food content
- Knows Dubai market

WHEN IBRAHIM ASKS FOR A CAPTION:
Generate engaging Instagram caption with:
- Strong hook
- 2-3 sentences of value  
- Clear call-to-action
- 8-10 relevant hashtags
- 150-200 words"""

def get_conversation(chat_id):
    if chat_id not in user_conversations:
        user_conversations[chat_id] = []
    return user_conversations[chat_id]

def add_to_conversation(chat_id, role, content):
    conversation = get_conversation(chat_id)
    conversation.append({"role": role, "content": content})
    if len(conversation) > 10:
        user_conversations[chat_id] = conversation[-10:]

def chat_with_ai(chat_id, user_message):
    add_to_conversation(chat_id, "user", user_message)
    conversation = get_conversation(chat_id)
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": SYSTEM_PROMPT}] + conversation,
            max_tokens=800,
            temperature=0.7
        )
        ai_response = response.choices[0].message.content
        add_to_conversation(chat_id, "assistant", ai_response)
        return ai_response
    except Exception as e:
        return f"Error: {str(e)}"

# ============ BOT 2 — DAILY ANALYTICS ============
def get_instagram_stats():
    try:
        url = f"https://www.instagram.com/{INSTAGRAM_USERNAME}/?__a=1&__d=dis"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        user = data["graphql"]["user"]
        followers = user["edge_followed_by"]["count"]
        following = user["edge_follow"]["count"]
        posts = user["edge_owner_to_timeline_media"]["count"]
        return followers, following, posts
    except:
        return None, None, None

def get_ai_daily_suggestion():
    try:
        now = datetime.now()
        day = now.strftime("%A")
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{
                "role": "user",
                "content": f"""Ibrahim is a fitness coach in Dubai Marina and runs Gheera Bakery (healthy cookies). 
                Today is {day}. Give him:
                1. One specific Instagram post idea for today
                2. Best time to post in Dubai (GST timezone)
                3. One quick growth tip
                Keep it short, direct, actionable. Max 100 words."""
            }],
            max_tokens=200,
            temperature=0.7
        )
        return response.choices[0].message.content
    except:
        return "💡 Post a behind-the-scenes story today — your audience loves authenticity!"

def send_daily_report():
    if not IBRAHIM_CHAT_ID:
        return
    
    followers, following, posts = get_instagram_stats()
    suggestion = get_ai_daily_suggestion()
    now = datetime.now()
    
    if followers:
        report = f"""🌅 Good morning Ibrahim! Daily Report — {now.strftime("%A, %d %b")}

📊 YOUR INSTAGRAM @calis_ibra
👥 Followers: {followers:,}
➡️ Following: {following:,}
📸 Total Posts: {posts:,}

💡 TODAY'S AI SUGGESTION:
{suggestion}

Let's have a great day! 💪🔥"""
    else:
        suggestion = get_ai_daily_suggestion()
        report = f"""🌅 Good morning Ibrahim! — {now.strftime("%A, %d %b")}

💡 TODAY'S CONTENT SUGGESTION:
{suggestion}

Let's crush it today! 💪🔥"""
    
    bot.send_message(IBRAHIM_CHAT_ID, report)

def run_scheduler():
    # Send report every day at 9am Dubai time (GST = UTC+4)
    schedule.every().day.at("05:00").do(send_daily_report)  # 5am UTC = 9am Dubai
    while True:
        schedule.run_pending()
        time.sleep(60)

# ============ TELEGRAM HANDLERS ============
@bot.message_handler(commands=['start'])
def start_command(message):
    bot.reply_to(message, """👋 Hey Ibrahim! Your bot team is live!

🤖 BOT 1 — Smart Assistant (always on)
Just talk to me naturally!
- "Give me a caption for my deadlift video"
- "What should I post this week?"
- "I need bakery content ideas"

📊 BOT 2 — Daily Analytics
Every morning at 9am Dubai time I send you your Instagram stats + content suggestion automatically!

Type /report to get today's report right now! 🚀""")

@bot.message_handler(commands=['report'])
def report_command(message):
    bot.send_chat_action(message.chat.id, 'typing')
    bot.reply_to(message, "📊 Fetching your stats...")
    
    followers, following, posts = get_instagram_stats()
    suggestion = get_ai_daily_suggestion()
    now = datetime.now()
    
    if followers:
        report = f"""📊 Instagram Report @calis_ibra — {now.strftime("%A, %d %b")}

👥 Followers: {followers:,}
➡️ Following: {following:,}
📸 Total Posts: {posts:,}

💡 TODAY'S AI SUGGESTION:
{suggestion}

💪 Keep grinding Ibrahim!"""
    else:
        report = f"""📊 Instagram Report — {now.strftime("%A, %d %b")}

⚠️ Could not fetch live stats right now (Instagram blocking scraping)

💡 TODAY'S AI SUGGESTION:
{suggestion}

💪 Keep grinding Ibrahim!"""
    
    bot.send_message(message.chat.id, report)

@bot.message_handler(commands=['clear'])
def clear_command(message):
    user_conversations[message.chat.id] = []
    bot.reply_to(message, "🔄 Fresh start! What do you need?")

@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    bot.send_chat_action(message.chat.id, 'typing')
    response = chat_with_ai(message.chat.id, message.text)
    bot.send_message(message.chat.id, response)

# ============ MAIN ============
if __name__ == "__main__":
    print("✓ Bot Team is running!")
    print("✓ Bot 1: Smart Assistant — ACTIVE")
    print("✓ Bot 2: Daily Analytics — ACTIVE (sends 9am Dubai time)")
    
    if not TELEGRAM_TOKEN or not GROQ_API_KEY:
        print("❌ Missing API keys!")
        exit(1)
    
    # Start scheduler in background thread
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    
    # Start bot
    bot.polling()
