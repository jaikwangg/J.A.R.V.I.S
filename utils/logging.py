"""
Logging utilities
"""
import logging
import logging.handlers
from pathlib import Path
import yaml

def setup_logging():
    """Setup logging configuration"""
    # Ensure log directory exists
    Path('out').mkdir(exist_ok=True)
    
    # Load logging config
    try:
        with open('config/settings.yaml', 'r', encoding='utf-8') as f:
            settings = yaml.safe_load(f) or {}
    except:
        settings = {}
    
    log_config = settings.get('logging', {})
    log_level = log_config.get('level', 'INFO')
    log_file = log_config.get('file', 'out/clawdbot.log')
    max_size_mb = log_config.get('max_size_mb', 10)
    backup_count = log_config.get('backup_count', 5)
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Setup root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # File handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=max_size_mb * 1024 * 1024,
        backupCount=backup_count,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    # Reduce noise from some libraries
    logging.getLogger('telegram').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('playwright').setLevel(logging.WARNING)
    
    logging.info("Logging setup complete")