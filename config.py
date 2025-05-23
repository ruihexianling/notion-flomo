import os
import logging
import sys

# Flomo配置
FLOMO_DOMAIN = "https://flomoapp.com"
MEMO_LIST_URL = FLOMO_DOMAIN + "/api/v1/memo/updated/"

# Telegram通知配置
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# 基本配置
DEBUG = os.getenv('DEBUG', 'false').lower() == 'true'
LOG_LEVEL = logging.DEBUG if DEBUG else logging.ERROR

# 日志配置
def setup_logging():
    logging.basicConfig(
        level=LOG_LEVEL,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # 设置第三方库的日志级别
    if not DEBUG:
        logging.getLogger('notion_client').setLevel(logging.ERROR)
        logging.getLogger('notion_client.api_endpoints').setLevel(logging.ERROR)
        logging.getLogger('urllib3').setLevel(logging.ERROR)
        logging.getLogger('requests').setLevel(logging.ERROR)
        logging.getLogger('httpx').setLevel(logging.ERROR)
    
    # 返回主日志记录器
    return logging.getLogger('flomo2notion')


def get_logger(name):
    """
    获取指定名称的日志器，确保日志系统已初始化

    Args:
        name: 日志器名称

    Returns:
        Logger: 配置好的日志器
    """
    # 确保日志系统已初始化
    setup_logging()
    return logging.getLogger(name)

# 创建默认日志记录器
logger = setup_logging() 