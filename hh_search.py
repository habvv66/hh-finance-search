#!/usr/bin/env python3
"""
Поиск вакансий на HH.ru и запись в Google Sheets.
Запускается в GitHub Actions.
"""

import os
import sys
import json
import time
import logging
import requests
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any

import gspread
from oauth2client.service_account import ServiceAccountCredentials
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# === Настройка логирования ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# === Константы ===
HH_API_BASE = 'https://api.hh.ru'
HH_API_TIMEOUT = 30
HH_MAX_RETRIES = 3
HH_RETRY_BACKOFF = 2  # секунды, экспоненциальный рост
HH_RATE_LIMIT_DELAY = 1.0  # задержка между запросами, секунды

GOOGLE_SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]


def create_requests_session() -> requests.Session:
    """Создаёт сессию с настройками повторов и таймаутов."""
    session = requests.Session()
    retry = Retry(
        total=HH_MAX_RETRIES,
        backoff_factor=HH_RETRY_BACKOFF,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=['GET', 'POST']
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('https://', adapter)
    session.mount('http://', adapter)
    return session


def fetch_vacancies(
    session: requests.Session,
    search_text: str,
    area_ids: List[str],
    per_page: int = 20
) -> List[Dict[str, Any]]:
    """Получает вакансии с HH.ru с обработкой лимитов."""
    all_items = []
    
    for area_id in area_ids:
        params = {
            'text': search_text,
            'area': area_id,
            'per_page': per_page,
            'order_by': 'publication_time'
        }
        
        url = f'{HH_API_BASE}/vacancies'
        headers = {
            'User-Agent': 'hh-finance-search-bot/1.0 (api@hh.ru)',
            'Accept': 'application/json'
        }
        
        try:
            logger.info(f'Запрос вакансий: area={area_id}, text="{search_text}"')
            response = session.get(url, params=params, headers=headers, timeout=HH_API_TIMEOUT)
            
            # Обработка 429 и других ошибок
            if response.status_code == 429:
                retry_after = response.headers.get('Retry-After', HH_RETRY_BACKOFF)
                logger.warning(f'Rate limit. Ждём {retry_after}с...')
                time.sleep(int(retry_after))
                response = session.get(url, params=params, headers=headers, timeout=HH_API_TIMEOUT)
            
            response.raise_for_status()
            data = response.json()
            items = data.get('items', [])
            all_items.extend(items)
            logger.info(f'Получено {len(items)} вакансий для area={area_id}')
            
            # Пауза между запросами к API
            time.sleep(HH_RATE_LIMIT_DELAY)
            
        except requests.exceptions.HTTPError as e:
            logger.error(f'HTTP ошибка для area={area_id}: {e}')
            if e.response is not None:
                logger.error(f'Ответ сервера: {e.response.text[:200]}')
        except requests.exceptions.RequestException as e:
            logger.error(f'Ошибка запроса для area={area_id}: {e}')
        except json.JSONDecodeError as e:
            logger.error(f'Ошибка парсинга JSON для area={area_id}: {e}')
    
    return all_items


def format_salary(salary: Optional[Dict[str, Any]]) -> str:
    """Форматирует информацию о зарплате."""
    if not salary:
        return 'Не указана'
    
    frm = salary.get('from')
    to = salary.get('to')
    currency = salary.get('currency', 'RUB')
    
    if frm and to:
        return f'{frm}-{to} {currency}'
    elif frm:
        return f'от {frm} {currency}'
    elif to:
        return f'до {to} {currency}'
    return 'Не указана'


def parse_published_date(date_str: str) -> Optional[datetime]:
    """Парсит дату публикации в формате ISO 8601."""
    try:
        # HH.ru возвращает формат: 2024-01-15T10:30:00+0300
        if date_str.endswith('Z'):
            date_str = date_str[:-1] + '+00:00'
        return datetime.fromisoformat(date_str)
    except (ValueError, AttributeError) as e:
        logger.warning(f'Не удалось распарсить дату "{date_str}": {e}')
        return None


def calculate_days_since(date: Optional[datetime]) -> int:
    """Вычисляет количество дней с указанной даты."""
    if not date:
        return -1
    now = datetime.now(timezone.utc)
    diff = now - date
    return max(0, diff.days)


def init_google_sheet(sheet_id: str, creds_json: str) -> Optional[gspread.Spreadsheet]:
    """Инициализирует подключение к Google Sheets."""
    try:
        creds_dict = json.loads(creds_json)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, GOOGLE_SCOPES)
        client = gspread.authorize(creds)
        return client.open_by_key(sheet_id)
    except json.JSONDecodeError as e:
        logger.error(f'Ошибка парсинга JSON ключа: {e}')
    except Exception as e:
        logger.error(f'Ошибка подключения к Google Sheets: {type(e).__name__}: {e}')
    return None


