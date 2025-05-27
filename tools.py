import requests
import json
import os
import mimetypes
import time
import html2text
from config import get_logger, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from markdownify import markdownify

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

class ImageProcessor:
    def __init__(self, notion_helper):
        self.notion_helper = notion_helper
        
    def process_image(self, image_url, image_name="图片"):
        """
        处理单个图片，包括清理URL和名称，上传到Notion
        
        Args:
            image_url (str): 图片URL
            image_name (str): 图片名称
            
        Returns:
            tuple: (file_upload_id, clean_url, clean_name)
        """
        try:
            clean_url = clean_backticks(image_url)
            clean_name = clean_backticks(image_name)
            
            if not is_valid_url(clean_url):
                logger.debug(f"⚠️ 图片链接无效: {clean_url}")
                return None, clean_url, clean_name
                
            file_upload_id = self.upload_image_to_notion(clean_url, clean_name)
            if file_upload_id:
                logger.debug(f"✅ 图片上传成功，ID: {file_upload_id}")
                return file_upload_id, clean_url, clean_name
            else:
                logger.debug(f"⚠️ 图片上传失败，使用原始URL")
                return None, clean_url, clean_name
                
        except Exception as e:
            logger.error(f"❌ 图片处理失败: {str(e)}", exc_info=True)
            return None, clean_url, clean_name
            
    def upload_image_to_notion(self, image_url, image_name="image"):
        """
        使用 Notion 的新文件上传 API 上传图片
        
        Args:
            image_url (str): 图片的 URL
            image_name (str): 图片的名称
            
        Returns:
            str: 上传成功后的文件 ID，失败则返回 None
        """
        try:
            logger.debug(f"🔄 开始从 URL 下载图片: {image_url}")
            # 1. 下载图片
            response = requests.get(image_url, stream=True)
            if response.status_code != 200:
                logger.error(f"❌ 下载图片失败: {response.status_code}")
                return None
                
            # 尝试从 URL 或响应头获取内容类型
            content_type = response.headers.get('Content-Type')
            if not content_type or content_type == 'application/octet-stream':
                # 尝试从 URL 猜测内容类型
                content_type, _ = mimetypes.guess_type(image_url)
                if not content_type:
                    # 默认为 PNG
                    content_type = 'image/png'
            
            # 2. 创建文件上传对象
            logger.debug(f"📤 创建 Notion 文件上传对象")
            payload = {
                "filename": image_name,
                "content_type": content_type
            }
            
            file_create_response = requests.post(
                "https://api.notion.com/v1/file_uploads", 
                json=payload, 
                headers={
                    "Authorization": f"Bearer {os.getenv('NOTION_TOKEN')}",
                    "accept": "application/json",
                    "content-type": "application/json",
                    "Notion-Version": "2022-06-28"
                }
            )
            
            if file_create_response.status_code != 200:
                logger.error(f"❌ 创建文件上传对象失败: {file_create_response.status_code} - {file_create_response.text}")
                return None
                
            file_upload_data = json.loads(file_create_response.text)
            file_upload_id = file_upload_data['id']
            logger.debug(f"✅ 文件上传对象创建成功，ID: {file_upload_id}")
            
            # 3. 上传文件内容
            logger.debug(f"📤 开始上传文件内容")
            files = {
                "file": (image_name, response.content, content_type)
            }
            
            upload_response = requests.post(
                f"https://api.notion.com/v1/file_uploads/{file_upload_id}/send",
                headers={
                    "Authorization": f"Bearer {os.getenv('NOTION_TOKEN')}",
                    "Notion-Version": "2022-06-28"
                },
                files=files
            )
            
            if upload_response.status_code != 200:
                logger.error(f"❌ 上传文件内容失败: {upload_response.status_code} - {upload_response.text}")
                return None
                
            logger.debug(f"✅ 文件内容上传成功")
            return file_upload_id
            
        except Exception as e:
            logger.error(f"❌ 上传图片到 Notion 失败: {str(e)}", exc_info=True)
            return None
            
    def create_image_block(self, file_upload_id, clean_url):
        """
        创建图片块
        
        Args:
            file_upload_id (str): 文件上传ID
            clean_url (str): 清理后的URL
            
        Returns:
            list: 图片块配置
        """
        if file_upload_id:
            return [{
                "image": {
                    "caption": [],
                    "type": "file_upload",
                    "file_upload": {
                        "id": file_upload_id
                    }
                }
            }]
        else:
            return [{
                "image": {
                    "caption": [],
                    "type": "external",
                    "external": {
                        "url": clean_url
                    }
                }
            }]

