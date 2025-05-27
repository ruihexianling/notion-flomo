import os
import random
import time
import sys
import requests
import json
import mimetypes

from flomo.flomo_api import FlomoApi
from notionify import notion_utils
from notionify.md2notion import Md2NotionUploader
from notionify.notion_cover_list import cover
from notionify.notion_helper import NotionHelper
from utils import truncate_string, is_within_n_hours
from tools import (
    split_long_text, clean_backticks, mask_sensitive_info,
    send_telegram_notification, is_valid_url,
    ImageProcessor, ContentProcessor, NotificationProcessor
)
from config import *

logger = get_logger(__name__)

class Flomo2Notion:
    def __init__(self):
        self.flomo_api = FlomoApi()
        self.notion_helper = NotionHelper()
        self.uploader = Md2NotionUploader()
        self.image_processor = ImageProcessor(self.notion_helper)
        self.content_processor = ContentProcessor(self.notion_helper, self.uploader)
        self.success_count = 0
        self.error_count = 0
        self.skip_count = 0

    def process_memo(self, memo, page_id=None):
        # 检查记录是否已删除
        if memo.get('deleted_at') is not None:
            if page_id:
                try:
                    logger.info(f"🗑️ 删除已删除的记录")
                    logger.debug(f"{memo['slug']}")
                    # 将 Notion 页面归档（相当于删除）
                    self.notion_helper.client.pages.update(
                        page_id=page_id,
                        archived=True
                    )
                    self.success_count += 1
                    logger.debug(f"✅ 归档记录成功: {memo['slug']}")
                    return
                except Exception as e:
                    logger.error(f"❌ 归档记录失败: {str(e)}", exc_info=True)
                    self.error_count += 1
                    raise
            else:
                self.skip_count += 1
                logger.info(f"🗑️ 跳过已删除的记录")
                logger.debug(f"{memo['slug']}")
                return
    
        # 处理内容
        content_md, content_text, image_files = self.content_processor.process_content(memo, self.image_processor)
    
        properties = {
            "标题": notion_utils.get_title(
                truncate_string(content_text)
            ),
            "更新时间": notion_utils.get_date(memo['updated_at']),
            "链接数量": notion_utils.get_number(memo['linked_count']),
            "标签": notion_utils.get_multi_select(
                memo['tags']
            ),
            "是否置顶": notion_utils.get_select("否" if memo['pin'] == 0 else "是"),
        }
    
        if not page_id:
            properties.update({
                "slug": notion_utils.get_rich_text(memo['slug']),
                "创建时间": notion_utils.get_date(memo['created_at']),
                "来源": notion_utils.get_select(memo['source']),
                "源链接": notion_utils.get_url(f"https://v.flomoapp.com/mine/?memo_id={memo['slug']}")
            })
    
        try:
            if page_id:
                logger.debug(f"📤 更新: 开始更新Notion页面属性，ID: {page_id}")
                page = self.notion_helper.client.pages.update(page_id=page_id, properties=properties)
                logger.info("✅ 更新: Notion页面属性更新成功")
    
                # 先清空page的内容，再重新写入
                logger.debug(f"🗑️ 更新: 清空页面内容，ID: {page['id']}")
                self.notion_helper.clear_page_content(page["id"])
                logger.info("✅ 更新: 页面内容清空成功")
            else:
                parent = {"database_id": self.notion_helper.page_id, "type": "database_id"}
                random_cover = random.choice(cover)
                logger.info(f"🖼️ 选择封面: {random_cover}")
                logger.info("📤 开始创建Notion页面")
                page = self.notion_helper.client.pages.create(
                    parent=parent,
                    icon=notion_utils.get_icon("https://www.notion.so/icons/target_red.svg"),
                    cover=notion_utils.get_icon(random_cover),
                    properties=properties,
                )
                logger.debug(f"✅ Notion页面创建成功，ID: {page['id']}")
    
            # 上传内容
            self.content_processor.upload_content(content_md, page['id'])
    
            # 上传图片
            self.content_processor.upload_images(image_files, page['id'], self.image_processor)
    
            self.success_count += 1
            logger.info("✅ 记录处理完成")
        except Exception as e:
            logger.error(f"❌ 记录处理失败: {str(e)}", exc_info=True)
            self.error_count += 1
            raise

    def sync_to_notion(self):
        logger.info("🚀 开始同步 Flomo 到 Notion")
        start_time = time.time()
        
        # 发送开始同步的通知
        notification_message = NotificationProcessor.format_start_notification()
        send_telegram_notification(notification_message)
        
        # 1. 调用flomo web端的api从flomo获取数据
        authorization = os.getenv("FLOMO_TOKEN")
        if not authorization:
            logger.error("❌ 未设置 FLOMO_TOKEN 环境变量")
            return
            
        memo_list = []
        latest_updated_at = "0"

        logger.info("📥 开始获取 Flomo 数据...")
        while True:
            try:
                logger.debug(f"请求参数: latest_updated_at(最早更新时间)={latest_updated_at}")
                new_memo_list = self.flomo_api.get_memo_list(authorization, latest_updated_at)
                if not new_memo_list:
                    logger.debug("📥 已获取所有记录")
                    break
                memo_list.extend(new_memo_list)
               
                # 获取本地时间戳
                local_time = time.localtime()
                # 将本地时间转换为时间戳
                local_timestamp = time.mktime(time.strptime(new_memo_list[-1]['updated_at'], "%Y-%m-%d %H:%M:%S"))
                # 如果不是北京时区(UTC+8),需要进行时区转换
                if local_time.tm_gmtoff != 8 * 3600:
                    # 转换为北京时间戳
                    beijing_timestamp = local_timestamp + (8 * 3600 - local_time.tm_gmtoff)
                else:
                    beijing_timestamp = local_timestamp
                latest_updated_at = str(int(beijing_timestamp))
                logger.debug(f"请求成功，最新记录时间: {latest_updated_at}")
                logger.debug(f"📥 已获取 {len(memo_list)} 条记录")
            except Exception as e:
                logger.error(f"❌ 获取 Flomo 数据失败: {str(e)}")
                return
        
        # 不要过滤掉已删除的记录，而是记录它们
        deleted_memo_slugs = set()
        for memo in memo_list:
            if memo.get('deleted_at') is not None:
                deleted_memo_slugs.add(memo['slug'])
        
        logger.info(f"📥 共有 {len(memo_list)} 条记录，其中 {len(deleted_memo_slugs)} 条已删除")
        
        # 2. 调用notion api获取数据库存在的记录，用slug标识唯一，如果存在则更新，不存在则写入
        logger.info("🔍 查询 Notion 数据库...")
        try:
            notion_memo_list = self.notion_helper.query_all(self.notion_helper.page_id)
            slug_map = {}
            for notion_memo in notion_memo_list:
                slug_map[notion_utils.get_rich_text_from_result(notion_memo, "slug")] = notion_memo.get("id")
            logger.debug(f"🔍 Notion 数据库中已有 {len(slug_map)} 条记录")
        except Exception as e:
            logger.error(f"❌ 查询 Notion 数据库失败: {str(e)}")
            return

        # 3. 轮询flomo的列表数据
        total = len(memo_list)
        logger.info(f"🔄 开始处理 {total} 条 Flomo 记录")
        
        # 获取更新间隔（小时）
        interval_hour = int(os.getenv("UPDATE_INTERVAL_HOUR", 2))  # 默认2小时
        
        # 获取在更新时间范围内的记录的最早和最新时间
        updated_memos = [memo for memo in memo_list if is_within_n_hours(memo['updated_at'], interval_hour)]
        if updated_memos:
            earliest_memo = min(updated_memos, key=lambda x: x['updated_at'])
            latest_memo = max(updated_memos, key=lambda x: x['updated_at'])
            time_range = f"更新时间范围({interval_hour}小时内): {earliest_memo['updated_at']} 至 {latest_memo['updated_at']}"
        else:
            time_range = f"没有 {interval_hour} 小时内更新的记录"
        
        for i, memo in enumerate(memo_list):
            progress = f"[{i+1}/{total}]"
            logger.debug(f"{progress} 🔍 处理记录 - {memo['slug']}")
            
            # 是否全量更新，默认否
            full_update = os.getenv("FULL_UPDATE", False)
            
            if memo['slug'] in slug_map.keys():
                # 检查是否需要更新
                if not full_update and not is_within_n_hours(memo['updated_at'], interval_hour):
                    self.skip_count += 1
                    logger.info(f"{progress} ⏭️ 跳过记录 - 更新时间超过 {interval_hour} 小时")
                    continue

                try:
                    page_id = slug_map[memo['slug']]
                    logger.info(f"{progress} 🔄 更新记录")
                    self.process_memo(memo, page_id)
                    logger.info(f"{progress} ✅ 更新成功")
                except Exception as e:
                    self.error_count += 1
                    logger.error(f"{progress} ❌ 更新失败: {str(e)}")
            else:
                try:
                    # 判断memo是否已删除
                    if memo['slug'] in deleted_memo_slugs:
                        logger.info(f"{progress} ⏭️ 跳过记录 - 已删除")
                        self.skip_count += 1
                        continue
                    logger.info(f"{progress} 📝 新记录")
                    self.process_memo(memo)
                    logger.info(f"{progress} ✅ 插入成功")
                except Exception as e:
                    self.error_count += 1
                    logger.error(f"{progress} ❌ 插入失败: {str(e)}")
        
        end_time = time.time()
        duration = end_time - start_time
        
        logger.info("📊 同步统计:")
        logger.info(f"  - 总记录数: {total}")
        logger.info(f"  - 成功处理: {self.success_count}")
        logger.info(f"  - 跳过记录: {self.skip_count}")
        logger.info(f"  - 失败记录: {self.error_count}")
        logger.info(f"  - 耗时: {duration:.2f} 秒")
        logger.info("✅ 同步完成")
        
        # 发送完成通知
        notification_message = NotificationProcessor.format_completion_notification(
            total,
            self.success_count,
            self.skip_count,
            self.error_count,
            duration,
            time_range
        )
        send_telegram_notification(notification_message)


if __name__ == "__main__":
    # flomo同步到notion入口
    flomo2notion = Flomo2Notion()
    flomo2notion.sync_to_notion()

    # notionify key
    # secret_IHWKSLUTqUh3A8TIKkeXWePu3PucwHiRwDEcqNp5uT3
