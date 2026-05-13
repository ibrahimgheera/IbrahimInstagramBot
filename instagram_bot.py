import os
import threading
import schedule
import time
import requests
import json
import hashlib
from datetime import datetime, timedelta
from groq import Groq
import telebot

# ============ CONFIG ============
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
IBRAHIM_CHAT_ID = os.getenv("IBRAHIM_CHAT_ID")
UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY")
INSTAGRAM_USERNAME = "calis_ibra"

bot = telebot.TeleBot(TELEGRAM_TOKEN)
groq_client = Groq(api_key=GROQ_API_KEY)
user_conversations = {}

# Storage
reminders = []
tracked_websites = {}

# ============ BOT 1 — SMART ASSISTANT ============
SYSTEM_PROMPT = """You are Ibrahim's personal assistant and Instagram content strategist.

WHO IBRAHIM IS:
- Fitness coach at TK MMAfit Dubai Marina
- Building Gheera Bakery (healthy premium cookies)
- Posts on Instagram about fitness and bakery content

YOUR ROLE: Help with captions, content strategy, post ideas, hashtags, daily tasks, and anything Ibrahim needs.

WHEN IBRAHIM ASKS FOR A CAPTION:
Generate engaging Instagram caption with strong hook, value, CTA, and 8-10 hashtags.

COMMANDS YOU UNDERSTAND:
- Any question or request → answer helpfully
- Caption requests → generate full caption
- Content ideas → give specific actionable ideas"""

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
        return user["edge_followed_by"]["count"], user["edge_follow"]["count"], user["edge_owner_to_timeline_media"]["count"]
    except:
        return None, None, None

def get_ai_daily_suggestion():
    try:
        day = datetime.now().strftime("%A")
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": f"Ibrahim is a fitness coach in Dubai Marina and runs Gheera Bakery. Today is {day}. Give him 1 Instagram post idea, best time to post, and 1 growth tip. Max 80 words."}],
            max_tokens=150
        )
        return response.choices[0].message.content
    except:
        return "💡 Post a behind-the-scenes story today!"

def send_daily_report():
    if not IBRAHIM_CHAT_ID:
        return
    followers, following, posts = get_instagram_stats()
    suggestion = get_ai_daily_suggestion()
    now = datetime.now()
    if followers:
        report = f"""🌅 Good morning Ibrahim! — {now.strftime("%A, %d %b")}

📊 @calis_ibra
👥 Followers: {followers:,}
➡️ Following: {following:,}
📸 Posts: {posts:,}

💡 TODAY:
{suggestion}

💪 Let's crush it!"""
    else:
        report = f"""🌅 Good morning Ibrahim! — {now.strftime("%A, %d %b")}

💡 TODAY:
{suggestion}

💪 Let's crush it!"""
    bot.send_message(IBRAHIM_CHAT_ID, report)

# ============ BOT 3 — IMAGE SENDER ============
def send_image(chat_id, query):
    try:
        # Try Unsplash first
        if UNSPLASH_ACCESS_KEY:
            url = f"https://api.unsplash.com/search/photos?query={requests.utils.quote(query)}&per_page=3&client_id={UNSPLASH_ACCESS_KEY}"
            response = requests.get(url, timeout=10)
            data = response.json()
            if data.get("results"):
                photo = data["results"][0]
                image_url = photo["urls"]["regular"]
                photographer = photo["user"]["name"]
                bot.send_photo(chat_id, image_url, caption=f"📸 {query.title()}\nPhoto by {photographer} on Unsplash")
                return True

        # Fallback: Pexels API (free)
        headers = {"Authorization": "563492ad6f91700001000001b1e7e6b8e7a748d5a5a5a5a5a5a5a5a5"}
        url = f"https://api.pexels.com/v1/search?query={requests.utils.quote(query)}&per_page=3"
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        if data.get("photos"):
            photo = data["photos"][0]
            image_url = photo["src"]["large"]
            bot.send_photo(chat_id, image_url, caption=f"📸 {query.title()}")
            return True

        bot.send_message(chat_id, f"⚠️ Couldn't find images for '{query}' right now. Try a different keyword!")
        return False
    except Exception as e:
        bot.send_message(chat_id, f"⚠️ Image search failed: {str(e)}")
        return False

