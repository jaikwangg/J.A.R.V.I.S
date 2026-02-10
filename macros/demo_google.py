"""
Demo Google Search Macro
"""
import asyncio
import logging
from datetime import datetime

async def run(page, update):
    """
    Demo macro: เปิด Google แล้วค้นหาคำ
    """
    try:
        # Navigate to Google
        await update.message.reply_text("🔍 เปิด Google...")
        await page.goto("https://www.google.com", wait_until="networkidle", timeout=30000)
        
        # Wait for search box and type
        await update.message.reply_text("⌨️ พิมพ์คำค้นหา...")
        search_box = await page.wait_for_selector('input[name="q"]', timeout=15000)
        await search_box.fill("Clawdbot automation")
        
        # Press Enter to search
        await update.message.reply_text("🚀 ค้นหา...")
        await search_box.press("Enter")
        
        # Wait for results
        await page.wait_for_selector('#search', timeout=15000)
        
        # Get page title
        title = await page.title()
        
        await update.message.reply_text(f"✅ เสร็จแล้ว! หน้าปัจจุบัน: {title}")
        
        # Optional: Take screenshot
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_path = f"out/demo_google_{timestamp}.png"
        await page.screenshot(path=screenshot_path)
        
        logging.info("Demo Google macro completed successfully")
        
    except Exception as e:
        logging.error(f"Error in demo_google macro: {e}")
        await update.message.reply_text(f"❌ เกิดข้อผิดพลาด: {str(e)}")
        raise