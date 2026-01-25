import logging
import re
import time

from typing import Optional
import requests
from bs4 import BeautifulSoup
from pydantic_settings import BaseSettings

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

class Config(BaseSettings):
    v2ex_cookie: str
    telegram_bot_token: str
    telegram_chat_id: int

class V2EXSigner:
    BASE_URL = "https://www.v2ex.com"

    def __init__(self):
        self.config = Config()

        self.client = requests.Session()
        self.client.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Cookie": self.config.v2ex_cookie,
            }
        )
        self.client.timeout = 15

    def _parse_selector_text(self, soup: BeautifulSoup, selector: str) -> Optional[str]:
        element = soup.select_one(selector)
        return element.get_text(strip=True) if element else None

    def _send_telegram_message(self, message: str):
        url = (
            f"https://api.telegram.org/bot{self.config.telegram_bot_token}/sendMessage"
        )
        payload = {
            "chat_id": self.config.telegram_chat_id,
            "text": message,
            "disable_web_page_preview": True,
        }
        logging.info("发送 Telegram 消息...")
        try:
            response = self.client.post(url, json=payload)
            if response.ok:
                logging.info("Telegram 消息发送成功")
            else:
                logging.warning(
                    f"Telegram 消息发送失败, 异常的响应: {response}"
                )
        except requests.RequestException as e:
            logging.error(f"Telegram 消息发送失败: {e}")

    def run(self):
        daily_url = f"{self.BASE_URL}/mission/daily"
        sign_status = "已完成/无需签到"

        try:
            logging.info("正在获取签到页面...")
            response = self.client.get(daily_url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

            sign_button = soup.select_one('input.super.normal.button[value*="领取"]')
            if sign_button and "onclick" in sign_button.attrs:
                onclick_attr = sign_button["onclick"]
                match = re.search(r"location\.href = '(.+?)'", onclick_attr)
                if match:
                    sign_link = match.group(1)
                    logging.info(f"检测到签到链接: {sign_link}")

                    sign_url = f"{self.BASE_URL}{sign_link}"
                    sign_response = self.client.get(
                        sign_url, headers={"Referer": daily_url}
                    )

                    if sign_response.ok:
                        logging.info("签到请求已发送成功")
                        sign_status = "🎉 签到成功"
                    else:
                        logging.warning(
                            f"签到请求返回异常状态码: {sign_response.status_code}"
                        )

                    time.sleep(2)  # 稍微等待确保后端处理完成

            else:
                logging.info("未在页面上发现领取按钮，可能今日已领取过")

            logging.info("正在解析账户信息...")
            final_response = self.client.get(daily_url)
            final_soup = BeautifulSoup(final_response.text, "html.parser")

            days = self._parse_selector_text(
                final_soup, "#Main > div.box > div:nth-child(3) > span"
            )
            username = self._parse_selector_text(
                final_soup, "#Top > div > div > div.tools > a:nth-child(2)"
            )

            balance_response = self.client.get(f"{self.BASE_URL}/balance")
            balance_soup = BeautifulSoup(balance_response.text, "html.parser")

            total_balance = self._parse_selector_text(
                balance_soup, "table.data tr:nth-child(2) > td:nth-child(4)"
            )
            daily_reward = self._parse_selector_text(
                balance_soup,
                "table.data tr:nth-child(2) > td:nth-child(3) > span > strong",
            )

            # 5. Format and send the notification
            message = (
                f"📝 V2EX签到信息 📝\n"
                f"👤 用户名：{username}\n"
                f"📅 签到状态：{sign_status}\n"
                f"💰 每日奖励：{daily_reward}\n"
                f"🏦 账户总额：{total_balance}\n"
                f"🗓️ {days}"
            )
            logging.info(f"账户信息:\n{message}")
            self._send_telegram_message(message)

        except requests.RequestException as e:
            logging.error(f"An HTTP error occurred: {e}")
            self._send_telegram_message(f"💥 V2EX签到脚本运行出错: {e}")
        except Exception as e:
            logging.error(f"An unexpected error occurred: {e}", exc_info=True)
            self._send_telegram_message(f"💥 V2EX签到脚本发生未知错误: {e}")


def main():
    logging.info("V2EX Signer 开始执行.")
    try:
        signer = V2EXSigner()
        signer.run()
        logging.info("V2EX Signer 执行完成.")
    except ValueError as e:
        logging.error(f"初始化失败: {e}")
    except Exception as e:
        logging.error(f"💥 运行出错: : {e}", exc_info=True)


if __name__ == "__main__":
    main()