class ContentProcessor:
    def __init__(self, notion_helper, uploader):
        self.notion_helper = notion_helper
        self.uploader = uploader
        
    def process_content(self, memo, image_processor):
        """
        处理备忘录内容，包括文本和图片
        
        Args:
            memo (dict): 备忘录数据
            image_processor (ImageProcessor): 图片处理器实例
            
        Returns:
            tuple: (content_md, content_text, image_files)
        """
        # 处理 None 内容
        if memo['content'] is None:
            return self._process_empty_content(memo, image_processor)
        else:
            return self._process_text_content(memo, image_processor)
            
    def _process_empty_content(self, memo, image_processor):
        """处理空内容的情况"""
        if memo.get('files') and len(memo['files']) > 0:
            content_md = "# 图片备忘录\n\n"
            image_files = []
            logger.debug(f"📷 发现 {len(memo['files'])} 个图片文件")
            
            for i, file in enumerate(memo['files']):
                if file.get('url'):
                    file_upload_id, clean_url, clean_name = image_processor.process_image(
                        file['url'], 
                        file.get('name', '图片')
                    )
                    if file_upload_id:
                        image_files.append({
                            "url": clean_url,
                            "name": clean_name,
                            "file_upload_id": file_upload_id
                        })
                    else:
                        content_md += f"![{clean_name}]({clean_url})\n\n"
                        
            return content_md, content_md, image_files
        else:
            return "", "", []
            
    def _process_text_content(self, memo, image_processor):
        """处理文本内容的情况"""
        content_md = markdownify(memo['content'])
        content_text = html2text.html2text(memo['content'])
        image_files = []
        
        if memo.get('files') and len(memo['files']) > 0:
            content_md += "\n\n# 附带图片\n\n"
            logger.debug(f"📷 发现文本+图片混合内容，图片数量: {len(memo['files'])}")
            
            for i, file in enumerate(memo['files']):
                if file.get('url'):
                    file_upload_id, clean_url, clean_name = image_processor.process_image(
                        file['url'], 
                        file.get('name', '图片')
                    )
                    if file_upload_id:
                        image_files.append({
                            "url": clean_url,
                            "name": clean_name,
                            "file_upload_id": file_upload_id
                        })
                    else:
                        content_md += f"![{clean_name}]({clean_url})\n\n"
                        
        return content_md, content_text, image_files
        
    def upload_content(self, content_md, page_id):
        """
        上传内容到Notion页面
        
        Args:
            content_md (str): Markdown格式的内容
            page_id (str): Notion页面ID
        """
        if len(content_md) > 2000:
            logger.debug(f"📏 内容超过2000字符，需要分割")
            content_chunks = split_long_text(content_md)
            logger.debug(f"📏 内容已分割为 {len(content_chunks)} 块")
            
            for i, chunk in enumerate(content_chunks):
                logger.debug(f"📤 上传内容块 {i+1}/{len(content_chunks)} 预览: {chunk[:10]}...")
                try:
                    self.uploader.uploadSingleFileContent(self.notion_helper.client, chunk, page_id)
                    logger.debug(f"✅ 内容块 {i+1} 上传成功")
                except Exception as e:
                    logger.error(f"❌ 内容块 {i+1} 上传失败: {str(e)}", exc_info=True)
        else:
            logger.debug(f"📤 上传完整内容预览: {content_md[:10]}...")
            try:
                self.uploader.uploadSingleFileContent(self.notion_helper.client, content_md, page_id)
                logger.debug("✅ 内容上传成功")
            except Exception as e:
                logger.error(f"❌ 内容上传失败: {str(e)}", exc_info=True)
                
    def upload_images(self, image_files, page_id, image_processor):
        """
        上传图片到Notion页面
        
        Args:
            image_files (list): 图片文件列表
            page_id (str): Notion页面ID
            image_processor (ImageProcessor): 图片处理器实例
        """
        if not image_files:
            return
            
        logger.debug(f"📤 开始添加 {len(image_files)} 个图片块")
        for i, img in enumerate(image_files):
            try:
                image_block = image_processor.create_image_block(
                    img.get('file_upload_id'),
                    img['url']
                )
                self.notion_helper.client.blocks.children.append(
                    block_id=page_id, 
                    children=image_block
                )
                logger.debug(f"✅ 图片块 {i+1} 添加成功")
            except Exception as e:
                logger.error(f"❌ 图片块 {i+1} 添加失败: {str(e)}", exc_info=True)

class NotificationProcessor:
    @staticmethod
    def get_beijing_time():
        """获取北京时间"""
        return time.localtime(time.time() + 8 * 3600) if time.localtime().tm_gmtoff != 8 * 3600 else time.localtime()
        
    @staticmethod
    def format_start_notification():
        """格式化开始同步的通知消息"""
        beijing_time = NotificationProcessor.get_beijing_time()
        
        # 获取触发者和触发类型信息
        triggered_by = os.getenv("ACTOR", "未知用户")
        trigger_type = os.getenv("EVENT_NAME", "未知触发类型")
        trigger_repo = os.getenv("REPOSITORY", "未知仓库")
        trigger_branch = os.getenv("BRANCH", "未知分支")
        trigger_workflow = os.getenv("GITHUB_WORKFLOW", "未知工作流")
        trigger_run_id = os.getenv("GITHUB_RUN_ID", "未知运行ID")
        trigger_run_number = os.getenv("GITHUB_RUN_NUMBER", "未知运行编号")
        trigger_run_url = f"https://github.com/{trigger_repo}/actions/runs/{trigger_run_id}" if trigger_repo else "未知URL"

        return """
<b>开始同步 Flomo 到 Notion</b>

⏰ 开始时间: {}
👤 触发者: {}
🔔 触发类型: {}
📂 仓库: {}
🌳 分支: {}
📊 工作流: {}
🔢 运行ID: {}
🔢 运行编号: {}
🔗 运行URL: {}
""".format(
            time.strftime('%Y-%m-%d %H:%M:%S', beijing_time),
            triggered_by,
            trigger_type,
            trigger_repo,
            trigger_branch,
            trigger_workflow,
            trigger_run_id,
            trigger_run_number,
            trigger_run_url
        )
        
    @staticmethod
    def format_completion_notification(total, success_count, skip_count, error_count, duration, time_range):
        """格式化完成同步的通知消息"""
        beijing_time = NotificationProcessor.get_beijing_time()
        
        return f"""
<b>Flomo 到 Notion 同步完成</b>

📊 <b>同步统计:</b>
  - 总记录数: {total}
  - 成功处理: {success_count}
  - 跳过记录: {skip_count}
  - 失败记录: {error_count}
  - 耗时: {duration:.2f} 秒
  - {time_range}

✅ 同步完成于 {time.strftime('%Y-%m-%d %H:%M:%S', beijing_time)}
"""