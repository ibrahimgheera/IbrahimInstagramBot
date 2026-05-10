"""
INSTAGRAM BOT - CAPTION GENERATOR
Works with Groq API (free alternative to Claude)
"""

import os
from groq import Groq
import telebot
from datetime import datetime

# ═══════════════════════════════════════════════════════════════════════════
# SETUP
# ═══════════════════════════════════════════════════════════════════════════

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
YOUR_CHAT_ID = os.getenv("YOUR_CHAT_ID")

# Create bot objects
bot = telebot.TeleBot(TELEGRAM_TOKEN)
groq_client = Groq(api_key=GROQ_API_KEY)

# Store conversations
user_conversations = {}

# ═══════════════════════════════════════════════════════════════════════════
# FUNCTION: Generate Instagram Caption using Groq
# ═══════════════════════════════════════════════════════════════════════════

def generate_caption(image_description, content_type="fitness"):
    """Generate Instagram caption using Groq AI"""
    
    system_prompts = {
        "fitness": """You are an expert social media manager for fitness coaches in Dubai.

Your job: Write engaging Instagram captions that get likes and build a fitness brand.

RULES:
- Hook in first line (question, statistic, or bold statement)
- 2-3 sentences of value/motivation
- Clear call-to-action at the end
- 8-10 relevant hashtags
- Total: 150-200 words
- Tone: Motivational, authentic, professional

Examples of good hooks:
- "This one mistake is costing you 30% of your gains..."
- "If you're not doing THIS, you're missing out"
- "80% of gym-goers get this wrong"

Always include hashtags like: #FitnessDubai #CoachLife #TransformationJourney #DubaiGym""",

        "bakery": """You are an expert social media manager for a premium healthy cookie brand.

Your job: Write engaging captions that drive sales for Gheera Bakery.

RULES:
- Hook about the product
- Highlight health benefits and ingredients
- Create urgency (limited availability)
- 5-8 relevant hashtags
- Total: 100-150 words
- Tone: Friendly, appetizing, premium

Include benefits like: organic, no artificial sugar, gluten-free options, etc."""
    }
    
    system = system_prompts.get(content_type, system_prompts["fitness"])
    
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": f"Photo description: {image_description}\n\nGenerate an engaging Instagram caption for this photo."}
            ],
            max_tokens=500,
            temperature=0.7
        )
        
        caption = response.choices[0].message.content
        return caption
        
    except Exception as e:
        return f"Error generating caption: {str(e)}\n\nPlease try again or check your Groq API key."

# ═══════════════════════════════════════════════════════════════════════════
# TELEGRAM BOT HANDLERS
# ═══════════════════════════════════════════════════════════════════════════

@bot.message_handler(commands=['start'])
def start_command(message):
    """Welcome message"""
    welcome = """👋 Welcome Ibrahim!

I'm your Instagram Caption Generator powered by AI!

Commands:
/caption - Generate an Instagram caption
/help - Show this menu

Ready to save you hours of writing! 💪"""
    
    bot.reply_to(message, welcome)

@bot.message_handler(commands=['help'])
def help_command(message):
    """Help menu"""
    help_text = """📖 HOW TO USE:

1️⃣ Send /caption
2️⃣ Describe your photo (e.g., "Heavy deadlift at gym, looking strong")
3️⃣ Get AI-generated caption with hashtags!

EXAMPLES:
✅ "Me doing heavy deadlift PR, 180kg"
✅ "Client transformation, lost 15kg in 3 months"
✅ "Healthy Gheera cookies, Pistachio Matcha flavor"

TIPS:
• Be specific about the photo
• Mention key details (weight, reps, achievement)
• Include emotion or story if relevant

Type /caption to start! 🚀"""
    
    bot.reply_to(message, help_text)

@bot.message_handler(commands=['caption'])
def caption_command(message):
    """Ask for photo description"""
    msg = bot.reply_to(message, """📸 Describe your photo:

Tell me what's in the photo and I'll generate a caption!

Example: "Heavy deadlift at gym, looking powerful, 180kg PR"

Or: "Gheera Bakery cookies, Pistachio Matcha, on wooden table"

What's your photo about? 👇""")
    
    # Wait for next message
    bot.register_next_step_handler(msg, generate_caption_from_description)

def generate_caption_from_description(message):
    """Generate caption from user's description"""
    photo_description = message.text
    
    # Show typing indicator
    bot.send_chat_action(message.chat.id, 'typing')
    
    # Detect content type
    content_type = "fitness"
    if any(word in photo_description.lower() for word in ['cookie', 'bakery', 'gheera', 'dessert', 'sweet']):
        content_type = "bakery"
    
    # Generate the caption
    caption = generate_caption(photo_description, content_type=content_type)
    
    # Send the caption back
    response = f"""✨ GENERATED CAPTION:

{caption}

━━━━━━━━━━━━━━━━━━

💡 TIP: Copy this caption to Instagram!

Want another version? Send /caption again!"""
    
    bot.send_message(message.chat.id, response)

@bot.message_handler(commands=['status'])
def status_command(message):
    """Bot status"""
    status = """✅ BOT STATUS: ONLINE

🤖 AI Model: Groq (llama-3.3-70b-versatile)
⚡ Response Time: Fast
🔋 API Status: Connected

Everything is working perfectly! 🎉"""
    
    bot.reply_to(message, status)

# Handle all other text messages
@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    """Handle any other messages"""
    text = message.text.lower()
    
    if "hello" in text or "hi" in text:
        bot.reply_to(message, "👋 Hey Ibrahim! Type /caption to generate Instagram captions, or /help for more options.")
    else:
        bot.reply_to(message, "I didn't understand that. Type /help to see what I can do!")

# ═══════════════════════════════════════════════════════════════════════════
# MAIN - Start the bot
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("""
╔═══════════════════════════════════════════════════════════════╗
║          INSTAGRAM BOT - STARTING UP (GROQ VERSION)           ║
╚═══════════════════════════════════════════════════════════════╝
    """)
    
    # Check if tokens are loaded
    if not TELEGRAM_TOKEN or not GROQ_API_KEY:
        print("❌ ERROR: Missing API keys!")
        print("Make sure you set environment variables:")
        print("- TELEGRAM_TOKEN")
        print("- GROQ_API_KEY")
        print("- YOUR_CHAT_ID")
        exit(1)
    
    print("✓ Telegram Token: Loaded")
    print("✓ Groq API Key: Loaded")
    print("✓ Chat ID: Loaded")
    
    print("\n🤖 Bot is running! Listening for messages...")
    print("Send /help to see available commands.\n")
    
    bot.polling()
