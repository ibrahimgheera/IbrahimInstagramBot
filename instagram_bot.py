import os
import telebot
import anthropic

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY")
YOUR_CHAT_ID = os.environ.get("YOUR_CHAT_ID")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

waiting_for_description = {}

def generate_caption(description):
    message = client.messages.create(
        model="claude-opus-4-20250514",
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": f"""You are an expert Instagram caption writer for a fitness coach and healthy bakery brand in Dubai.

Write an Instagram caption for this post: {description}

Format:
- Hook (first line, attention grabbing)
- 2-3 lines of value or story
- Call to action
- Line break
- 10-15 relevant hashtags

Make it engaging, authentic, and suited for Dubai/fitness/healthy lifestyle audience."""
            }
        ]
    )
    return message.content[0].text

@bot.message_handler(commands=['start', 'help'])
def help_command(message):
    bot.reply_to(message, """👋 Welcome Ibrahim!

Commands:
/caption - Generate an Instagram caption
/help - Show this menu

Ready to save you hours of writing! 💪""")

@bot.message_handler(commands=['caption'])
def caption_command(message):
    waiting_for_description[message.chat.id] = True
    bot.reply_to(message, "📸 Describe your post and I'll write the caption!\n\nExample: Heavy deadlift at the gym today, new PR")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    if waiting_for_description.get(message.chat.id):
        waiting_for_description[message.chat.id] = False
        bot.reply_to(message, "✍️ Writing your caption...")
        try:
            caption = generate_caption(message.text)
            bot.reply_to(message, caption)
        except Exception as e:
            bot.reply_to(message, f"❌ Error: {str(e)}")
    else:
        bot.reply_to(message, "Use /caption to generate an Instagram caption!")

print("✓ Bot is running!")
bot.infinity_polling()
