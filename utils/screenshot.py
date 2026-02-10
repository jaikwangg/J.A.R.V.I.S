"""
Screenshot utilities
"""
import mss
import logging
from datetime import datetime
from pathlib import Path
from PIL import Image

class ScreenshotManager:
    def __init__(self):
        self.output_dir = Path('out')
        self.output_dir.mkdir(exist_ok=True)
    
    def take_desktop_screenshot(self) -> str:
        """Take screenshot of entire desktop"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"desktop_{timestamp}.png"
            filepath = self.output_dir / filename
            
            with mss.mss() as sct:
                # Capture primary monitor
                monitor = sct.monitors[1]
                screenshot = sct.grab(monitor)
                
                # Convert to PIL Image and save
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                img.save(str(filepath))
                
            logging.info(f"Desktop screenshot saved: {filepath}")
            return str(filepath)
            
        except Exception as e:
            logging.error(f"Error taking desktop screenshot: {e}")
            return None
    
    def take_region_screenshot(self, x: int, y: int, width: int, height: int) -> str:
        """Take screenshot of specific region"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"region_{timestamp}.png"
            filepath = self.output_dir / filename
            
            with mss.mss() as sct:
                region = {"top": y, "left": x, "width": width, "height": height}
                screenshot = sct.grab(region)
                
                # Convert to PIL Image and save
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                img.save(str(filepath))
                
            logging.info(f"Region screenshot saved: {filepath}")
            return str(filepath)
            
        except Exception as e:
            logging.error(f"Error taking region screenshot: {e}")
            return None