import os
import threading
import schedule
import time
import asyncio
import requests
import json
import hashlib
from datetime import datetime
from groq import Groq
import telebot
import edge_tts

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

# ============ SYSTEM PROMPT ============
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

# ============ CONVERSATION MEMORY ============
def get_conversation(chat_id):
    if chat_id not in user_conversations:
        user_conversations[chat_id] = []
    return user_conversations[chat_id]

def add_to_conversation(chat_id, role, content):
    conversation = get_conversation(chat_id)
    conversation.append({"role": role, "content": content})
    if len(conversation) > 10:
        user_conversations[chat_id] = conversation[-10:]

def chat_with_ai(chat_id, user_message, voice_mode=False):
    add_to_conversation(chat_id, "user", user_message)
    conversation = get_conversation(chat_id)
    system = SYSTEM_PROMPT
    if voice_mode:
        system += "\n\nIMPORTANT: You are replying by VOICE. Keep it short and natural — max 3 sentences. No bullet points, no asterisks, no hashtags, no markdown. Write exactly as you would speak."
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": system}] + conversation,
            max_tokens=800,
            temperature=0.7
        )
        ai_response = response.choices[0].message.content
        add_to_conversation(chat_id, "assistant", ai_response)
        return ai_response
    except Exception as e:
        return f"Error: {str(e)}"

# ============ FREE TTS — Microsoft Edge (edge-tts) ============
def is_arabic(text):
    """Check if text contains Arabic characters"""
    arabic_chars = sum(1 for c in text if '\u0600' <= c <= '\u06FF')
    return arabic_chars > len(text) * 0.2

async def _generate_voice(text, output_path, arabic=False):
    """Async TTS generation using edge-tts (completely free)"""
    # Arabic: ar-SA-HamedNeural (male) or ar-SA-ZariyahNeural (female)
    # English: en-US-GuyNeural (male) or en-US-JennyNeural (female)
    voice = "ar-SA-HamedNeural" if arabic else "en-US-GuyNeural"
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)

def text_to_voice(text, arabic=False):
    """Convert text to MP3 voice file — returns path or None"""
    try:
        output_path = "/tmp/bot_reply.mp3"
        # Clean text for speech (remove markdown symbols)
        clean = text.replace("*", "").replace("_", "").replace("#", "").replace("`", "")
        # Run async TTS
        asyncio.run(_generate_voice(clean, output_path, arabic=arabic))
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return output_path
        return None
    except Exception as e:
        print(f"TTS error: {e}")
        return None

# ============ SHARED PROCESSING LOGIC ============
def process_text(chat_id, text, reply_to_message=None, voice_reply=False):
    """Core logic — handles image requests, reminders, AI chat"""
    text_lower = text.lower()
    arabic = is_arabic(text)

    def send_text(msg):
        if reply_to_message:
            bot.reply_to(reply_to_message, msg)
        else:
            bot.send_message(chat_id, msg)

    def send_response(msg):
        if voice_reply:
            audio_path = text_to_voice(msg, arabic=arabic)
            if audio_path:
                with open(audio_path, "rb") as audio:
                    bot.send_voice(chat_id, audio)
                # Also send text so Ibrahim can read it
                send_text(f"💬 _{msg}_")
            else:
                # TTS failed — fall back to text
                send_text(msg)
        else:
            send_text(msg)

    # IMAGE REQUEST — always text reply for these
    image_triggers = ["send me", "show me", "give me", "image", "photo", "picture", "pic",
                      "ابعت", "اعطني", "صورة", "صوره"]
    if any(trigger in text_lower for trigger in image_triggers):
        bot.send_chat_action(chat_id, 'upload_photo')
        try:
            response = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": f'Extract the image search query from: "{text}". Reply with ONLY 2-4 English words, nothing else.'}],
                max_tokens=20, temperature=0
            )
            query = response.choices[0].message.content.strip().strip('"')
        except:
            query = text
        send_text(f"🔍 Searching for: {query}...")
        send_image(chat_id, query)
        return

    # REMINDER
    reminder_triggers = ["remind me", "reminder", "don't let me forget", "alert me",
                         "ذكرني", "تذكير", "ذكر"]
    if any(trigger in text_lower for trigger in reminder_triggers):
        bot.send_chat_action(chat_id, 'typing')
        result = parse_reminder_with_ai(text)
        if result.get("valid"):
            reminders.append({"task": result["task"], "datetime": result["datetime"], "chat_id": chat_id})
            if voice_reply:
                send_response(f"Reminder set! I'll remind you to {result['task']} at {result['datetime']}.")
            else:
                send_text(f"✅ Reminder set!\n\n📌 Task: {result['task']}\n⏰ Time: {result['datetime']}\n\nI'll message you at that time! 🔔")
        else:
            send_response("I couldn't understand the time. Try: remind me at 3pm to post.")
        return

    # AI ASSISTANT (default)
    bot.send_chat_action(chat_id, 'typing')
    ai_response = chat_with_ai(chat_id, text, voice_mode=voice_reply)
    send_response(ai_response)

