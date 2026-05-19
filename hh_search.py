import os
import requests
import json
import time
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

def main():
    print("Start")
    sheet_id = os.environ.get('GOOGLE_SHEET_ID')
    creds_json = os.environ.get('GOOGLE_SERVICE_ACCOUNT')
    if not sheet_id or not creds_json:
        print("No secrets")
        return
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(creds_json))
        sheet = gspread.authorize(creds).open_by_key(sheet_id).sheet1
        if not sheet.cell(1,1).value:
            sheet.insert_row(["Date","Job","Salary","Company","Days","Link","City"], 1)
    except Exception as e:
        print(f"GS Error: {e}")
        return
    params = {'text':'финансовый директор','area':113,'per_page':5}
    headers = {'User-Agent':'Mozilla/5.0','Accept':'application/json'}
    try:
        r = requests.get('https://api.hh.ru/vacancies', params=params, headers=headers, timeout=30)
        time.sleep(0.5)
        print(f"Status:{r.status_code}")
        if r.status_code != 200:
            print(f"Err:{r.text}")
            return
        items = r.json().get('items',[])
        print(f"Found:{len(items)}")
        for it in items:
            s = it.get('salary') or {}
            zp = f"{s.get('from','?')}-{s.get('to','?')} {s.get('currency','RUB')}" if s else "N/A"
            pub = datetime.fromisoformat(it['published_at'].replace('Z','+00:00'))
            days = (datetime.now(pub.tzinfo)-pub).days
            sheet.append_row([datetime.now().strftime("%Y-%m-%d"),it['name'],zp,it['employer']['name'],days,it['alternate_url'],it['area']['name']])
        print(f"Added:{len(items)}")
    except Exception as e:
        print(f"Err:{e}")

if __name__ == "__main__":
    main()
