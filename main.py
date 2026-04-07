import ezsheets
import time
import logging
import random
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from datetime import datetime
import config
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

sheet_lock = threading.Lock()

# Список User-Agent для ротации
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

def get_driver():
    """Создает и возвращает настроенный драйвер для Railway"""
    chrome_options = Options()
    
    # Критические настройки для Railway
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--disable-software-rasterizer')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_argument('--disable-web-security')
    chrome_options.add_argument('--disable-features=VizDisplayCompositor')
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--remote-debugging-port=9222')
    
    # Случайный User-Agent
    chrome_options.add_argument(f'--user-agent={random.choice(USER_AGENTS)}')
    
    # Путь к Chrome на Railway
    chrome_options.binary_location = '/usr/bin/chromium'
    
    # Отключаем логирование WebDriver
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
    
    # Настройки для стабильности
    chrome_options.add_argument('--disable-setuid-sandbox')
    chrome_options.add_argument('--disable-logging')
    chrome_options.add_argument('--log-level=3')
    chrome_options.add_argument('--silent')
    
    service = Service(
        '/usr/bin/chromedriver',
        service_args=['--verbose', '--log-path=/tmp/chromedriver.log']
    )
    
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def format_number(value_str):
    """Форматирует число"""
    if not value_str or value_str == '0':
        return '0'
    try:
        clean = value_str.replace('$', '').strip()
        clean = clean.replace(',', '')
        clean = clean.replace('.', ',')
        
        if ',' in clean:
            integer_part = clean.split(',')[0]
            decimal_part = clean.split(',')[1]
        else:
            integer_part = clean
            decimal_part = "00"
        
        if len(integer_part) > 3:
            integer_part = integer_part[::-1]
            integer_part = ' '.join(integer_part[i:i+3] for i in range(0, len(integer_part), 3))
            integer_part = integer_part[::-1]
        
        return f"{integer_part},{decimal_part}"
    except:
        return value_str

def parse_single_link(url):
    """Парсит одну ссылку"""
    driver = None
    try:
        logging.info(f"[{url[-10:]}] Открываю страницу...")
        driver = get_driver()
        
        driver.get(url)
        
        # Принимаем куки
        try:
            cookie_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.ID, "CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll"))
            )
            cookie_button.click()
            logging.info(f"[{url[-10:]}] Куки приняты")
            time.sleep(1)
        except:
            pass
        
        wait = WebDriverWait(driver, 15)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(3)
        
        # Клик на Interval
        try:
            interval_input = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "input[name='date'][placeholder='Interval']"))
            )
            interval_input.click()
            time.sleep(1)
        except:
            pass
        
        # Выбор All Time
        try:
            all_time_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[text()='All Time']"))
            )
            all_time_btn.click()
        except:
            try:
                all_time_btn = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-index='10']"))
                )
                all_time_btn.click()
            except:
                pass
        
        time.sleep(2)
        
        # Поиск таблицы
        all_tables = driver.find_elements(By.TAG_NAME, "table")
        target_table = None
        table_type = None
        
        for tbl in all_tables:
            rows = tbl.find_elements(By.TAG_NAME, "tr")
            for row in rows:
                ths = row.find_elements(By.TAG_NAME, "th")
                th_texts = [th.text.strip() for th in ths]
                if 'Track Link' in th_texts and 'Clicks' in th_texts:
                    target_table = tbl
                    table_type = 'track'
                    break
                elif 'Trial Link' in th_texts and 'Claims' in th_texts:
                    target_table = tbl
                    table_type = 'trial'
                    break
            if target_table:
                break
        
        if not target_table:
            logging.error(f"[{url[-10:]}] Таблица не найдена")
            return None
        
        rows = target_table.find_elements(By.TAG_NAME, "tr")
        
        headers = []
        for row in rows:
            ths = row.find_elements(By.TAG_NAME, "th")
            if ths:
                headers = [th.text.strip() for th in ths]
                break
        
        data_row = None
        for row in rows:
            tds = row.find_elements(By.TAG_NAME, "td")
            if tds and len(tds) > 1:
                data_row = row
                break
        
        if not data_row:
            logging.error(f"[{url[-10:]}] Нет данных")
            return None
        
        cells = data_row.find_elements(By.TAG_NAME, "td")
        cell_values = [cell.text.strip() for cell in cells]
        
        data_dict = {}
        for i, header in enumerate(headers):
            if i < len(cell_values):
                if header not in data_dict:
                    data_dict[header] = cell_values[i]
        
        if table_type == 'track':
            source = data_dict.get('Track Link', 'Unknown')
            clicks_raw = data_dict.get('Clicks', '0')
            fans_raw = data_dict.get('Fans', '0')
            spenders_raw = data_dict.get('Spenders', '0')
            earnings_raw = data_dict.get('Earnings', '0')
        else:
            source = data_dict.get('Trial Link', 'Unknown')
            clicks_raw = data_dict.get('Claims', '0')
            fans_raw = data_dict.get('Fans', '0')
            spenders_raw = data_dict.get('Spenders', '0')
            earnings_raw = data_dict.get('Earnings', '0')
        
        if '\n' in source:
            source = source.split('\n')[0].strip()
        
        if ' / ' in clicks_raw:
            clicks_raw = clicks_raw.split(' / ')[0].strip()
        
        result = {
            'source': source,
            'clicks': format_number(clicks_raw),
            'fans': format_number(fans_raw),
            'spenders': format_number(spenders_raw),
            'income': format_number(earnings_raw),
            'url': url
        }
        logging.info(f"[{url[-10:]}] ✅ Спарсено: {result['source']}")
        return result
        
    except Exception as e:
        logging.error(f"[{url[-10:]}] Ошибка: {e}")
        return None
    finally:
        if driver:
            driver.quit()

