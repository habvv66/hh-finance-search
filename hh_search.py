import os
import requests
import json
import time
from datetime import datetime, timedelta
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
        client = gspread.authorize(creds)
        sheet = client.open_by_key(sheet_id).sheet1
        
        # Заголовки, если таблица пустая
        if sheet.cell(1, 1).value == "":
            headers = ["Дата поиска", "Название", "Зарплата", "Компания", "Дней в поиске", "Ссылка", "Город"]
            sheet.insert_row(headers, 1)
    except Exception as e:
        print(f"Google Sheets Error: {e}")
        return

    # 3. Ищем вакансии на HH.ru (ИСПРАВЛЕНО для 403)
    params = {
        'text': 'финансовый директор',
        'area': 113,  # Россия по документации HH
        'per_page': 20,
        'order_by': 'publication_time'
    }
    
    # Правильные заголовки, чтобы не получить 403
    headers = {
        'User-Agent': 'MyApp/1.0 (habvv66@gmail.com)',
        'Accept': 'application/json'
    }
    
    try:
        # requests сам закодирует параметры + добавим задержку
        response = requests.get('https://api.hh.ru/vacancies', params=params, headers=headers, timeout=30)
        time.sleep(0.3)  # Задержка из статьи Habr
        
        print(f"HH.ru status: {response.status_code}")
        
        if response.status_code == 403:
            print("ERROR 403: Проверьте User-Agent и заголовки!")
            return
        elif response.status_code != 200:
            print(f"HH.ru error: {response.status_code} - {response.text}")
            return
            
        data = response.json()
        items = data.get('items', [])
        print(f"Found {len(items)} vacancies.")
        
        # 4. Записываем данные в таблицу
        for item in items:
            salary = item.get('salary') or {}
            if salary:
                frm = salary.get('from', '?')
                to = salary.get('to', '?')
                curr = salary.get('currency', 'RUB')
                salary_text = f"{frm}-{to} {curr}"
            else:
                salary_text = "Не указана"
            
            pub_date = datetime.fromisoformat(item['published_at'].replace('Z', '+00:00'))
            days = (datetime.now(pub_date.tzinfo) - pub_date).days
            
            sheet.append_row([
                datetime.now().strftime("%Y-%m-%d"),
                item['name'],
                salary_text,
                item['employer']['name'],
                days,
                item['alternate_url'],
                item['area']['name']
            ])
        
        print(f"Added {len(items)} rows to sheet.")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