# ============ BOT 4 — SMART REMINDERS ============
def parse_reminder_with_ai(text):
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{
                "role": "user",
                "content": f"""Extract reminder details from this message: "{text}"
                
Current time: {datetime.now().strftime("%Y-%m-%d %H:%M")} (Dubai time GST UTC+4)

Reply ONLY with JSON like this, nothing else:
{{
  "task": "what to remind about",
  "datetime": "YYYY-MM-DD HH:MM",
  "valid": true
}}

If you cannot extract a clear time, set valid to false.
Examples:
- "remind me to call Ahmed at 3pm today" → task: "Call Ahmed", datetime: today at 15:00
- "remind me tomorrow 9am to post on instagram" → task: "Post on Instagram", datetime: tomorrow at 09:00
- "remind me in 2 hours to eat" → task: "Eat", datetime: now + 2 hours"""
            }],
            max_tokens=100,
            temperature=0
        )
        raw = response.choices[0].message.content.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except:
        return {"valid": False}

def check_reminders():
    global reminders
    now = datetime.now()
    still_pending = []
    for reminder in reminders:
        remind_time = datetime.strptime(reminder["datetime"], "%Y-%m-%d %H:%M")
        if now >= remind_time:
            try:
                bot.send_message(
                    reminder["chat_id"],
                    f"⏰ REMINDER!\n\n📌 {reminder['task']}\n\nDon't forget! 💪"
                )
            except:
                pass
        else:
            still_pending.append(reminder)
    reminders = still_pending

# ============ BOT 5 — WEBSITE TRACKER ============
def get_website_hash(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=15)
        # Only hash the text content, not headers/timestamps
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(response.text, "html.parser")
        # Remove scripts and styles for cleaner comparison
        for tag in soup(["script", "style", "meta", "time"]):
            tag.decompose()
        content = soup.get_text(separator=" ", strip=True)
        return hashlib.md5(content[:5000].encode()).hexdigest()
    except:
        return None

def check_websites():
    if not tracked_websites:
        return
    for url, data in list(tracked_websites.items()):
        new_hash = get_website_hash(url)
        if new_hash is None:
            continue
        if data["hash"] is None:
            tracked_websites[url]["hash"] = new_hash
            continue
        if new_hash != data["hash"]:
            tracked_websites[url]["hash"] = new_hash
            chat_id = data["chat_id"]
            label = data.get("label", url)
            bot.send_message(
                chat_id,
                f"""🚨 WEBSITE CHANGED!

🌐 {label}
🔗 {url}

Something changed on this page!
Could be a new discount, price change, or update.
Check it now! 👆"""
            )

# ============ SCHEDULER ============
def run_scheduler():
    schedule.every().day.at("05:00").do(send_daily_report)  # 9am Dubai
    schedule.every(1).minutes.do(check_reminders)            # Check reminders every minute
    schedule.every(1).hours.do(check_websites)               # Check websites every hour
    while True:
        schedule.run_pending()
        time.sleep(30)

# ============ TELEGRAM HANDLERS ============
@bot.message_handler(commands=['start'])
def start_command(message):
    bot.reply_to(message, """👋 Hey Ibrahim! Full Bot Team is LIVE! 🚀

🤖 WHAT I CAN DO:

📸 IMAGES — just say:
"send me [anything] image"
"show me [topic] photo"

⏰ REMINDERS — just say:
"remind me at 3pm to post"
"remind me tomorrow 9am to call Ahmed"

🌐 WEBSITE TRACKER:
/track [url] [nickname]
/mytracks — see tracked sites
/untrack [nickname]

📊 REPORTS:
/report — Instagram stats now

💬 ANYTHING ELSE:
Just talk to me naturally!
Captions, ideas, strategy — I got you!""")

@bot.message_handler(commands=['report'])
def report_command(message):
    bot.send_chat_action(message.chat.id, 'typing')
    bot.reply_to(message, "📊 Fetching your stats...")
    followers, following, posts = get_instagram_stats()
    suggestion = get_ai_daily_suggestion()
    now = datetime.now()
    if followers:
        report = f"""📊 @calis_ibra — {now.strftime("%A, %d %b")}
👥 Followers: {followers:,}
➡️ Following: {following:,}
📸 Posts: {posts:,}

💡 {suggestion}"""
    else:
        report = f"""📊 Report — {now.strftime("%A, %d %b")}
⚠️ Could not fetch live stats

💡 {suggestion}"""
    bot.send_message(message.chat.id, report)

