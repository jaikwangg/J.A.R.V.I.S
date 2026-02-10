"""
Bot Runner - Core execution engine
"""
import asyncio
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Any
import yaml
from playwright.async_api import async_playwright, Browser, Page

from utils.screenshot import ScreenshotManager
from engine.safety import SecurityManager

class BotRunner:
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.playwright = None
        self.current_job_id: Optional[str] = None
        self.pending_confirmations: Dict[str, Dict] = {}
        
        # Load configurations
        self.settings = self._load_yaml('config/settings.yaml')
        self.macros_config = self._load_yaml('config/macros.yaml')
        
        self.screenshot_manager = ScreenshotManager()
        self.security = SecurityManager()
        
        # Ensure output directory exists
        Path('out').mkdir(exist_ok=True)
    
    def _load_yaml(self, path: str) -> Dict:
        """Load YAML configuration file"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            logging.warning(f"Config file not found: {path}")
            return {}
        except Exception as e:
            logging.error(f"Error loading {path}: {e}")
            return {}
    
    async def _ensure_browser(self):
        """Ensure browser is running"""
        try:
            # Check if browser is still alive
            if self.browser and self.page:
                try:
                    # Test if page is still alive
                    await self.page.evaluate("1 + 1")
                    return  # Browser is working fine
                except:
                    # Browser/page is dead, need to recreate
                    logging.info("Browser/page is dead, recreating...")
                    await self._cleanup_browser()
            
            # Start playwright if needed
            if self.playwright is None:
                self.playwright = await async_playwright().start()
            
            chrome_config = self.settings.get('chrome', {})
            mode = chrome_config.get('mode', 'chromium')
            
            if mode == 'chromium':
                # Use Playwright's Chromium
                args = chrome_config.get('args', [])
                self.browser = await self.playwright.chromium.launch(
                    headless=self.settings.get('runtime', {}).get('headless', False),
                    args=args
                )
                self.page = await self.browser.new_page()
            else:
                # Use existing Chrome profile
                chrome_exe = chrome_config.get('chrome_exe')
                user_data_dir = chrome_config.get('user_data_dir')
                profile_dir = chrome_config.get('profile_dir', 'Default')
                
                if not chrome_exe or not user_data_dir:
                    raise ValueError("Chrome exe and user_data_dir required for profile mode")
                
                self.browser = await self.playwright.chromium.launch_persistent_context(
                    user_data_dir=f"{user_data_dir}\\{profile_dir}",
                    executable_path=chrome_exe,
                    headless=self.settings.get('runtime', {}).get('headless', False)
                )
                
                # For persistent context
                pages = self.browser.pages
                self.page = pages[0] if pages else await self.browser.new_page()
            
            # Set viewport
            window_size = self.settings.get('chrome', {}).get('window_size', [1280, 720])
            await self.page.set_viewport_size({"width": window_size[0], "height": window_size[1]})
            
            logging.info("Browser initialized successfully")
            
        except Exception as e:
            logging.error(f"Error ensuring browser: {e}")
            await self._cleanup_browser()
            raise
    
    async def run_macro(self, update, macro_name: str):
        """Run a macro"""
        try:
            # Check if macro exists and is enabled
            macros = self.macros_config.get('macros', {})
            if macro_name not in macros:
                await update.message.reply_text(f"❌ Macro '{macro_name}' not found")
                return
            
            macro_config = macros[macro_name]
            if not macro_config.get('enabled', False):
                await update.message.reply_text(f"❌ Macro '{macro_name}' is disabled")
                return
            
            # Check if confirmation required
            if macro_config.get('requires_confirm', False):
                job_id = str(uuid.uuid4())[:8]
                self.pending_confirmations[job_id] = {
                    'macro_name': macro_name,
                    'user_id': update.effective_user.id,
                    'timestamp': datetime.now(),
                    'update': update
                }
                
                await update.message.reply_text(
                    f"⚠️ Macro '{macro_name}' requires confirmation\n"
                    f"Description: {macro_config.get('description', 'N/A')}\n\n"
                    f"Use `/confirm {job_id}` to proceed"
                )
                return
            
            # Run macro directly
            await self._execute_macro(update, macro_name)
            
        except Exception as e:
            logging.error(f"Error running macro {macro_name}: {e}")
            await update.message.reply_text(f"❌ Error: {str(e)}")
    
    async def confirm_job(self, update, job_id: str):
        """Confirm and execute pending job"""
        if job_id not in self.pending_confirmations:
            await update.message.reply_text(f"❌ Job ID '{job_id}' not found or expired")
            return
        
        job = self.pending_confirmations[job_id]
        
        # Verify user
        if job['user_id'] != update.effective_user.id:
            await update.message.reply_text("❌ You can only confirm your own jobs")
            return
        
        # Execute the macro
        macro_name = job['macro_name']
        await update.message.reply_text(f"✅ Confirmed! Executing '{macro_name}'...")
        
        # Remove from pending
        del self.pending_confirmations[job_id]
        
        # Execute
        await self._execute_macro(update, macro_name)
    
    async def _execute_macro(self, update, macro_name: str):
        """Execute macro implementation"""
        try:
            self.current_job_id = str(uuid.uuid4())[:8]
            
            await update.message.reply_text(f"🚀 Starting macro: {macro_name}")
            
            # Ensure browser is ready
            await self._ensure_browser()
            
            # Import and run macro
            macro_module = __import__(f'macros.{macro_name}', fromlist=[''])
            
            if hasattr(macro_module, 'run'):
                await macro_module.run(self.page, update)
                await update.message.reply_text(f"✅ Macro '{macro_name}' completed successfully")
            else:
                await update.message.reply_text(f"❌ Macro '{macro_name}' has no run function")
                
        except Exception as e:
            logging.error(f"Error executing macro {macro_name}: {e}")
            
            # Take error screenshot
            if self.settings.get('runtime', {}).get('screenshot_on_error', True):
                screenshot_path = await self.take_screenshot()
                if screenshot_path:
                    with open(screenshot_path, 'rb') as photo:
                        await update.message.reply_photo(
                            photo, 
                            caption=f"❌ Error in '{macro_name}': {str(e)}"
                        )
                else:
                    await update.message.reply_text(f"❌ Error in '{macro_name}': {str(e)}")
            else:
                await update.message.reply_text(f"❌ Error in '{macro_name}': {str(e)}")
        finally:
            self.current_job_id = None
    
    async def take_screenshot(self) -> Optional[str]:
        """Take screenshot of current page"""
        try:
            await self._ensure_browser()
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = f"out/screenshot_{timestamp}.png"
            
            await self.page.screenshot(path=screenshot_path, full_page=True)
            return screenshot_path
            
        except Exception as e:
            logging.error(f"Error taking screenshot: {e}")
            # Try desktop screenshot as fallback
            try:
                return self.screenshot_manager.take_desktop_screenshot()
            except:
                return None
    
    async def stop_current_job(self):
        """Stop current job"""
        if self.current_job_id:
            logging.info(f"Stopping job: {self.current_job_id}")
            self.current_job_id = None
            # Additional cleanup if needed
    
    def get_available_macros(self) -> Dict[str, str]:
        """Get list of available macros"""
        macros = {}
        for name, config in self.macros_config.get('macros', {}).items():
            if config.get('enabled', False):
                macros[name] = config.get('description', 'No description')
        return macros
    
    def get_status(self) -> str:
        """Get bot status"""
        status_parts = []
        
        if self.browser:
            status_parts.append("🌐 Browser: Ready")
        else:
            status_parts.append("🌐 Browser: Not started")
        
        if self.current_job_id:
            status_parts.append(f"⚙️ Job: {self.current_job_id}")
        else:
            status_parts.append("⚙️ Job: Idle")
        
        if self.pending_confirmations:
            status_parts.append(f"⏳ Pending: {len(self.pending_confirmations)}")
        
        return "\n".join(status_parts)
    
    async def _cleanup_browser(self):
        """Clean up browser resources"""
        try:
            if self.page:
                await self.page.close()
                self.page = None
        except:
            pass
        
        try:
            if self.browser:
                await self.browser.close()
                self.browser = None
        except:
            pass
    
    async def cleanup(self):
        """Cleanup resources"""
        await self._cleanup_browser()
        
        try:
            if self.playwright:
                await self.playwright.stop()
                self.playwright = None
        except:
            pass