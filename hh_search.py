import os
import requests
import json
import urllib.parse
import time
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

def main():
    print("Start searching...")
    
    # 1. Получаем настройки из Secrets
    sheet_id = os.environ.get('GOOGLE_SHEET_ID')
    creds_json = os.environ.get('GOOGLE_SERVICE_ACCOUNT')
    
    if not sheet_id or not creds_json:
        print("ERROR: Missing secrets!")
        return

    # 2. Настраиваем доступ к Google Таблицам
    try:
        creds_dict = json.loads(creds_json)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict)
        client = gspread.authorize(creds)  # Исправлено: убран пробел в client
        sheet = client.open_by_key(sheet_id).sheet1
        
        # Заголовки, если таблица пустая
        if sheet.cell(1, 1).value == "":
            headers = ["Дата поиска", "Название", "Зарплата", "Компания", "Дней в поиске", "Ссылка", "Город"]
            sheet.insert_row(headers, 1)
            
    except Exception as e:
        print(f"Google Sheets Error: {e}")  # Исправлено: f-строка без пробела
        return

    # 3. Ищем вакансии на HH.ru
    import urllib.parse

    search_text = "финансовый директор"
    area_ids = ['1', '11', '1913']  # Россия, Москва, Воронеж

    params = {
        'text': search_text,
        'per_page': 20,
        'order_by': 'publication_time'
    }

    # HH.ru принимает несколько параметров area=
    query_parts = [f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items()]  # Исправлено
    for area in area_ids:
        query_parts.append(f"area={area}")

    url = f"https://api.hh.ru/vacancies?{'&'.join(query_parts)}"
    
    # ВАЖНО: Исправленный User-Agent, чтобы HH не давал ошибку 403
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json'
    }

    try:
        response = requests.get(url, headers=headers)
        time.sleep(0.5) # Пауза, чтобы не забанили
        
        data = response.json()
        items = data.get('items', [])
        
        print(f"Found {len(items)} vacancies.")  # Исправлено
        
        # 4. Записываем данные в таблицу
        rows_to_add = []
        for item in items:
            salary = item.get('salary', {})
            salary_text = "Не указана"
            if salary:
                frm = salary.get('from', '?')
                to = salary.get('to', '?')
                currency = salary.get('currency', 'RUB')
                salary_text = f"{frm}-{to} {currency}"  # Исправлено
            
            pub_date_str = item.get('published_at')
            pub_date = datetime.fromisoformat(pub_date_str.replace('Z', '+00:00'))
            days_diff = (datetime.now(pub_date.tzinfo) - pub_date).days  # Исправлено
            
            rows_to_add.append([
                datetime.now().strftime("%Y-%m-%d"),
                item.get('name'),
                salary_text,
                item.get('employer', {}).get('name'),
                days_diff,
                item.get('alternate_url'),
                item.get('area', {}).get('name')
            ])
            
        if rows_to_add:
            sheet.insert_rows(rows_to_add, 2)
            print(f"Added {len(rows_to_add)} rows to sheet.")
        else:
            print("No vacancies found matching criteria.")
            
    except Exception as e:
        print(f"HH API Error: {e}")

# Исправлено: правильная конструкция запуска
if __name__ == "__main__":
    main()
