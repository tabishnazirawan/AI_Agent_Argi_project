import time
import requests
from apscheduler.schedulers.background import BackgroundScheduler

FARMER = {
    "name": "Muhammad Tabish", 
    "email": "tabishnazir0101@gmail.com", 
    "city": "Islamabad"
}

BASE_URL = "http://127.0.0.1:5000/api/send-instant-alert"

def send_alert(alert_type):
    print(f"📧 {time.strftime('%H:%M:%S')} - Sending {alert_type} alert...")
    try:
        response = requests.post(BASE_URL, json={
            "email": FARMER["email"],
            "city": FARMER["city"],
            "alertType": alert_type
        }, timeout=15)
        
        if response.status_code == 200:
            print(f"✅ {alert_type.upper()} alert sent to {FARMER['email']}")
        else:
            print(f"❌ Failed: {response.json().get('message')}")
    except Exception as e:
        print(f"❌ Connection error: {e}")

def morning_weather():
    send_alert("weather")

def afternoon_prices():
    send_alert("prices")

def evening_disease():
    send_alert("disease")

scheduler = BackgroundScheduler()

# Subah 8 baje — Weather
scheduler.add_job(morning_weather, 'cron', hour=8, minute=0)

# Dopahar 2 baje — Market Prices
scheduler.add_job(afternoon_prices, 'cron', hour=14, minute=0)

# Shaam 6 baje — Disease Alert
scheduler.add_job(evening_disease, 'cron', hour=18, minute=0)

scheduler.start()
print("🛡️ Agri-AI Scheduler active...")
print("⏰ Schedule: Weather@8AM | Prices@2PM | Disease@6PM")

try:
    while True:
        time.sleep(60)
except (KeyboardInterrupt, SystemExit):
    scheduler.shutdown()
    print("🛑 Scheduler stopped.")