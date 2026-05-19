import os
import sys
import requests
import json
import urllib.parse
from datetime import datetime, timedelta, timezone
import gspread
from oauth2client.service_account import ServiceAccountCredentials

def setup_logging():
    """Настройка базового логгирования"""
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        stream=sys.stdout
    )
    return logging.getLogger(__name__)

def main():
    logger = setup_logging()
    logger.info("🚀 Starting HH.ru vacancy search...")
    
    # 1. Получаем настройки из Secrets
    sheet_id = os.environ.get('GOOGLE_SHEET_ID')
    creds_json = os.environ.get('GOOGLE_SERVICE_ACCOUNT')

    if not sheet_id or not creds_json:
        logger.error("❌ ERROR: Missing required secrets!")
        logger.error("   - GOOGLE_SHEET_ID")
        logger.error("   - GOOGLE_SERVICE_ACCOUNT")
        sys.exit(1)

    # 2. Настраиваем доступ к Google Таблицам
    try:
        logger.info("🔐 Authorizing Google Sheets access...")
        creds_dict = json.loads(creds_json)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(
            creds_dict, 
            scopes=['https://spreadsheets.google.com/feeds', 
                   'https://www.googleapis.com/auth/drive']
        )
        client = gspread.authorize(creds)
        sheet = client.open_by_key(sheet_id).sheet1
        
        # Заголовки, если таблица пустая или первый ряд пустой
        first_cell = sheet.cell(1, 1).value if sheet.row_values(1) else None
        if not first_cell or first_cell.strip() == "":
            logger.info("📝 Initializing sheet headers...")
            headers = ["Дата поиска", "Название", "Зарплата", "Компания", "Дней в поиске", "Ссылка", "Город"]
            sheet.insert_row(headers, 1)
        
        logger.info("✅ Google Sheets connected")
        
    except json.JSONDecodeError as e:
        logger.error(f"❌ Invalid JSON in GOOGLE_SERVICE_ACCOUNT: {e}")
        sys.exit(1)
    except gspread.exceptions.APIError as e:
        logger.error(f"❌ Google Sheets API error: {e}")
        logger.error("💡 Check: Service Account has editor access to the Sheet")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Google Sheets setup error: {type(e).__name__}: {e}")
        sys.exit(1)

    # 3. Ищем вакансии на HH.ru
    search_text = "финансовый директор"
    area_ids = ['1', '11', '1913']  # Россия, Москва, Воронеж

    params = {
        'text': search_text,
        'per_page': 20,
        'order_by': 'publication_time'
    }

    # Формируем URL с множественными area= параметрами
    query_parts = [f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items()]
    for area in area_ids:
        query_parts.append(f"area={area}")

    url = f"https://api.hh.ru/vacancies?{'&'.join(query_parts)}"
    headers = {
        'User-Agent': 'hh-finance-search-bot/1.0 (your-email@example.com)',
        'Accept': 'application/json'
    }

    try:
        logger.info(f"🔍 Requesting: {url[:100]}...")
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        items = data.get('items', [])
        
        logger.info(f"📦 Found {len(items)} vacancies from HH.ru API")
        
        # 4. Записываем данные в таблицу
        rows_to_add = []
        for idx, item in enumerate(items, 1):
            try:
                # Зарплата
                salary = item.get('salary') or {}
                if salary and (salary.get('from') or salary.get('to')):
                    frm = salary.get('from', '')
                    to = salary.get('to', '')
                    currency = salary.get('currency', 'RUB')
                    salary_text = f"{frm if frm else '?'}-{to if to else '?'} {currency}"
                else:
                    salary_text = "Не указана"
                
                # Дата публикации
                pub_date_str = item.get('published_at')
                if pub_date_str:
                    # Парсинг даты с обработкой разных форматов
                    pub_date_str = pub_date_str.replace('Z', '+00:00')
                    try:
                        pub_date = datetime.fromisoformat(pub_date_str)
                    except ValueError:
                        pub_date = datetime.now(timezone.utc)
                    days_diff = (datetime.now(timezone.utc) - pub_date).days
                else:
                    days_diff = 0
                
                # Данные строки
                row = [
                    datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
                    item.get('name', 'Без названия'),
                    salary_text,
                    (item.get('employer') or {}).get('name', 'Не указано'),
                    days_diff,
                    item.get('alternate_url', ''),
                    (item.get('area') or {}).get('name', '')
                ]
                rows_to_add.append(row)
                
            except Exception as row_error:
                logger.warning(f"⚠️ Skipping item #{idx}: {row_error}")
                continue
        
        # 5. Запись в таблицу
        if rows_to_add:
            logger.info(f"📤 Inserting {len(rows_to_add)} rows into sheet...")
            # Вставляем после заголовка (строка 2)
            sheet.insert_rows(rows_to_add, 2)
            logger.info(f"✅ Successfully added {len(rows_to_add)} rows")
        else:
            logger.info("ℹ️ No new vacancies found matching criteria")
            
    except requests.exceptions.Timeout:
        logger.error("❌ HH.ru API request timed out")
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ HH.ru API request failed: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Unexpected error: {type(e).__name__}: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        sys.exit(1)
    
    logger.info("🎉 Search completed successfully!")

# 🔧 ИСПРАВЛЕНО: было `if name == "main":`
if __name__ == "__main__":
    main()
