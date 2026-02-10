"""
Security Manager - Handle authorization and safety checks
"""
import os
import time
import logging
from typing import List, Set
from collections import defaultdict, deque
import yaml

class SecurityManager:
    def __init__(self):
        self.settings = self._load_settings()
        self.rate_limiter = defaultdict(deque)
        self.blocked_users: Set[int] = set()
        
    def _load_settings(self) -> dict:
        """Load security settings"""
        try:
            with open('config/settings.yaml', 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logging.error(f"Error loading settings: {e}")
            return {}
    
    def is_authorized_user(self, user_id: int) -> bool:
        """Check if user is authorized"""
        if user_id in self.blocked_users:
            logging.warning(f"Blocked user attempted access: {user_id}")
            return False
        
        # Check allowlist from settings.yaml
        allowed_ids = self.settings.get('security', {}).get('allow_user_ids', [])
        
        # Also check from .env as fallback
        env_ids = os.getenv('ADMIN_USER_IDS', '')
        if env_ids:
            try:
                env_allowed = [int(x.strip()) for x in env_ids.split(',') if x.strip()]
                allowed_ids.extend(env_allowed)
            except ValueError:
                logging.error("Invalid ADMIN_USER_IDS format in .env")
        
        if not allowed_ids:
            logging.warning("No authorized users configured!")
            return False
        
        is_allowed = user_id in allowed_ids
        
        if not is_allowed:
            logging.warning(f"Unauthorized access attempt from user: {user_id}")
        
        return is_allowed
    
    def check_rate_limit(self, user_id: int) -> bool:
        """Check if user is within rate limits"""
        current_time = time.time()
        rate_limit = self.settings.get('security', {}).get('rate_limit_per_min', 20)
        
        # Clean old entries (older than 1 minute)
        user_requests = self.rate_limiter[user_id]
        while user_requests and current_time - user_requests[0] > 60:
            user_requests.popleft()
        
        # Check if under limit
        if len(user_requests) >= rate_limit:
            logging.warning(f"Rate limit exceeded for user: {user_id}")
            return False
        
        # Add current request
        user_requests.append(current_time)
        return True
    
    def requires_confirmation(self, macro_name: str) -> bool:
        """Check if macro requires confirmation"""
        confirm_list = self.settings.get('security', {}).get('require_confirm_for_macros', [])
        return macro_name in confirm_list
    
    def block_user(self, user_id: int, reason: str = "Security violation"):
        """Block a user"""
        self.blocked_users.add(user_id)
        logging.warning(f"User {user_id} blocked: {reason}")
    
    def unblock_user(self, user_id: int):
        """Unblock a user"""
        self.blocked_users.discard(user_id)
        logging.info(f"User {user_id} unblocked")
    
    def is_safe_url(self, url: str) -> bool:
        """Check if URL is safe to visit"""
        # Basic URL safety checks
        dangerous_patterns = [
            'javascript:',
            'data:',
            'file://',
            'ftp://',
        ]
        
        url_lower = url.lower()
        for pattern in dangerous_patterns:
            if pattern in url_lower:
                logging.warning(f"Dangerous URL blocked: {url}")
                return False
        
        return True
    
    def validate_macro_name(self, macro_name: str) -> bool:
        """Validate macro name for security"""
        # Only allow alphanumeric and underscore
        if not macro_name.replace('_', '').isalnum():
            logging.warning(f"Invalid macro name: {macro_name}")
            return False
        
        # Prevent path traversal
        if '..' in macro_name or '/' in macro_name or '\\' in macro_name:
            logging.warning(f"Path traversal attempt in macro name: {macro_name}")
            return False
        
        return True