def update_google_sheet():
    """Обновляет Google таблицу с 5 потоками и увеличенными задержками"""
    logging.info("=" * 50)
    logging.info("Запуск обновления таблицы (5 потоков)...")
    try:
        ss = ezsheets.Spreadsheet(config.SHEET_ID)
        sheet = ss[0]
        logging.info(f"Подключено к таблице: {ss.title}")
        
        all_rows = sheet.getRows()
        if len(all_rows) < 2:
            logging.warning("Таблица пуста")
            return
        
        links_to_parse = []
        for row_idx, row in enumerate(all_rows[1:], start=2):
            if len(row) <= 18:
                continue
            tracking_link = row[18].strip() if row[18] else ""
            if tracking_link and tracking_link.startswith('https://onlymonster.ai/'):
                links_to_parse.append((row_idx, tracking_link))
        
        if not links_to_parse:
            logging.info("Нет ссылок для парсинга")
            return
        
        logging.info(f"Найдено ссылок: {len(links_to_parse)}. Начинаем параллельный парсинг (5 потоков)...")
        
        results = {}
        
        # Функция-обертка для добавления задержки между запусками потоков
        def process_with_delay(url):
            # Случайная задержка перед началом парсинга (имитация человека)
            delay = random.uniform(2, 5)
            time.sleep(delay)
            return parse_single_link(url)
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_row = {}
            for row_idx, url in links_to_parse:
                future = executor.submit(process_with_delay, url)
                future_to_row[future] = (row_idx, url)
            
            for future in as_completed(future_to_row):
                row_idx, url = future_to_row[future]
                try:
                    result = future.result(timeout=120)
                    if result:
                        results[row_idx] = result
                except Exception as e:
                    logging.error(f"Ошибка при парсинге {url}: {e}")
        
        # Обновляем таблицу
        updated_count = 0
        for row_idx, data in results.items():
            try:
                with sheet_lock:
                    current_row = sheet.getRow(row_idx)
                    
                    while len(current_row) < 20:
                        current_row.append('')
                    
                    current_row[2] = data['clicks']
                    current_row[3] = data['fans']
                    current_row[12] = data['spenders']
                    current_row[15] = data['income']
                    current_row[17] = data['source']
                    
                    current_date = datetime.now().strftime("%d.%m.%Y")
                    old_value = current_row[19] if len(current_row) > 19 and current_row[19] else ""
                    
                    if ' / ' in old_value:
                        first_date = old_value.split(' / ')[0]
                        new_value = f"{first_date} / {current_date}"
                    else:
                        new_value = f"{current_date} / {current_date}"
                    
                    current_row[19] = new_value
                    sheet.updateRow(row_idx, current_row)
                    
                    updated_count += 1
                    logging.info(f"✅ Строка {row_idx} ({data['source']}) обновлена")
                    
            except Exception as e:
                logging.error(f"❌ Ошибка обновления строки {row_idx}: {e}")
        
        logging.info(f"\nОбновление завершено: {updated_count} из {len(links_to_parse)} обновлено")
        
    except Exception as e:
        logging.error(f"Критическая ошибка: {e}")
        raise

def main():
    logging.info("🚀 Парсер OnlyMonster запущен (5 потоков, увеличенные задержки)")
    logging.info(f"Интервал: {config.UPDATE_INTERVAL // 3600} часа")
    while True:
        try:
            update_google_sheet()
        except Exception as e:
            logging.error(f"Ошибка цикла: {e}")
        logging.info("Ожидание 2 часа до следующего цикла...")
        time.sleep(config.UPDATE_INTERVAL)

if __name__ == "__main__":
    main()