# ============ VOICE MESSAGE HANDLER — must be before catch-all ============
@bot.message_handler(content_types=['voice'])
def handle_voice(message):
    chat_id = message.chat.id
    bot.send_chat_action(chat_id, 'typing')

    try:
        # Step 1: Download voice from Telegram
        file_info = bot.get_file(message.voice.file_id)
        file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_info.file_path}"
        audio_data = requests.get(file_url).content
        with open("/tmp/voice_in.ogg", "wb") as f:
            f.write(audio_data)

        # Step 2: Transcribe with Groq Whisper (free)
        with open("/tmp/voice_in.ogg", "rb") as audio_file:
            transcription = requests.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                files={"file": ("voice.ogg", audio_file, "audio/ogg")},
                data={"model": "whisper-large-v3-turbo", "response_format": "json"}
            )

        transcribed_text = transcription.json().get("text", "").strip()
        if not transcribed_text:
            bot.reply_to(message, "⚠️ Couldn't understand the voice. Please try again.")
            return

        # Step 3: Show what was heard
        bot.reply_to(message, f"🎤 *You said:* _{transcribed_text}_", parse_mode="Markdown")

        # Step 4: Generate voice reply
        bot.send_chat_action(chat_id, 'record_voice')
        process_text(chat_id, transcribed_text, reply_to_message=None, voice_reply=True)

    except Exception as e:
        bot.reply_to(message, f"⚠️ Voice error: {str(e)}")
        print(f"Voice handler error: {e}")

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
        if UNSPLASH_ACCESS_KEY:
            url = f"https://api.unsplash.com/search/photos?query={requests.utils.quote(query)}&per_page=3&client_id={UNSPLASH_ACCESS_KEY}"
            response = requests.get(url, timeout=10)
            data = response.json()
            if data.get("results"):
                photo = data["results"][0]
                bot.send_photo(chat_id, photo["urls"]["regular"], caption=f"📸 {query.title()}\nPhoto by {photo['user']['name']} on Unsplash")
                return True
        headers = {"Authorization": "563492ad6f91700001000001b1e7e6b8e7a748d5a5a5a5a5a5a5a5a5"}
        url = f"https://api.pexels.com/v1/search?query={requests.utils.quote(query)}&per_page=3"
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        if data.get("photos"):
            bot.send_photo(chat_id, data["photos"][0]["src"]["large"], caption=f"📸 {query.title()}")
            return True
        bot.send_message(chat_id, f"⚠️ Couldn't find images for '{query}'. Try a different keyword!")
        return False
    except Exception as e:
        bot.send_message(chat_id, f"⚠️ Image search failed: {str(e)}")
        return False

