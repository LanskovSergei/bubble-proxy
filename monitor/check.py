#!/usr/bin/env python3
"""
Мониторинг доступности Bubble Proxy с Telegram алертами
"""
import os
import sys
import time
import logging
import requests
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/logs/monitor.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('ProxyMonitor')


class TelegramNotifier:
    """Отправка уведомлений в Telegram"""
    
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        
    def send_message(self, text: str, parse_mode: str = 'HTML') -> bool:
        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                'chat_id': self.chat_id,
                'text': text,
                'parse_mode': parse_mode,
                'disable_web_page_preview': True
            }
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            logger.info("Telegram notification sent")
            return True
        except Exception as e:
            logger.error(f"Failed to send Telegram: {e}")
            return False
    
    def send_alert(self, domain: str, status_code: int, 
                   error: str, response_time: float = None):
        """Алерт о недоступности"""
        message = f"🔴 <b>ПРОКСИ НЕДОСТУПЕН</b>\n\n"
        message += f"<b>Домен:</b> {domain}\n"
        message += f"<b>Время:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        
        if status_code:
            message += f"<b>Статус:</b> {status_code}\n"
        if response_time:
            message += f"<b>Время ответа:</b> {response_time:.2f}s\n"
        if error:
            message += f"<b>Ошибка:</b> {error}\n"
        
        message += f"\n⚠️ <i>Проверь сервер и DNS настройки</i>"
        
        self.send_message(message)
    
    def send_recovery(self, domain: str, downtime_duration: int):
        """Уведомление о восстановлении"""
        message = f"✅ <b>ПРОКСИ ВОССТАНОВЛЕН</b>\n\n"
        message += f"<b>Домен:</b> {domain}\n"
        message += f"<b>Время:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        message += f"<b>Даунтайм:</b> {downtime_duration} секунд\n"
        message += f"\n🎉 <i>Всё работает нормально</i>"
        
        self.send_message(message)


class ProxyMonitor:
    """Мониторинг прокси"""
    
    def __init__(self, domain: str, telegram_notifier = None):
        self.domain = domain
        self.url = f"https://{domain}/health"
        self.notifier = telegram_notifier
        
        self.is_down = False
        self.downtime_start = None
        self.consecutive_failures = 0
        self.consecutive_successes = 0
        
        self.timeout = 15
        self.max_response_time = 5
        self.failure_threshold = 2
        self.recovery_threshold = 2
        
    def _get_headers(self):
        """Заголовки для эмуляции РФ браузера"""
        return {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                         '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0'
        }
    
    def check_health(self):
        """Проверка доступности"""
        result = {
            'success': False,
            'status_code': None,
            'response_time': None,
            'error': None,
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            start_time = time.time()
            
            response = requests.get(
                self.url,
                headers=self._get_headers(),
                timeout=self.timeout,
                verify=True,
                allow_redirects=True
            )
            
            response_time = time.time() - start_time
            result['response_time'] = response_time
            result['status_code'] = response.status_code
            
            if response.status_code == 200:
                result['success'] = True
                
                if response_time > self.max_response_time:
                    logger.warning(f"Slow response: {response_time:.2f}s")
            else:
                result['error'] = f"Bad status code: {response.status_code}"
                
        except requests.exceptions.SSLError as e:
            result['error'] = f"SSL Error: {str(e)}"
            logger.error(f"SSL error: {e}")
            
        except requests.exceptions.Timeout:
            result['error'] = f"Timeout after {self.timeout}s"
            logger.error(f"Timeout checking {self.url}")
            
        except requests.exceptions.ConnectionError as e:
            result['error'] = f"Connection error: {str(e)}"
            logger.error(f"Connection error: {e}")
            
        except Exception as e:
            result['error'] = f"Unexpected error: {str(e)}"
            logger.error(f"Unexpected error: {e}")
        
        return result
    
    def handle_check_result(self, result):
        """Обработка результата проверки"""
        
        if result['success']:
            self.consecutive_failures = 0
            self.consecutive_successes += 1
            
            if self.is_down and self.consecutive_successes >= self.recovery_threshold:
                downtime_duration = int(time.time() - self.downtime_start)
                logger.info(f"✅ Service recovered after {downtime_duration}s")
                
                if self.notifier:
                    self.notifier.send_recovery(self.domain, downtime_duration)
                
                self.is_down = False
                self.downtime_start = None
                self.consecutive_successes = 0
            
            if result['response_time']:
                logger.info(f"✓ Check passed: {result['status_code']} in {result['response_time']:.2f}s")
        else:
            self.consecutive_successes = 0
            self.consecutive_failures += 1
            
            logger.warning(f"✗ Check failed ({self.consecutive_failures}/{self.failure_threshold}): {result['error']}")
            
            if not self.is_down and self.consecutive_failures >= self.failure_threshold:
                self.is_down = True
                self.downtime_start = time.time()
                
                logger.error(f"🔴 Service DOWN: {result['error']}")
                
                if self.notifier:
                    self.notifier.send_alert(
                        domain=self.domain,
                        status_code=result['status_code'],
                        error=result['error'],
                        response_time=result['response_time']
                    )
    
    def run_forever(self, interval: int = 300):
        """Запуск в бесконечном цикле"""
        logger.info(f"Starting monitor for {self.domain}")
        logger.info(f"Check interval: {interval}s")
        logger.info(f"Failure threshold: {self.failure_threshold}")
        
        while True:
            try:
                result = self.check_health()
                self.handle_check_result(result)
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
            
            time.sleep(interval)


def main():
    domain = os.getenv('DOMAIN')
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    interval = int(os.getenv('MONITOR_INTERVAL', '300'))
    
    if not domain:
        logger.error("DOMAIN environment variable is required")
        sys.exit(1)
    
    notifier = None
    if bot_token and chat_id:
        notifier = TelegramNotifier(bot_token, chat_id)
        logger.info("Telegram notifications enabled")
        
        notifier.send_message(
            f"🚀 <b>Мониторинг запущен</b>\n\n"
            f"<b>Домен:</b> {domain}\n"
            f"<b>Интервал:</b> {interval}s"
        )
    else:
        logger.warning("Telegram notifications disabled")
    
    monitor = ProxyMonitor(domain=domain, telegram_notifier=notifier)
    
    try:
        monitor.run_forever(interval=interval)
    except KeyboardInterrupt:
        logger.info("Monitor stopped by user")
        if notifier:
            notifier.send_message(f"⏸️ <b>Мониторинг остановлен</b>\n\nДомен: {domain}")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        if notifier:
            notifier.send_message(f"💥 <b>КРИТИЧЕСКАЯ ОШИБКА</b>\n\nДомен: {domain}\nОшибка: {str(e)}")
        sys.exit(1)


if __name__ == '__main__':
    main()
