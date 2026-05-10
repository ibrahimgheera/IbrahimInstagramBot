"""
SMART INSTAGRAM BOT - Conversational AI Assistant
"""

import os
from groq import Groq
import telebot

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
groq_client = Groq(api_key=GROQ_API_KEY)

user_conversations = {}

SMART_BOT_SYSTEM = """You are Ibrahim's personal Instagram content strategist and AI assistant.

WHO IBRAHIM IS:
- Fitness coach at TK MMAfit Dubai Marina
- Building Gheera Bakery (healthy premium cookies)
- Posts on Instagram about fitness and bakery content
- Wants to grow his brand and save time

YOUR ROLE: Help Ibrahim with captions, content strategy, post ideas, hashtags, scheduling advice, and social media growth. Be his creative partner.

YOUR PERSONALITY:
- Smart and helpful
- Direct and actionable (Ibrahim is busy)
- Expert in fitness and food content
- Knows Dubai market

WHEN IBRAHIM ASKS FOR A CAPTION:
Generate engaging Instagram caption with:
- Strong hook (question, stat, or bold statement)
- 2-3 sentences of value
- Clear call-to-action
- 8-10 relevant hashtags
- Keep it 150-200 words

Just talk naturally and be genuinely helpful!"""

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
            messages=[{"role": "system", "content": SMART_BOT_SYSTEM}] + conversation,
            max_tokens=800,
            temperature=0.7
        )
        ai_response = response.choices[0].message.content
        add_to_conversation(chat_id, "assistant", ai_response)
        return ai_response
    except Exception as e:
        return f"Error: {str(e)}"

@bot.message_handler(commands=['start'])
def start_command(message):
    bot.reply_to(message, "👋 Hey Ibrahim! I'm your smart Instagram assistant.\n\nJust talk to me naturally! Try:\n• \"Give me a caption for my deadlift video\"\n• \"What should I post this week?\"\n• \"How do I get more followers?\"\n• \"I need bakery content ideas\"\n\nI can have real conversations now! 🚀")

@bot.message_handler(commands=['clear'])
def clear_command(message):
    user_conversations[message.chat.id] = []
    bot.reply_to(message, "🔄 Fresh start! What do you need?")

@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    bot.send_chat_action(message.chat.id, 'typing')
    response = chat_with_ai(message.chat.id, message.text)
    bot.send_message(message.chat.id, response)

if __name__ == "__main__":
    print("✓ Smart Bot is running!")
    if not TELEGRAM_TOKEN or not GROQ_API_KEY:
        print("❌ Missing API keys!")
        exit(1)
    bot.polling()
