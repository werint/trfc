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
from datetime import datetime
import config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_driver():
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--remote-debugging-port=9222')
    chrome_options.binary_location = '/usr/bin/chromium'
    chrome_options.add_argument('--log-level=3')
    
    service = Service('/usr/bin/chromedriver')
    return webdriver.Chrome(service=service, options=chrome_options)

def click_all_time(driver):
    """Кликает на All Time в текущей странице"""
    try:
        interval_input = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "input[name='date'][placeholder='Interval']"))
        )
        interval_input.click()
        time.sleep(0.5)
        
        all_time_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//button[text()='All Time']"))
        )
        all_time_btn.click()
        time.sleep(1)
        return True
    except:
        return False

def parse_current_page(driver):
    """Парсит данные с текущей открытой страницы"""
    try:
        # Ждем загрузки таблицы
        wait = WebDriverWait(driver, 10)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "table")))
        
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
        
        return {
            'source': source,
            'clicks': clicks_raw,
            'fans': fans_raw,
            'spenders': spenders_raw,
            'income': earnings_raw
        }
        
    except Exception as e:
        logging.error(f"Ошибка парсинга: {e}")
        return None

def format_number(value_str):
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

def update_google_sheet():
    logging.info("=" * 50)
    logging.info("Запуск обновления таблицы (один браузер)...")
    
    driver = None
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
        
        logging.info(f"Найдено ссылок: {len(links_to_parse)}. Запускаю один браузер...")
        
        # ЗАПУСКАЕМ ОДИН БРАУЗЕР
        driver = get_driver()
        
        updated_count = 0
        for row_idx, url in links_to_parse:
            try:
                logging.info(f"[{url[-10:]}] Открываю страницу...")
                driver.get(url)
                time.sleep(2)
                
                # Выбираем All Time
                click_all_time(driver)
                
                # Парсим данные
                data = parse_current_page(driver)
                
                if data:
                    # Форматируем числа
                    formatted_data = {
                        'source': data['source'],
                        'clicks': format_number(data['clicks']),
                        'fans': format_number(data['fans']),
                        'spenders': format_number(data['spenders']),
                        'income': format_number(data['income'])
                    }
                    
                    # Обновляем таблицу
                    current_row = sheet.getRow(row_idx)
                    while len(current_row) < 20:
                        current_row.append('')
                    
                    current_row[2] = formatted_data['clicks']
                    current_row[3] = formatted_data['fans']
                    current_row[12] = formatted_data['spenders']
                    current_row[15] = formatted_data['income']
                    current_row[17] = formatted_data['source']
                    
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
                else:
                    logging.error(f"[{url[-10:]}] Не удалось спарсить данные")
                
                # Небольшая пауза между ссылками
                time.sleep(1)
                
            except Exception as e:
                logging.error(f"[{url[-10:]}] Ошибка: {e}")
                # Если браузер упал, пересоздаем его
                if driver:
                    try:
                        driver.quit()
                    except:
                        pass
                driver = get_driver()
        
        logging.info(f"\nОбновление завершено: {updated_count} из {len(links_to_parse)} обновлено")
        
    except Exception as e:
        logging.error(f"Критическая ошибка: {e}")
        raise
    finally:
        if driver:
            driver.quit()

def main():
    logging.info("🚀 Парсер OnlyMonster запущен (один браузер, быстро)")
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