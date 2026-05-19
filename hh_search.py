import os
import requests
import json
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

    # 3. Ищем вакансии на HH.ru
    # Финансовый директор в Воронеже и Москве
    #areas = '11, 1913' # 11 - Москва, 1913 - Воронеж
    #search_text = "Финансовый директор"
    areas = '1'  # 1 = Россия целиком
    search_text = "финансовый"  # найдёт и "финансовый директор", и "финансовый аналитик"
    
    url = f"https://api.hh.ru/vacancies?text={search_text}&area={areas}&order_by=publication_time&per_page=10"
    
    try:
        response = requests.get(url)
        data = response.json()
        items = data.get('items', [])
        
        print(f"Found {len(items)} vacancies.")
        
        # 4. Записываем данные в таблицу
        rows_to_add = []
        for item in items:
            salary = item.get('salary', {})
            salary_text = "Не указана"
            if salary:
                frm = salary.get('from', '?')
                to = salary.get('to', '?')
                currency = salary.get('currency', 'RUB')
                salary_text = f"{frm}-{to} {currency}"
            
            # Дата публикации
            pub_date_str = item.get('published_at')
            pub_date = datetime.fromisoformat(pub_date_str.replace('Z', '+00:00'))
            days_diff = (datetime.now(pub_date.tzinfo) - pub_date).days
            
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
            # Вставляем после заголовков
            sheet.insert_rows(rows_to_add, 2)
            print(f"Added {len(rows_to_add)} rows to sheet.")
        else:
            print("No vacancies found matching criteria.")
            
    except Exception as e:
        print(f"HH API Error: {e}")

if __name__ == "__main__":
    main()
