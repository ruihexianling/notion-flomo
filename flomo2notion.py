import os
import random
import time
import logging
import sys
import requests

import html2text
from markdownify import markdownify

from flomo.flomo_api import FlomoApi
from notionify import notion_utils
from notionify.md2notion import Md2NotionUploader
from notionify.notion_cover_list import cover
from notionify.notion_helper import NotionHelper
from utils import truncate_string, is_within_n_hours
from tools import (
    split_long_text, clean_backticks, mask_sensitive_info,
    send_telegram_notification, is_valid_url
)
from config import logger

# 使用配置模块中的logger

# 这些函数已移至tools.py模块

class Flomo2Notion:
    def __init__(self):
        self.flomo_api = FlomoApi()
        self.notion_helper = NotionHelper()
        self.uploader = Md2NotionUploader()
        self.success_count = 0
        self.error_count = 0
        self.skip_count = 0

    def insert_memo(self, memo):
        # 检查记录是否已删除
        if memo.get('deleted_at') is not None:
            self.skip_count += 1
            return
        
        # 记录结构日志
        logger.debug(f"记录结构: content 是否为 None: {memo['content'] is None}, 是否有图片: {bool(memo.get('files'))}, 图片数量: {len(memo.get('files', []))}")
        
        # 处理 None 内容
        if memo['content'] is None:
            # 如果有文件，将它们作为内容
            if memo.get('files') and len(memo['files']) > 0:
                content_md = "# 图片备忘录\n\n"
                logger.debug(f"📷 发现 {len(memo['files'])} 个图片文件")
                for i, file in enumerate(memo['files']):
                    if file.get('url'):
                        try:
                            # 使用新函数彻底清理 URL 和名称
                            clean_url = clean_backticks(file['url'])
                            clean_name = clean_backticks(file.get('name', '图片'))
                            
                            logger.debug(f"📷 处理图片 {i+1}/{len(memo['files'])}: {clean_name}")
                            logger.debug(f"🔗 图片URL: {clean_url}")
                            
                            # 检查URL是否有效
                            if is_valid_url(clean_url):
                                content_md += f"![{clean_name}]({clean_url})\n\n"
                                logger.debug(f"✅ 图片 {i+1} Markdown 链接已添加")
                            else:
                                content_md += f"{clean_name}: {clean_url}\n\n"
                                logger.debug(f"⚠️ 图片 {i+1} 链接无效，作为文本添加")
                        except Exception as e:
                            logger.error(f"❌ 图片处理失败: {str(e)}", exc_info=True)
            else:
                content_md = ""  # 如果没有文件则为空内容
                logger.info("📝 没有图片文件，内容为空")
            content_text = content_md
        else:
            logger.info("📝 处理HTML内容转换为Markdown")
            content_md = markdownify(memo['content'])
            content_text = html2text.html2text(memo['content'])
            logger.debug(f"📝 内容长度: {len(content_md)} 字符")
            
            # 不要在Markdown内容中添加图片，而是记录图片信息，稍后单独处理
            image_files = []
            if memo.get('files') and len(memo['files']) > 0:
                logger.debug(f"📷 发现文本+图片混合内容，图片数量: {len(memo['files'])}")
                for i, file in enumerate(memo['files']):
                    if file.get('url'):
                        try:
                            clean_url = clean_backticks(file['url'])
                            clean_name = clean_backticks(file.get('name', '图片'))
                            
                            logger.debug(f"📷 处理混合内容中的图片 {i+1}/{len(memo['files'])}: {clean_name}")
                            logger.debug(f"🔗 混合内容图片URL: {clean_url}")
                            
                            # 检查URL是否有效
                            if is_valid_url(clean_url):
                                content_md += f"![{clean_name}]({clean_url})\n\n"
                                logger.debug(f"✅ 混合内容图片 {i+1} Markdown 链接已添加")
                            else:
                                content_md += f"{clean_name}: {clean_url}\n\n"
                                logger.debug(f"⚠️ 混合内容图片 {i+1} 链接无效，作为文本添加")
                        except Exception as e:
                            logger.error(f"❌ 混合内容图片处理失败: {str(e)}", exc_info=True)
        
        parent = {"database_id": self.notion_helper.page_id, "type": "database_id"}
        properties = {
            "标题": notion_utils.get_title(
                truncate_string(content_text)
            ),
            "标签": notion_utils.get_multi_select(
                memo['tags']
            ),
            "是否置顶": notion_utils.get_select("否" if memo['pin'] == 0 else "是"),
            # 文件的处理方式待定
            # "文件": notion_utils.get_file(""),
            # slug是文章唯一标识
            "slug": notion_utils.get_rich_text(memo['slug']),
            "创建时间": notion_utils.get_date(memo['created_at']),
            "更新时间": notion_utils.get_date(memo['updated_at']),
            "来源": notion_utils.get_select(memo['source']),
            "链接数量": notion_utils.get_number(memo['linked_count']),
            "源链接": notion_utils.get_url(f"https://v.flomoapp.com/mine/?memo_id={memo['slug']}"),
        }
    
        random_cover = random.choice(cover)
        logger.info(f"🖼️ 选择封面: {random_cover}")
    
        try:
            logger.info("📤 开始创建Notion页面")
            page = self.notion_helper.client.pages.create(
                parent=parent,
                icon=notion_utils.get_icon("https://www.notion.so/icons/target_red.svg"),
                cover=notion_utils.get_icon(random_cover),
                properties=properties,
            )
            logger.debug(f"✅ Notion页面创建成功，ID: {page['id']}")
            
            # 检查内容长度，如果超过限制则分割
            if len(content_md) > 2000:
                logger.debug(f"📏 内容超过2000字符，需要分割")
                content_chunks = split_long_text(content_md)
                logger.debug(f"📏 内容已分割为 {len(content_chunks)} 块")
                
                # 逐块上传
                for i, chunk in enumerate(content_chunks):
                    logger.debug(f"📤 上传内容块 {i+1}/{len(content_chunks)} 预览: {chunk[:100]}...")
                    try:
                        self.uploader.uploadSingleFileContent(self.notion_helper.client, chunk, page['id'])
                        logger.debug(f"✅ 内容块 {i+1} 上传成功")
                    except Exception as e:
                        logger.error(f"❌ 内容块 {i+1} 上传失败: {str(e)}", exc_info=True)
            else:
                logger.debug(f"📤 上传完整内容预览: {content_md[:100]}...")
                try:
                    self.uploader.uploadSingleFileContent(self.notion_helper.client, content_md, page['id'])
                    logger.debug("✅ 内容上传成功")
                except Exception as e:
                    logger.error(f"❌ 内容上传失败: {str(e)}", exc_info=True)
            
            # 如果有图片，单独添加图片块
            if 'image_files' in locals() and image_files:
                logger.debug(f"📤 开始添加 {len(image_files)} 个图片块")
                for i, img in enumerate(image_files):
                    try:
                        # 创建图片块
                        image_block = [{
                            "image": {
                                "caption": [],
                                "type": "external",
                                "external": {
                                    "url": img["url"]
                                }
                            }
                        }]
                        self.notion_helper.client.blocks.children.append(block_id=page['id'], children=image_block)
                        logger.debug(f"✅ 图片块 {i+1} 添加成功")
                    except Exception as e:
                        logger.error(f"❌ 图片块 {i+1} 添加失败: {str(e)}", exc_info=True)
            
            self.success_count += 1
            logger.info("✅ 记录插入完成")
        except Exception as e:
            logger.error(f"❌ 记录插入失败: {str(e)}", exc_info=True)
            self.error_count += 1
            raise

    def update_memo(self, memo, page_id):
        # 检查记录是否已删除
        if memo.get('deleted_at') is not None:
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
        
        # 记录结构日志
        logger.debug(f"更新记录结构: content 是否为 None: {memo['content'] is None}, 是否有图片: {bool(memo.get('files'))}, 图片数量: {len(memo.get('files', []))}")
        
        # 处理 None 内容
        if memo['content'] is None:
            # 如果有文件，将它们作为内容
            if memo.get('files') and len(memo['files']) > 0:
                content_md = "# 图片备忘录\n\n"
                logger.debug(f"📷 更新: 发现 {len(memo['files'])} 个图片文件")
                
                # 只添加 Markdown 链接
                for i, file in enumerate(memo['files']):
                    if file.get('url'):
                        try:
                            # 使用新函数彻底清理 URL 和名称
                            clean_url = clean_backticks(file['url'])
                            clean_name = clean_backticks(file.get('name', '图片'))
                            
                            logger.debug(f"📷 更新: 处理图片 {i+1}/{len(memo['files'])}: {clean_name}")
                            logger.debug(f"🔗 更新: 图片URL: {clean_url}")
                            
                            # 检查URL是否有效
                            if is_valid_url(clean_url):
                                content_md += f"![{clean_name}]({clean_url})\n\n"
                                logger.debug(f"✅ 更新: 图片 {i+1} Markdown 链接已添加")
                            else:
                                content_md += f"{clean_name}: {clean_url}\n\n"
                                logger.debug(f"⚠️ 更新: 图片 {i+1} 链接无效，作为文本添加")
                        except Exception as e:
                            logger.error(f"❌ 更新: 图片处理失败: {str(e)}", exc_info=True)
            else:
                content_md = ""  # 如果没有文件则为空内容
                logger.debug("📝 更新: 没有图片文件，内容为空")
            content_text = content_md
        else:
            logger.debug("📝 更新: 处理HTML内容转换为Markdown")
            content_md = markdownify(memo['content'])
            content_text = html2text.html2text(memo['content'])
            logger.debug(f"📝 更新: 内容长度: {len(content_md)} 字符")
            
            # 检查是否同时有图片，如果有，添加到内容后面
            if memo.get('files') and len(memo['files']) > 0:
                logger.debug(f"📷 更新: 发现文本+图片混合内容，图片数量: {len(memo['files'])}")
                content_md += "\n\n# 附带图片\n\n"
                for i, file in enumerate(memo['files']):
                    if file.get('url'):
                        try:
                            clean_url = clean_backticks(file['url'])
                            clean_name = clean_backticks(file.get('name', '图片'))
                            
                            logger.debug(f"📷 更新: 处理混合内容中的图片 {i+1}/{len(memo['files'])}: {clean_name}")
                            logger.debug(f"🔗 更新: 混合内容图片URL: {clean_url}")
                            
                            # 检查URL是否有效
                            if is_valid_url(clean_url):
                                content_md += f"![{clean_name}]({clean_url})\n\n"
                                logger.debug(f"✅ 更新: 混合内容图片 {i+1} Markdown 链接已添加")
                            else:
                                content_md += f"{clean_name}: {clean_url}\n\n"
                                logger.debug(f"⚠️ 更新: 混合内容图片 {i+1} 链接无效，作为文本添加")
                        except Exception as e:
                            logger.error(f"❌ 更新: 混合内容图片处理失败: {str(e)}", exc_info=True)
        
        # 只更新内容
        notion_title = truncate_string(content_text)
        logger.debug(f"📝 更新: 标题: {notion_title}")
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
        
        try:
            logger.debug(f"📤 更新: 开始更新Notion页面属性，ID: {page_id}")
            page = self.notion_helper.client.pages.update(page_id=page_id, properties=properties)
            logger.info("✅ 更新: Notion页面属性更新成功")
        
            # 先清空page的内容，再重新写入
            logger.debug(f"🗑️ 更新: 清空页面内容，ID: {page['id']}")
            self.notion_helper.clear_page_content(page["id"])
            logger.info("✅ 更新: 页面内容清空成功")
        
            # 检查内容长度，如果超过限制则分割
            if len(content_md) > 2000:
                logger.debug(f"📏 更新: 内容超过2000字符，需要分割")
                content_chunks = split_long_text(content_md)
                logger.debug(f"📏 更新: 内容已分割为 {len(content_chunks)} 块")
                
                # 逐块上传
                for i, chunk in enumerate(content_chunks):
                    logger.debug(f"📤 更新: 上传内容块 {i+1}/{len(content_chunks)} 预览: {chunk[:100]}...")
                    try:
                        self.uploader.uploadSingleFileContent(self.notion_helper.client, chunk, page['id'])
                        logger.debug(f"✅ 更新: 内容块 {i+1} 上传成功")
                    except Exception as e:
                        logger.error(f"❌ 更新: 内容块 {i+1} 上传失败: {str(e)}", exc_info=True)
            else:
                logger.debug(f"📤 更新: 上传完整内容预览: {content_md[:100]}...")
                try:
                    self.uploader.uploadSingleFileContent(self.notion_helper.client, content_md, page['id'])
                    logger.info("✅ 更新: 内容上传成功")
                except Exception as e:
                    logger.error(f"❌ 更新: 内容上传失败: {str(e)}", exc_info=True)
                
            self.success_count += 1
            logger.info("✅ 更新: 记录更新完成")
        except Exception as e:
            logger.error(f"❌ 记录更新失败: {str(e)}", exc_info=True)
            self.error_count += 1
            raise

    # 具体步骤：
    def sync_to_notion(self):
        logger.info("🚀 开始同步 Flomo 到 Notion")
        start_time = time.time()
        
        # 发送开始同步的通知
        # 获取北京时间
        beijing_time = time.localtime(time.time() + 8 * 3600) if time.localtime().tm_gmtoff != 8 * 3600 else time.localtime()
        
        # 获取触发者和触发类型信息
        triggered_by = os.getenv("ACTOR", "未知用户")
        trigger_type = os.getenv("EVENT_NAME", "未知触发类型")
        trigger_repo = os.getenv("REPOSITORY", "未知仓库")
        trigger_branch = os.getenv("BRANCH", "未知分支")
        trigger_workflow = os.getenv("GITHUB_WORKFLOW", "未知工作流")
        trigger_run_id = os.getenv("GITHUB_RUN_ID", "未知运行ID")
        trigger_run_number = os.getenv("GITHUB_RUN_NUMBER", "未知运行编号")
        trigger_run_url = f"https://github.com/{trigger_repo}/actions/runs/{trigger_run_id}" if trigger_repo else "未知URL"

        notification_message = """
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
""".format(time.strftime('%Y-%m-%d %H:%M:%S', beijing_time), triggered_by, trigger_type, trigger_repo, trigger_branch, trigger_workflow, trigger_run_id, trigger_run_number, trigger_run_url)
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
                new_memo_list = self.flomo_api.get_memo_list(authorization, latest_updated_at)
                if not new_memo_list:
                    break
                memo_list.extend(new_memo_list)
                latest_updated_at = str(int(time.mktime(time.strptime(new_memo_list[-1]['updated_at'], "%Y-%m-%d %H:%M:%S"))))
                logger.debug(f"📥 已获取 {len(memo_list)} 条记录")
                # 按更新时间打印记录信息
                for memo in sorted(new_memo_list, key=lambda x: x['updated_at']):
                    logger.debug(f"📝 记录: {memo['slug']} - 更新时间: {memo['updated_at']}")
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
        
        for i, memo in enumerate(memo_list):
            progress = f"[{i+1}/{total}]"
            logger.debug(f"{progress} 🔍 处理记录 - {memo['slug']}")
            # 3.1 判断memo的slug是否存在，不存在则写入
            # 3.2 防止大批量更新，只更新更新时间为制定时间的数据（默认为1天）
            if memo['slug'] in slug_map.keys():
                # 是否全量更新，默认否
                full_update = os.getenv("FULL_UPDATE", False)
                # 获取更新间隔（小时）
                interval_hour = int(os.getenv("UPDATE_INTERVAL_HOUR", 2))  # 默认2小时
                
                # 获取在更新时间范围内的记录的最早和最新时间
                if memo_list:
                    # 筛选出在时间范围内的记录
                    updated_memos = [memo for memo in memo_list if is_within_n_hours(memo['updated_at'], interval_hour)]
                    
                    if updated_memos:
                        earliest_memo = min(updated_memos, key=lambda x: x['updated_at'])
                        latest_memo = max(updated_memos, key=lambda x: x['updated_at'])
                        time_range = f"更新时间范围({interval_hour}小时内): {earliest_memo['updated_at']} 至 {latest_memo['updated_at']}"
                    else:
                        time_range = f"没有 {interval_hour} 小时内更新的记录"
                else:
                    time_range = "没有需要更新的记录"
                
                # 检查是否需要更新
                if not full_update and not is_within_n_hours(memo['updated_at'], interval_hour):
                    self.skip_count += 1
                    logger.info(f"{progress} ⏭️ 跳过记录 - 更新时间超过 {interval_hour} 小时")
                    continue

                try:
                    page_id = slug_map[memo['slug']]
                    logger.info(f"{progress} 🔄 更新记录")
                    self.update_memo(memo, page_id)
                    logger.info(f"{progress} ✅ 更新成功")
                except Exception as e:
                    logger.error(f"{progress} ❌ 更新失败: {str(e)}")
            else:
                try:
                    logger.info(f"{progress} 📝 新记录")
                    self.insert_memo(memo)
                    logger.info(f"{progress} ✅ 插入成功")
                except Exception as e:
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
        
        # 发送 Telegram 通知
        # 获取北京时间
        beijing_time = time.localtime(time.time() + 8 * 3600) if time.localtime().tm_gmtoff != 8 * 3600 else time.localtime()
        
        
        notification_message = f"""
<b>Flomo 到 Notion 同步完成</b>

📊 <b>同步统计:</b>
  - 总记录数: {total}
  - 成功处理: {self.success_count}
  - 跳过记录: {self.skip_count}
  - 失败记录: {self.error_count}
  - 耗时: {duration:.2f} 秒
  - {time_range}

✅ 同步完成于 {time.strftime('%Y-%m-%d %H:%M:%S', beijing_time)}
"""
        send_telegram_notification(notification_message)


if __name__ == "__main__":
    # flomo同步到notion入口
    flomo2notion = Flomo2Notion()
    flomo2notion.sync_to_notion()

    # notionify key
    # secret_IHWKSLUTqUh3A8TIKkeXWePu3PucwHiRwDEcqNp5uT3
