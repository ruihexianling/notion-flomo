# 官网开启一键同步

如果你觉得部署繁琐，可以直接使用NotesToNotion
NotesToNotion能同步图片，并且删除和更新的也可以同步
[NotesToNotion](https://notes2notion.notionify.net)

# 将flomo同步到Notion

本项目通过Github Action每天定时同步flomo到Notion。

预览效果：

[flomo2notion列表页面](https://www.notion.so/image/https%3A%2F%2Fprod-files-secure.s3.us-west-2.amazonaws.com%2Fd01f9e1b-37be-4e62-ba09-3e4835a67760%2F7d8e606e-2bb2-48e0-84fb-e8fe4f70ae5b%2FUntitled.png?table=block&id=df77b666-0f2b-4d96-848e-a0193759c0e3&t=df77b666-0f2b-4d96-848e-a0193759c0e3&width=840.6771240234375&cache=v2)

[flomo2notion详情页面](https://www.notion.so/image/https%3A%2F%2Fprod-files-secure.s3.us-west-2.amazonaws.com%2Fd01f9e1b-37be-4e62-ba09-3e4835a67760%2F8daf2284-aedf-4e04-8f55-9f1fe409e4cc%2FUntitled.png?table=block&id=31fb72fd-0b40-4ae1-82f5-9de52e1aeed1&t=31fb72fd-0b40-4ae1-82f5-9de52e1aeed1&width=2078&cache=v2)

## 使用教程

[flomo2notion教程](https://blog.notionedu.com/article/0d91c395-d74a-4ce4-a219-afdca8e90c92#52ef8ad045d84e0c900ecbe529ce3653)

## 项目结构

```
notion-flomo/
├── config.py               # 配置模块
├── flomo/                  # Flomo相关模块
│   ├── flomo_api.py        # Flomo API封装
│   └── flomo_sign.py       # Flomo签名生成
├── flomo2notion.py         # Flomo同步到Notion的主要逻辑
├── main.py                 # FastAPI服务入口
├── notion2flomo.py         # Notion同步到Flomo的主要逻辑
├── notionify/              # Notion相关模块
│   ├── md2notion.py        # Markdown转Notion
│   ├── notion_helper.py    # Notion API助手
│   ├── notion_utils.py     # Notion工具函数
│   └── notion_cover_list.py# Notion封面列表
├── requirements.txt        # 项目依赖
├── tools.py                # 通用工具函数
└── utils.py                # 实用工具函数
```

## 启动服务

```bash
# 安装依赖
pip install -r requirements.txt

# 启动FastAPI服务
uvicorn main:app --reload
```

## API接口

- `GET /`: 首页
- `GET /sync/flomo2notion`: 触发从Flomo同步到Notion
- `GET /sync/notion2flomo`: 触发从Notion同步到Flomo
