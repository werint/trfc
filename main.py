import ezsheets
import time
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime
import config

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def get_driver():
    """Создает и возвращает настроенный драйвер Selenium"""
    chrome_options = Options()
    for opt in config.CHROME_OPTIONS:
        chrome_options.add_argument(opt)
    
    driver = webdriver.Chrome(options=chrome_options)
    return driver

def parse_single_link(url):
    """
    Парсит одну ссылку и возвращает словарь с данными
    
    Ожидаемые HTML элементы:
    - Fans: <p class="text-sm">148</p>
    - Clicks: <p class="text-sm">2785</p> (в другом месте)
    - Spenders: <p class="text-sm">2</p>
    - Income: <p class="text-sm text-nowrap text-success">$ 31.04</p>
    - Source: название трекинг-ссылки (из таблицы на странице)
    """
    driver = get_driver()
    
    try:
        logging.info(f"Открываю страницу: {url}")
        driver.get(url)
        
        # Ждем загрузки страницы (ждем появления любого элемента с данными)
        wait = WebDriverWait(driver, 15)
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "text-sm")))
        
        # Небольшая пауза для полной загрузки
        time.sleep(2)
        
        # Нажимаем кнопку "All Time"
        try:
            all_time_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'All Time')]")
            all_time_btn.click()
            logging.info("Нажата кнопка 'All Time'")
            time.sleep(2)  # Ждем обновления данных
        except Exception as e:
            logging.warning(f"Кнопка 'All Time' не найдена или уже активна: {e}")
        
        # Парсим данные
        
        # 1. Total Fans
        fans_elements = driver.find_elements(By.CSS_SELECTOR, "p.text-sm")
        fans = None
        for el in fans_elements:
            text = el.text.strip()
            if text.isdigit() and len(text) <= 4:  # Ищем число до 9999 (фэны)
                # Проверяем, что это не Spenders (будем искать отдельно)
                fans = text
                break
        
        # Альтернативный поиск Total Fans по контексту
        if not fans:
            try:
                fans_label = driver.find_element(By.XPATH, "//*[contains(text(), 'Total Fans')]/following-sibling::p")
                fans = fans_label.text.strip()
            except:
                pass
        
        # 2. Total Earnings (Income)
        try:
            income_elem = driver.find_element(By.CSS_SELECTOR, "p.text-sm.text-nowrap.text-success")
            income_text = income_elem.text.strip().replace('$', '').replace(' ', '').replace('.', ',')
            income = income_text
        except:
            income = "0"
        
        # 3. Spenders
        spenders = None
        try:
            # Ищем по контексту (обычно Spenders рядом с цифрой)
            spenders_label = driver.find_element(By.XPATH, "//*[contains(text(), 'Spenders')]/following-sibling::p")
            spenders = spenders_label.text.strip()
        except:
            # Если не нашли, пробуем найти все числа и взять подходящее
            for el in fans_elements:
                if el.text.strip().isdigit() and el.text != fans:
                    spenders = el.text.strip()
                    break
        
        # 4. Clicks
        clicks = None
        try:
            # Ищем в строке "XXX / ∞"
            click_elements = driver.find_elements(By.XPATH, "//*[contains(text(), '/ ∞')]")
            if click_elements:
                click_text = click_elements[0].text.strip()
                clicks = click_text.split('/')[0].strip()
        except:
            pass
        
        # 5. Source (название трекинг-ссылки)
        source = "Unknown"
        try:
            # Ищем название в таблице Trial Links
            source_elem = driver.find_element(By.XPATH, "//table//tr//td[1]")
            source = source_elem.text.strip()
        except:
            pass
        
        # Если какие-то данные не найдены, ставим значение по умолчанию
        result = {
            'source': source if source else "Unknown",
            'clicks': clicks if clicks else "0",
            'fans': fans if fans else "0",
            'spenders': spenders if spenders else "0",
            'income': income if income else "0"
        }
        
        logging.info(f"Успешно спарсено: {result}")
        return result
        
    except Exception as e:
        logging.error(f"Ошибка при парсинге {url}: {e}")
        raise
        
    finally:
        driver.quit()

def update_google_sheet():
    """Обновляет Google таблицу"""
    logging.info("=" * 50)
    logging.info("Запуск обновления таблицы...")
    
    try:
        # Подключаемся к таблице
        ss = ezsheets.Spreadsheet(config.SHEET_ID)
        sheet = ss[0]  # Первый лист
        logging.info(f"Подключено к таблице: {ss.title}")
        
        # Получаем все значения
        all_values = sheet.get_all_values()
        
        if len(all_values) < 2:
            logging.warning("Таблица пуста")
            return
        
        # Заголовки (для информации)
        headers = all_values[0]
        logging.info(f"Заголовки: {headers}")
        
        updated_count = 0
        error_count = 0
        
        # Проходим по всем строкам, начиная с 1 (индекс 1 = вторая строка в таблице)
        for row_idx, row in enumerate(all_values[1:], start=2):
            # Проверяем, есть ли ссылка в столбце F (индекс 5)
            if len(row) <= 5:
                continue
                
            tracking_link = row[5].strip() if row[5] else ""
            
            if not tracking_link or not tracking_link.startswith('http'):
                continue
            
            logging.info(f"\n--- Обработка строки {row_idx} ---")
            logging.info(f"Ссылка: {tracking_link}")
            
            try:
                # Парсим данные
                data = parse_single_link(tracking_link)
                
                # Обновляем ячейки (столбцы A-E)
                sheet.update(row_idx, 1, data['source'])      # Source
                sheet.update(row_idx, 2, data['clicks'])      # Clicks
                sheet.update(row_idx, 3, data['fans'])        # Fans
                sheet.update(row_idx, 4, data['spenders'])    # Spenders
                sheet.update(row_idx, 5, data['income'])      # Income
                
                # Обновляем вторую дату в столбце G (Start / Update)
                current_date = datetime.now().strftime("%d.%m.%Y")
                
                if len(row) > 6:
                    old_value = row[6] if row[6] else ""
                else:
                    old_value = ""
                
                if ' / ' in old_value:
                    first_date = old_value.split(' / ')[0]
                    new_value = f"{first_date} / {current_date}"
                else:
                    new_value = f"{current_date} / {current_date}"
                
                sheet.update(row_idx, 7, new_value)
                
                updated_count += 1
                logging.info(f"✅ Строка {row_idx} обновлена")
                
            except Exception as e:
                error_count += 1
                logging.error(f"❌ Ошибка при обработке {tracking_link}: {e}")
                continue
            
            # Небольшая пауза между запросами, чтобы не перегружать сайт
            time.sleep(2)
        
        logging.info(f"\n{'='*50}")
        logging.info(f"Обновление завершено: {updated_count} строк обновлено, {error_count} ошибок")
        logging.info(f"{'='*50}")
        
    except Exception as e:
        logging.error(f"Критическая ошибка при работе с таблицей: {e}")
        raise

def main():
    """Основной цикл"""
    logging.info("😀Парсер OnlyMonster запущен")
    logging.info(f"Интервал обновления: {config.UPDATE_INTERVAL // 3600} часа")
    logging.info(f"ID таблицы: {config.SHEET_ID}")
    
    while True:
        try:
            update_google_sheet()
        except Exception as e:
            logging.error(f"Ошибка в основном цикле: {e}")
        
        wait_hours = config.UPDATE_INTERVAL // 3600
        logging.info(f"⏰ Следующее обновление через {wait_hours} часа(ов)")
        time.sleep(config.UPDATE_INTERVAL)

if __name__ == "__main__":
    main()