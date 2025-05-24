from fastapi import FastAPI, BackgroundTasks
from flomo2notion import Flomo2Notion
from notion2flomo import Notion2Flomo
import logging
import os
from config import get_logger
logger = get_logger(__name__)


app = FastAPI()


@app.get("/")
async def root():
    return {"message": "Flomo to Notion Sync Tool"}


@app.get("/hello/{name}")
async def say_hello(name: str):
    return {"message": f"Hello {name}"}


@app.get("/sync/flomo2notion")
async def sync_flomo2notion(background_tasks: BackgroundTasks):
    """将flomo笔记同步到Notion"""
    background_tasks.add_task(Flomo2Notion().sync_to_notion)
    return {"message": "同步任务已启动"}


@app.get("/sync/notion2flomo")
async def sync_notion2flomo(background_tasks: BackgroundTasks):
    """将Notion笔记同步到flomo"""
    background_tasks.add_task(Notion2Flomo().sync_to_flomo)
    return {"message": "同步任务已启动"}
