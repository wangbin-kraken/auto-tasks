use reqwest::header::{
    ACCEPT, ACCEPT_LANGUAGE, COOKIE, HeaderMap, HeaderValue, REFERER, USER_AGENT,
};
use scraper::{Html, Selector};
use std::time::Duration;
use tracing::{Level, error, info, warn};
use tracing_subscriber::fmt::time;
use tracing_subscriber::FmtSubscriber;

// 错误处理别名
type MyResult<T> = Result<T, Box<dyn std::error::Error>>;

struct Config {
    v2ex_cookie: String,
    telegram_bot_token: String,
    telegram_chat_id: String,
}

impl Config {
    fn from_env() -> MyResult<Self> {
        let v2ex_cookie =
            std::env::var("V2EX_COOKIE").map_err(|_| "环境变量 V2EX_COOKIE 未设置")?;
        if v2ex_cookie.trim().is_empty() {
            return Err("环境变量 V2EX_COOKIE 为空，请正确设置".into());
        }
        let telegram_bot_token = std::env::var("TELEGRAM_BOT_TOKEN")
            .map_err(|_| "环境变量 TELEGRAM_BOT_TOKEN 未设置")?;
        if telegram_bot_token.trim().is_empty() {
            return Err("环境变量 TELEGRAM_BOT_TOKEN 为空，请正确设置".into());
        }
        let telegram_chat_id =
            std::env::var("TELEGRAM_CHAT_ID").map_err(|_| "环境变量 TELEGRAM_CHAT_ID 未设置")?;
        if telegram_chat_id.trim().is_empty() {
            return Err("环境变量 TELEGRAM_CHAT_ID 为空，请正确设置".into());
        }
        Ok(Self {
            v2ex_cookie,
            telegram_bot_token,
            telegram_chat_id,
        })
    }
}

struct V2EXSigner {
    config: Config,
    client: reqwest::Client,
}

impl V2EXSigner {
    async fn new() -> MyResult<Self> {
        let config: Config = Config::from_env()?;

        let mut headers = HeaderMap::new();
        headers.insert(USER_AGENT, HeaderValue::from_static("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"));
        headers.insert(ACCEPT, HeaderValue::from_static("text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"));
        headers.insert(ACCEPT_LANGUAGE, HeaderValue::from_static("zh-CN,zh;q=0.9"));

        let cookie_val = HeaderValue::from_str(&config.v2ex_cookie)
            .map_err(|_| "Cookie 包含非法字符，请检查 config.json")?;
        headers.insert(COOKIE, cookie_val);

        let client = reqwest::Client::builder()
            .default_headers(headers)
            .timeout(Duration::from_secs(15))
            .build()?;

        Ok(Self { config, client })
    }

    async fn run(&self) -> MyResult<()> {
        let base_url = "https://www.v2ex.com";
        let daily_url = format!("{}/mission/daily", base_url);
        info!("正在获取签到页面...");
        let resp = self.client.get(&daily_url).send().await?.text().await?;
        let document = Html::parse_document(&resp);
        let mut sign_status = "已完成/无需签到".to_string();

        let sign_button_selector = Selector::parse("input.super.normal.button")?;
        let sign_link = document
            .select(&sign_button_selector)
            .find(|e| e.attr("value").unwrap_or("").contains("领取"))
            .and_then(|e| e.attr("onclick"))
            .and_then(|onclick| onclick.split('\'').nth(1).map(|s| s.to_string()));
        if let Some(link) = sign_link {
            info!("检测到签到链接: {}", link);
            let sign_response = self
                .client
                .get(format!("{}{}", base_url, link))
                .header(REFERER, &daily_url)
                .send()
                .await?;
            if sign_response.status().is_success() {
                info!("签到请求已发送成功");
                sign_status = "🎉 签到成功".to_string();
            } else {
                warn!(status = %sign_response.status(), "签到请求返回异常状态码");
            }
            // 稍微等待确保后端处理完成
            tokio::time::sleep(Duration::from_millis(2000)).await;
        } else {
            info!("未在页面上发现领取按钮，可能今日已领取过");
        }
        info!("正在解析账户信息...");
        let final_resp = self.client.get(&daily_url).send().await?.text().await?;
        let final_doc = Html::parse_document(&final_resp);
        let days =
            self.parse_selector_text(&final_doc, "#Main > div.box > div:nth-child(3) > span");
        let username =
            self.parse_selector_text(&final_doc, "#Top > div > div > div.tools > a:nth-child(2)");

        let balance_resp = self
            .client
            .get("https://www.v2ex.com/balance")
            .send()
            .await?
            .text()
            .await?;
        let balance_doc = Html::parse_document(&balance_resp);
        let total_balance =
            self.parse_selector_text(&balance_doc, "table.data tr:nth-child(2) > td:nth-child(4)");
        let daily_reward = self.parse_selector_text(
            &balance_doc,
            "table.data tr:nth-child(2) > td:nth-child(3) > span > strong",
        );
        let message = format!(r#"📝 V2EX签到信息 📝
👤 用户名：{}
📅 签到状态：{}
💰 每日奖励：{}
🏦 账户总额：{}
🗓️ {}"#,
            username.unwrap_or("未知用户".to_string()),
            sign_status,
            daily_reward.unwrap_or("未知".to_string()),
            total_balance.unwrap_or("未知".to_string()),
            days.unwrap_or("未知".to_string())
        );
        info!("账户信息: \n{}", message);
        self.send_telegram_message(&message).await;
        Ok(())
    }

    fn parse_selector_text(&self, doc: &Html, selector: &str) -> Option<String> {
        let sel = Selector::parse(selector).ok()?;
        let node = doc.select(&sel).next()?;
        let text = node.text().collect::<String>().trim().to_string();
        Some(text)
    }

    async fn send_telegram_message(&self, msg: &str) {
        let url = format!(
            "https://api.telegram.org/bot{}/sendMessage",
            self.config.telegram_bot_token
        );
        let body = serde_json::json!({
            "chat_id": self.config.telegram_chat_id,
            "text": msg,
            "disable_web_page_preview": true
        });
        info!("发送Telegram 消息...");
        let response_result = self.client.post(url).json(&body).send().await;
        match response_result {
            Ok(response) => {
                if !response.status().is_success() {
                    warn!("Telegram 消息发送失败，异常的状态码: {}", response.status());
                } else {
                    info!("Telegram 消息发送成功");
                }
            }
            Err(e) => {
                warn!("Telegram 消息发送失败: {}", e);
            }
        }
    }
}

#[tokio::main]
async fn main() {
    let subscriber = FmtSubscriber::builder()
        .with_max_level(Level::INFO)
        .with_target(false)
        .with_thread_ids(false)
        .with_timer(time::LocalTime::rfc_3339())
        .finish();
    tracing::subscriber::set_global_default(subscriber).expect("日志系统初始化失败");

    info!(version = env!("CARGO_PKG_VERSION"), "V2EX Signer 开始执行");
    match V2EXSigner::new().await {
        Ok(signer) => {
            let result = signer.run().await;

            match result {
                Ok(()) => {
                    info!(version = env!("CARGO_PKG_VERSION"), "V2EX Signer 执行完成");
                }
                Err(e) => {
                    error!("💥 运行出错: {}", e);
                }
            };
        }
        Err(e) => {
            error!("V2EX Signer 初始化失败: {}", e);
            std::process::exit(1);
        }
    }
}
