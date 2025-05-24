import requests
from config import get_logger, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
logger = get_logger(__name__)

def split_long_text(text, max_length=1900):
    """
    将长文本分割成多个小块，每个块不超过指定的最大长度
    
    Args:
        text (str): 要分割的文本
        max_length (int): 每个块的最大长度，默认为1900（留出一些余量）
        
    Returns:
        list: 分割后的文本块列表
    """
    if not text or len(text) <= max_length:
        return [text]
        
    chunks = []
    current_pos = 0
    text_length = len(text)
    
    while current_pos < text_length:
        # 如果剩余文本长度小于等于最大长度，直接添加
        if current_pos + max_length >= text_length:
            chunks.append(text[current_pos:])
            break
            
        # 尝试在最大长度位置附近找到一个合适的分割点（如句号、换行符等）
        end_pos = current_pos + max_length
        
        # 优先在句号、问号、感叹号、换行符处分割
        for char in ['\n', '。', '！', '？', '.', '!', '?']:
            last_char_pos = text.rfind(char, current_pos, end_pos)
            if last_char_pos != -1 and last_char_pos > current_pos:
                end_pos = last_char_pos + 1
                break
                
        # 如果没找到合适的分割点，就在最大长度处直接分割
        chunks.append(text[current_pos:end_pos])
        current_pos = end_pos
        
    return chunks

def clean_backticks(text):
    """彻底清理字符串中的所有反引号和多余空格"""
    if not text:
        return ""
    # 移除所有反引号和规范化空格
    return text.replace('`', '').strip()

def mask_sensitive_info(text, mask_length=4):
    """
    对敏感信息进行脱敏处理
    
    Args:
        text (str): 需要脱敏的文本
        mask_length (int): 保留的字符数量
        
    Returns:
        str: 脱敏后的文本
    """
    if not text or len(text) <= mask_length:
        return text
        
    # 保留前几个字符，其余用*代替
    return text[:mask_length] + '*' * (len(text) - mask_length)

def send_telegram_notification(message):
    """
    发送 Telegram 通知
    
    Args:
        message (str): 要发送的消息内容
    """
    try:
        # 如果未设置 Telegram 相关环境变量，则跳过通知
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            logger.warning("⚠️ 未设置 Telegram 相关环境变量，跳过通知")
            return
            
        # 构建 API URL
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        
        # 构建请求数据
        data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"  # 支持 HTML 格式
        }
        
        # 发送请求
        response = requests.post(url, data=data)
        
        # 检查响应
        if response.status_code == 200:
            logger.info("✅ Telegram 通知发送成功")
        else:
            logger.error(f"❌ Telegram 通知发送失败: {response.text}")
    except Exception as e:
        logger.error(f"❌ Telegram 通知发送异常: {str(e)}", exc_info=True)

def is_valid_url(url):
    """检查URL是否有效"""
    try:
        response = requests.head(url, allow_redirects=True)
        return response.status_code == 200
    except requests.RequestException:
        return False 