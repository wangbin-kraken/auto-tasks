import asyncio
import logging
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings
from telethon import TelegramClient, errors
from telethon.sessions import StringSession

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("telegram-sign")


class MessageType(str, Enum):
    TEXT = "text"
    MARKDOWN = "markdown"
    HTML = "html"
    FILE = "file"


class SignTask(BaseModel):
    chat_id: int
    type: MessageType = MessageType.TEXT
    delay: int = Field(default=0, ge=0)
    text: Optional[str] = None
    file: Optional[str] = None
    caption: Optional[str] = None

    @model_validator(mode="after")
    def check_payload(self):
        if self.type == MessageType.FILE:
            if not self.file:
                raise ValueError("file 类型消息必须提供 file 字段")
        else:
            if not self.text:
                raise ValueError(f"{self.type} 类型消息必须提供 text 字段")

        return self


class Config(BaseSettings):
    telegram_session: str
    telegram_api_id: int
    telegram_api_hash: str
    telegram_sign_tasks: list[SignTask]


def log_task_result(name: str, chat_id: int, sent: str, replies: list[str]):
    separator = "─" * 40

    # 组合多条回复
    if not replies:
        reply_content = "   (未收到回复)"
    else:
        # 每条回复前加一个回车和缩进，增强可读性
        reply_content = "\n".join([f"   └─ 内容: {r.strip()}" for r in replies])

    log_msg = (
        f"\n{'=' * 50}\n"
        f"👤 目标: {name} (ID: {chat_id})\n"
        f"{separator}\n"
        f"📤 发送: {sent}\n"
        f"📥 回复:\n{reply_content}\n"
        f"{'=' * 50}"
    )
    logger.info(log_msg)


async def execute_task(client: TelegramClient, task: SignTask):
    chat_id = task.chat_id
    if not chat_id:
        logger.warning("⚠️ 跳过无 chat_id 的任务")
        return

    message_type = task.type
    delay = task.delay

    if delay > 0:
        logger.info(f"⏳ 延迟 {delay}s 后执行任务 [{chat_id}]")
        await asyncio.sleep(delay)

    try:
        entity = await client.get_entity(chat_id)
        name = getattr(entity, "title", getattr(entity, "first_name", "Unknown"))
    except Exception as err:
        logger.error(f"{err}")
        name = f"ID:{chat_id}"

    replies: list[str] = []

    try:
        async with client.conversation(chat_id, timeout=10) as conv:
            if message_type == MessageType.FILE:
                sent_message = await conv.send_file(
                    task.file,
                    caption=task.caption,
                )
                sent_content = f"{task.caption}: {task.file}" or f"[文件: {task.file}]"
            else:
                parse_mode = task.type.value if task.type != MessageType.TEXT else None
                sent_message = await conv.send_message(task.text, parse_mode=parse_mode)
                sent_content = task.text

            logger.info(f"📡 已发送至 [{name}]，等待回复...")

            try:
                while True:
                    response = await conv.get_response(timeout=5, message=sent_message)
                    replies.append(response.text or "[非文本消息]")
            except asyncio.TimeoutError:
                # 如果几秒内没新消息了，说明对方发完了
                pass
    except asyncio.TimeoutError:
        pass
    except errors.FloodWaitError as err:
        logger.error(f"🚫 FloodWait：需等待 {err.seconds}s")
    except Exception as err:
        logger.exception(f"❌ 任务执行失败 [{chat_id}]: {err}")

    log_task_result(name, chat_id, sent_content, replies)


async def main():
    try:
        config = Config()
    except Exception as err:
        logger.critical(f"❌ 配置加载失败: {err}")
        return

    client = TelegramClient(
        StringSession(config.telegram_session),
        config.telegram_api_id,
        config.telegram_api_hash,
    )

    async with client:
        me = await client.get_me()
        logger.info(f"✅ 登录成功: {me.first_name} (ID: {me.id})")

        logger.info("🔄 同步对话缓存...")
        await client.get_dialogs()

        for idx, task in enumerate(config.telegram_sign_tasks, 1):
            logger.info(f"🚀 执行任务 {idx}/{len(config.telegram_sign_tasks)}")
            await execute_task(client, task)

    logger.info("🏁 所有任务执行完毕")


# ================= 6. 入口 =================
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⛔ 用户中断")
    except Exception as e:
        logger.critical(f"💥 程序崩溃: {e}")
