import requests
from bs4 import BeautifulSoup
import json
import time

class SimpleChannelParser:
    def __init__(self, channels_file):
        self.channels_file = channels_file
        self.channels = self.load_channels()

    def load_channels(self):
        with open(self.channels_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def get_channel_posts(self, channel):
        web_url = f'https://t.me/s/{channel["username"]}'
        try:
            response = requests.get(web_url, timeout=10)
            if response.status_code != 200:
                print(f"[!] Не удалось получить данные с {web_url} (код {response.status_code})")
                return []

            soup = BeautifulSoup(response.text, 'html.parser')
            messages = soup.find_all('div', class_='tgme_widget_message')
            
            # Если сообщений нет — вероятно, это не канал
            if not messages:
                print(f"[!] {channel['username']} не является каналом или недоступен.")
                return []

            posts = []
            for msg in messages:
                text_div = msg.find('div', class_='tgme_widget_message_text')
                if text_div:
                    posts.append(text_div.get_text(strip=True))
            return posts

        except Exception as e:
            print(f"[!] Ошибка при парсинге {web_url}: {e}")
            return []

    def run(self):
        for channel in self.channels:
            print(f"\n📡 Парсим: {channel['username']}")
            posts = self.get_channel_posts(channel)
            print(f"✅ Найдено постов: {len(posts)}")
            for i, post in enumerate(posts[:3], 1):  # Показываем первые 3 поста
                print(f"{i}. {post[:100]}...")  # Обрезаем до 100 символов
            time.sleep(1)  # Пауза между запросами

if __name__ == '__main__':
    parser = SimpleChannelParser('channels.json')
    parser.run()