def ensure_headers(sheet: gspread.Worksheet, headers: List[str]) -> None:
    """Создаёт заголовки, если таблица пустая."""
    try:
        first_cell = sheet.cell(1, 1).value
        if not first_cell or first_cell.strip() == '':
            sheet.insert_row(headers, 1)
            logger.info('Заголовки добавлены в таблицу')
    except Exception as e:
        logger.warning(f'Не удалось проверить/добавить заголовки: {e}')


def append_rows(sheet: gspread.Worksheet, rows: List[List[Any]], start_row: int = 2) -> bool:
    """Добавляет строки в таблицу."""
    if not rows:
        logger.info('Нет данных для добавления')
        return True
    
    try:
        sheet.insert_rows(rows, start_row)
        logger.info(f'Добавлено {len(rows)} строк в таблицу')
        return True
    except Exception as e:
        logger.error(f'Ошибка записи в таблицу: {type(e).__name__}: {e}')
        return False


def main() -> int:
    """Точка входа."""
    logger.info('=== Запуск поиска вакансий ===')
    
    # 1. Проверка секретов
    sheet_id = os.environ.get('GOOGLE_SHEET_ID')
    creds_json = os.environ.get('GOOGLE_SERVICE_ACCOUNT')
    
    if not sheet_id or not creds_json:
        logger.error('ERROR: Отсутствуют обязательные переменные окружения!')
        logger.error('Проверьте настройки Secrets в репозитории:')
        logger.error('  - GOOGLE_SHEET_ID')
        logger.error('  - GOOGLE_SERVICE_ACCOUNT')
        return 1
    
    # 2. Инициализация сессии и Google Sheets
    session = create_requests_session()
    
    spreadsheet = init_google_sheet(sheet_id, creds_json)
    if not spreadsheet:
        return 1
    
    sheet = spreadsheet.sheet1
    headers = ['Дата поиска', 'Название', 'Зарплата', 'Компания', 'Дней в поиске', 'Ссылка', 'Город']
    ensure_headers(sheet, headers)
    
    # 3. Поиск вакансий
    search_text = os.environ.get('HH_SEARCH_TEXT', 'финансовый директор')
    area_ids = os.environ.get('HH_AREA_IDS', '1,11,1913').split(',')
    
    logger.info(f'Поиск: текст="{search_text}", регионы={area_ids}')
    
    vacancies = fetch_vacancies(session, search_text, area_ids)
    logger.info(f'Всего найдено вакансий: {len(vacancies)}')
    
    # 4. Подготовка данных
    rows_to_add = []
    for item in vacancies:
        pub_date = parse_published_date(item.get('published_at'))
        days_diff = calculate_days_since(pub_date)
        
        rows_to_add.append([
            datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
            item.get('name', 'Без названия'),
            format_salary(item.get('salary')),
            item.get('employer', {}).get('name', 'Не указано'),
            days_diff if days_diff >= 0 else '',
            item.get('alternate_url', ''),
            item.get('area', {}).get('name', '')
        ])
    
    # 5. Запись в таблицу
    success = append_rows(sheet, rows_to_add)
    
    logger.info('=== Завершение ===')
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