@bot.message_handler(commands=['track'])
def track_command(message):
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        bot.reply_to(message, "Usage: /track [url] [nickname]\nExample: /track https://noon.com/uae noon")
        return
    url = parts[1]
    label = parts[2] if len(parts) > 2 else url
    if not url.startswith("http"):
        url = "https://" + url
    bot.reply_to(message, f"⏳ Checking {label}...")
    initial_hash = get_website_hash(url)
    tracked_websites[url] = {
        "hash": initial_hash,
        "label": label,
        "chat_id": message.chat.id,
        "added": datetime.now().strftime("%d %b %H:%M")
    }
    bot.send_message(message.chat.id, f"""✅ Now tracking: {label}
🔗 {url}
⏰ Checks every hour
🔔 I'll alert you when anything changes!

Perfect for tracking discounts, price drops, or any updates!""")

@bot.message_handler(commands=['mytracks'])
def mytracks_command(message):
    if not tracked_websites:
        bot.reply_to(message, "You're not tracking any websites yet!\n\nUse /track [url] [nickname] to start!")
        return
    text = "🌐 YOUR TRACKED WEBSITES:\n\n"
    for url, data in tracked_websites.items():
        text += f"📌 {data['label']}\n🔗 {url}\nAdded: {data['added']}\n\n"
    text += "Use /untrack [nickname] to remove one"
    bot.reply_to(message, text)

@bot.message_handler(commands=['untrack'])
def untrack_command(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "Usage: /untrack [nickname]")
        return
    label = parts[1]
    removed = False
    for url, data in list(tracked_websites.items()):
        if data["label"].lower() == label.lower():
            del tracked_websites[url]
            removed = True
            break
    if removed:
        bot.reply_to(message, f"✅ Stopped tracking: {label}")
    else:
        bot.reply_to(message, f"❌ Couldn't find '{label}'. Use /mytracks to see your list.")

@bot.message_handler(commands=['clear'])
def clear_command(message):
    user_conversations[message.chat.id] = []
    bot.reply_to(message, "🔄 Fresh start!")

@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    text = message.text.lower()

    # IMAGE REQUEST detection
    image_triggers = ["send me", "show me", "give me", "image", "photo", "picture", "pic"]
    is_image_request = any(trigger in text for trigger in image_triggers)

    if is_image_request:
        bot.send_chat_action(message.chat.id, 'upload_photo')
        # Extract search query using AI
        try:
            response = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{
                    "role": "user",
                    "content": f'Extract the image search query from: "{message.text}". Reply with ONLY 2-4 words for the search query, nothing else. Example: "deadlift workout" or "healthy cookies" or "Dubai marina"'
                }],
                max_tokens=20,
                temperature=0
            )
            query = response.choices[0].message.content.strip().strip('"')
        except:
            query = message.text.replace("send me", "").replace("show me", "").replace("image", "").replace("photo", "").strip()

        bot.reply_to(message, f"🔍 Searching for: {query}...")
        send_image(message.chat.id, query)
        return

    # REMINDER detection
    reminder_triggers = ["remind me", "reminder", "don't let me forget", "alert me"]
    is_reminder = any(trigger in text for trigger in reminder_triggers)

    if is_reminder:
        bot.send_chat_action(message.chat.id, 'typing')
        result = parse_reminder_with_ai(message.text)
        if result.get("valid"):
            reminders.append({
                "task": result["task"],
                "datetime": result["datetime"],
                "chat_id": message.chat.id
            })
            bot.reply_to(message, f"""✅ Reminder set!

📌 Task: {result['task']}
⏰ Time: {result['datetime']}

I'll message you automatically at that time! 🔔""")
        else:
            bot.reply_to(message, "⚠️ I couldn't understand the time. Try:\n'Remind me at 3pm to post'\n'Remind me tomorrow 9am to call Ahmed'")
        return

    # Everything else → AI assistant
    bot.send_chat_action(message.chat.id, 'typing')
    response = chat_with_ai(message.chat.id, message.text)
    bot.send_message(message.chat.id, response)

# ============ MAIN ============
if __name__ == "__main__":
    print("✓ Full Bot Team Running!")
    print("✓ Bot 1: Smart Assistant")
    print("✓ Bot 2: Daily Analytics (9am Dubai)")
    print("✓ Bot 3: Image Sender")
    print("✓ Bot 4: Smart Reminders")
    print("✓ Bot 5: Website Tracker")

    if not TELEGRAM_TOKEN or not GROQ_API_KEY:
        print("❌ Missing API keys!")
        exit(1)

    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    bot.polling()
