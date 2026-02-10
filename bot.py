#!/usr/bin/env python3
"""
Clawdbot - Secure, Config-driven Telegram Bot for Browser Automation
"""
import os
import asyncio
import logging
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from engine.runner import BotRunner
from engine.safety import SecurityManager
from utils.logging import setup_logging

# Load environment variables
load_dotenv()

class ClawdBot:
    def __init__(self):
        self.runner = BotRunner()
        self.security = SecurityManager()
        
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command handler"""
        if not self.security.is_authorized_user(update.effective_user.id):
            if update.message:
                await update.message.reply_text("❌ Unauthorized access")
            return
            
        await update.message.reply_text(
            "🤖 Clawdbot Ready!\n\n"
            "Commands:\n"
            "/run <macro> - Run a macro\n"
            "/list - List available macros\n"
            "/status - Bot status\n"
            "/shot - Take screenshot\n"
            "/stop - Stop current job\n"
            "/confirm <job_id> - Confirm pending action"
        )
    
    async def run_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Run macro command"""
        if not self.security.is_authorized_user(update.effective_user.id):
            if update.message:
                await update.message.reply_text("❌ Unauthorized")
            return
            
        if not context.args:
            await update.message.reply_text("Usage: /run <macro_name>")
            return
            
        macro_name = context.args[0]
        await self.runner.run_macro(update, macro_name)
    
    async def list_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List available macros"""
        if not self.security.is_authorized_user(update.effective_user.id):
            return
            
        macros = self.runner.get_available_macros()
        if not macros:
            await update.message.reply_text("No macros available")
            return
            
        macro_list = "\n".join([f"• {name}: {desc}" for name, desc in macros.items()])
        await update.message.reply_text(f"📋 Available Macros:\n\n{macro_list}")
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Bot status"""
        if not self.security.is_authorized_user(update.effective_user.id):
            return
            
        status = self.runner.get_status()
        await update.message.reply_text(f"🔍 Status: {status}")
    
    async def stop_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Stop current job"""
        if not self.security.is_authorized_user(update.effective_user.id):
            return
            
        await self.runner.stop_current_job()
        await update.message.reply_text("🛑 Stopping current job...")
    
    async def shot_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Take screenshot"""
        if not self.security.is_authorized_user(update.effective_user.id):
            return
            
        screenshot_path = await self.runner.take_screenshot()
        if screenshot_path:
            with open(screenshot_path, 'rb') as photo:
                await update.message.reply_photo(photo, caption="📸 Current screen")
        else:
            await update.message.reply_text("❌ Failed to take screenshot")
    
    async def confirm_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Confirm pending action"""
        if not self.security.is_authorized_user(update.effective_user.id):
            return
            
        if not context.args:
            await update.message.reply_text("Usage: /confirm <job_id>")
            return
            
        job_id = context.args[0]
        await self.runner.confirm_job(update, job_id)

def main():
    """Main function"""
    # Setup logging
    setup_logging()
    
    # Get bot token
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        logging.error("TELEGRAM_BOT_TOKEN not found in environment")
        return
    
    # Create bot instance
    bot = ClawdBot()
    
    # Create application
    app = Application.builder().token(token).build()
    
    # Add handlers
    app.add_handler(CommandHandler("start", bot.start_command))
    app.add_handler(CommandHandler("run", bot.run_command))
    app.add_handler(CommandHandler("list", bot.list_command))
    app.add_handler(CommandHandler("status", bot.status_command))
    app.add_handler(CommandHandler("stop", bot.stop_command))
    app.add_handler(CommandHandler("shot", bot.shot_command))
    app.add_handler(CommandHandler("confirm", bot.confirm_command))
    
    # Start bot
    logging.info("Starting Clawdbot...")
    app.run_polling()

if __name__ == "__main__":
    main()