# ============ BOT 4 — SMART REMINDERS ============
def parse_reminder_with_ai(text):
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": f"""Extract reminder details from: "{text}"
Current time: {datetime.now().strftime("%Y-%m-%d %H:%M")} (Dubai time GST UTC+4)
Reply ONLY with JSON, nothing else:
{{"task": "what to remind about", "datetime": "YYYY-MM-DD HH:MM", "valid": true}}
If no clear time, set valid to false."""}],
            max_tokens=100, temperature=0
        )
        raw = response.choices[0].message.content.strip().replace("```json", "").replace("```", "").strip()
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
                bot.send_message(reminder["chat_id"], f"⏰ REMINDER!\n\n📌 {reminder['task']}\n\nDon't forget! 💪")
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
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(response.text, "html.parser")
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
            bot.send_message(data["chat_id"], f"🚨 WEBSITE CHANGED!\n\n🌐 {data.get('label', url)}\n🔗 {url}\n\nCheck it now! 👆")

# ============ SCHEDULER ============
def run_scheduler():
    schedule.every().day.at("05:00").do(send_daily_report)
    schedule.every(1).minutes.do(check_reminders)
    schedule.every(1).hours.do(check_websites)
    while True:
        schedule.run_pending()
        time.sleep(30)

# ============ TELEGRAM HANDLERS ============
@bot.message_handler(commands=['start'])
def start_command(message):
    bot.reply_to(message, """👋 Hey Ibrahim! I'm live! 🚀

🎤 VOICE IN + VOICE OUT
Send me a voice note → I reply with a voice note!
Works in Arabic 🇸🇦 and English 🇬🇧

📸 IMAGES — "send me [topic] image"
⏰ REMINDERS — "remind me at 3pm to post"
🌐 TRACK — /track [url] [nickname]
📊 REPORT — /report
🔄 CLEAR — /clear

💬 Or just type normally!""")

@bot.message_handler(commands=['report'])
def report_command(message):
    bot.send_chat_action(message.chat.id, 'typing')
    bot.reply_to(message, "📊 Fetching your stats...")
    followers, following, posts = get_instagram_stats()
    suggestion = get_ai_daily_suggestion()
    now = datetime.now()
    if followers:
        report = f"📊 @calis_ibra — {now.strftime('%A, %d %b')}\n👥 Followers: {followers:,}\n➡️ Following: {following:,}\n📸 Posts: {posts:,}\n\n💡 {suggestion}"
    else:
        report = f"📊 Report — {now.strftime('%A, %d %b')}\n⚠️ Could not fetch live stats\n\n💡 {suggestion}"
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
    tracked_websites[url] = {"hash": get_website_hash(url), "label": label, "chat_id": message.chat.id, "added": datetime.now().strftime("%d %b %H:%M")}
    bot.send_message(message.chat.id, f"✅ Now tracking: {label}\n🔗 {url}\n⏰ Checks every hour")

@bot.message_handler(commands=['mytracks'])
def mytracks_command(message):
    if not tracked_websites:
        bot.reply_to(message, "Not tracking any websites yet!\nUse /track [url] [nickname] to start!")
        return
    text = "🌐 YOUR TRACKED WEBSITES:\n\n"
    for url, data in tracked_websites.items():
        text += f"📌 {data['label']}\n🔗 {url}\nAdded: {data['added']}\n\n"
    bot.reply_to(message, text)

@bot.message_handler(commands=['untrack'])
def untrack_command(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "Usage: /untrack [nickname]")
        return
    label = parts[1]
    for url, data in list(tracked_websites.items()):
        if data["label"].lower() == label.lower():
            del tracked_websites[url]
            bot.reply_to(message, f"✅ Stopped tracking: {label}")
            return
    bot.reply_to(message, f"❌ Couldn't find '{label}'. Use /mytracks to see your list.")

@bot.message_handler(commands=['clear'])
def clear_command(message):
    user_conversations[message.chat.id] = []
    bot.reply_to(message, "🔄 Fresh start!")

# ============ TEXT HANDLER — catch-all (MUST be last) ============
@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_text_messages(message):
    process_text(message.chat.id, message.text, reply_to_message=message, voice_reply=False)

# ============ MAIN ============
if __name__ == "__main__":
    print("✓ Bot Running!")
    print("✓ Voice IN (Groq Whisper) + Voice OUT (edge-tts, FREE)")
    print("✓ Arabic & English support")
    print("✓ Smart Assistant | Daily Analytics | Images | Reminders | Website Tracker")

    if not TELEGRAM_TOKEN or not GROQ_API_KEY:
        print("❌ Missing TELEGRAM_TOKEN or GROQ_API_KEY!")
        exit(1)

    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()

    while True:
        try:
            print("🔄 Bot polling started...")
            bot.polling(none_stop=True, timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"⚠️ Connection dropped: {e}")
            print("🔄 Restarting in 10 seconds...")
            time.sleep(10)
