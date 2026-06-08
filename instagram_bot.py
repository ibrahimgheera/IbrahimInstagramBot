import os
import threading
import schedule
import time
import requests
import json
import hashlib
import langdetect
from datetime import datetime
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

# ============ SYSTEM PROMPT ============
SYSTEM_PROMPT = """You are Ibrahim's personal assistant and Instagram content strategist.

WHO IBRAHIM IS:
- Fitness coach at TK MMAfit Dubai Marina
- Building Gheera Bakery (healthy premium cookies)
- Posts on Instagram about fitness and bakery content

YOUR ROLE: Help with captions, content strategy, post ideas, hashtags, daily tasks, and anything Ibrahim needs.

WHEN IBRAHIM ASKS FOR A CAPTION:
Generate engaging Instagram caption with strong hook, value, CTA, and 8-10 hashtags.

IMPORTANT FOR VOICE REPLIES:
- Keep responses concise and natural — they will be spoken aloud
- Avoid bullet points, asterisks, hashtags, or markdown in voice replies
- Write like you're speaking, not typing"""

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
        system += "\n\nYou are replying via VOICE. Keep it short, natural, conversational. No bullet points, no markdown, no hashtags. Max 3 sentences."
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

# ============ TTS — TEXT TO VOICE ============
def detect_language(text):
    """Detect if text is Arabic or English"""
    try:
        lang = langdetect.detect(text)
        return "arabic" if lang == "ar" else "english"
    except:
        # Fallback: check for Arabic characters
        arabic_chars = sum(1 for c in text if '\u0600' <= c <= '\u06FF')
        return "arabic" if arabic_chars > len(text) * 0.3 else "english"

def text_to_voice(text, language="english"):
    """Convert text to voice using Groq Orpheus TTS — FREE tier"""
    try:
        # Choose model and voice based on language
        if language == "arabic":
            model = "canopylabs/orpheus-arabic-saudi"
            voice = "abdullah"  # calm professional male Arabic voice
        else:
            model = "canopylabs/orpheus-v1-english"
            voice = "daniel"    # natural male English voice

        # Groq TTS has 200 char limit — split if needed
        chunks = []
        words = text.split()
        current = ""
        for word in words:
            if len(current) + len(word) + 1 <= 190:
                current += (" " if current else "") + word
            else:
                if current:
                    chunks.append(current)
                current = word
        if current:
            chunks.append(current)

        # Generate audio for each chunk and combine
        all_audio = b""
        for chunk in chunks:
            response = groq_client.audio.speech.create(
                model=model,
                voice=voice,
                input=chunk,
                response_format="wav"
            )
            # Read bytes from response
            audio_bytes = b""
            for data in response.iter_bytes():
                audio_bytes += data
            all_audio += audio_bytes

        # Save combined audio
        output_path = "/tmp/bot_reply.wav"
        with open(output_path, "wb") as f:
            f.write(all_audio)

        return output_path

    except Exception as e:
        print(f"TTS error: {e}")
        return None

def send_voice_reply(chat_id, text, language="english", reply_to=None):
    """Generate TTS and send as voice note to Telegram"""
    audio_path = text_to_voice(text, language)
    if audio_path:
        with open(audio_path, "rb") as audio:
            if reply_to:
                bot.send_voice(chat_id, audio, reply_to_message_id=reply_to.message_id)
            else:
                bot.send_voice(chat_id, audio)
        return True
    else:
        # Fallback to text if TTS fails
        if reply_to:
            bot.reply_to(reply_to, text)
        else:
            bot.send_message(chat_id, text)
        return False

# ============ SHARED PROCESSING LOGIC ============
def process_text(chat_id, text, reply_to_message=None, voice_reply=False, language="english"):
    """Core logic — handles image requests, reminders, AI chat"""
    text_lower = text.lower()

    def send_text(msg):
        if reply_to_message:
            bot.reply_to(reply_to_message, msg)
        else:
            bot.send_message(chat_id, msg)

    def send_response(msg):
        """Send as voice if voice_reply=True, else as text"""
        if voice_reply:
            send_voice_reply(chat_id, msg, language=language, reply_to=reply_to_message)
        else:
            send_text(msg)

    # IMAGE REQUEST — never reply with voice for these
    image_triggers = ["send me", "show me", "give me", "image", "photo", "picture", "pic"]
    if any(trigger in text_lower for trigger in image_triggers):
        bot.send_chat_action(chat_id, 'upload_photo')
        try:
            response = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": f'Extract the image search query from: "{text}". Reply with ONLY 2-4 words, nothing else.'}],
                max_tokens=20, temperature=0
            )
            query = response.choices[0].message.content.strip().strip('"')
        except:
            query = text
        send_text(f"🔍 Searching for: {query}...")
        send_image(chat_id, query)
        return

    # REMINDER
    reminder_triggers = ["remind me", "reminder", "don't let me forget", "alert me"]
    if any(trigger in text_lower for trigger in reminder_triggers):
        bot.send_chat_action(chat_id, 'typing')
        result = parse_reminder_with_ai(text)
        if result.get("valid"):
            reminders.append({"task": result["task"], "datetime": result["datetime"], "chat_id": chat_id})
            msg = f"Reminder set! I'll remind you to {result['task']} at {result['datetime']}."
            send_response(msg)
            if not voice_reply:
                send_text(f"✅ Reminder set!\n\n📌 Task: {result['task']}\n⏰ Time: {result['datetime']}\n\nI'll message you at that time! 🔔")
        else:
            send_response("I couldn't understand the time for your reminder. Try saying something like: remind me at 3pm to post.")
        return

    # AI ASSISTANT (default)
    bot.send_chat_action(chat_id, 'typing')
    ai_response = chat_with_ai(chat_id, text, voice_mode=voice_reply)
    send_response(ai_response)
    # If voice reply, also send text so Ibrahim can read it
    if voice_reply:
        send_text(f"💬 _{ai_response}_")

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
        local_path = "/tmp/voice_in.ogg"
        with open(local_path, "wb") as f:
            f.write(audio_data)

        # Step 2: Transcribe with Groq Whisper
        with open(local_path, "rb") as audio_file:
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

        # Step 3: Detect language for TTS reply
        language = detect_language(transcribed_text)

        # Step 4: Show what was heard
        bot.reply_to(message, f"🎤 *You said:* _{transcribed_text}_", parse_mode="Markdown")

        # Step 5: Process and reply with voice
        bot.send_chat_action(chat_id, 'record_voice')
        process_text(chat_id, transcribed_text, reply_to_message=None, voice_reply=True, language=language)

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
                image_url = photo["urls"]["regular"]
                photographer = photo["user"]["name"]
                bot.send_photo(chat_id, image_url, caption=f"📸 {query.title()}\nPhoto by {photographer} on Unsplash")
                return True
        headers = {"Authorization": "563492ad6f91700001000001b1e7e6b8e7a748d5a5a5a5a5a5a5a5a5"}
        url = f"https://api.pexels.com/v1/search?query={requests.utils.quote(query)}&per_page=3"
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        if data.get("photos"):
            photo = data["photos"][0]
            bot.send_photo(chat_id, photo["src"]["large"], caption=f"📸 {query.title()}")
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
If you cannot extract a clear time, set valid to false."""}],
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
Send a voice note → I reply with a voice note!
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
    initial_hash = get_website_hash(url)
    tracked_websites[url] = {"hash": initial_hash, "label": label, "chat_id": message.chat.id, "added": datetime.now().strftime("%d %b %H:%M")}
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
    print("✓ Voice IN (Whisper) + Voice OUT (Orpheus TTS)")
    print("✓ Arabic & English")
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
