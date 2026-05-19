import os
import requests
import json
import time
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

def main():
    print("Start searching...")
    
    sheet_id = os.environ.get('GOOGLE_SHEET_ID')
    creds_json = os.environ.get('GOOGLE_SERVICE_ACCOUNT')
    
    if not sheet_id or not creds_json:
        print("ERROR: Missing secrets!")
        return

    try:
        creds_dict = json.loads(creds_json)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(sheet_id).sheet1
        
        if sheet.cell(1, 1).value == "":
            headers = ["Дата", "Вакансия", "ЗП", "Компания", "Дней", "Ссылка", "Город"]
            sheet.insert_row(headers, 1)
    except Exception as e:
        print(f"Google Error: {e}")
        return

    # Запрос к HH.ru
    params = {
        'text': 'финансовый директор',
        'area': 113,
        'per_page': 10
    }
    
    # ВАЖНО: Стандартный браузерный User-Agent
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json'
    }
    
    try:
        response = requests.get('https://api.hh.ru/vacancies', params=params, headers=headers, timeout=30)
        time.sleep(0.5)
        
        print(f"Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"Error: {response.text}")
            return
            
        items = response.json().get('items', [])
        print(f"Found: {len(items)}")
        
        for item in items:
            sal = item.get('salary') or {}
            zp = f"{sal.get('from','?')}-{sal.get('to','?')} {sal.get('currency','RUB')}" if sal else "Не указана"
            pub = datetime.fromisoformat(item['published_at'].replace('Z','+00:00'))
            days = (datetime.now(pub.tzinfo) - pub).days
            
            sheet.append_row([
                datetime.now().strftime("%Y-%m-%d"),
                item['name'],
                zp,
                item['employer']['name'],
                days,
                item['alternate_url'],
                item['area']['name']
            ])
        
        print(f"Added: {len(items)}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
