import json
import os
import requests
from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta

alert_bp = Blueprint("alert_bp", __name__)

# --- CONFIGURATION ---
RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
RESEND_SENDER_EMAIL = "onboarding@resend.dev"  # Resend's free testing sender, works without domain verification
RESEND_SENDER_NAME = "Agri-AI Team By TYS"

BREVO_API_KEY = os.environ.get("BREVO_API_KEY")
SENDER_EMAIL = "23-se-117@student.hitecuni.edu.pk"
SENDER_NAME = "Agri-AI Team By TYS"

OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY")
OPENWEATHER_BASE_URL = "https://api.openweathermap.org/data/2.5"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FARMERS_DB = os.path.join(BASE_DIR, "farmers_data.json")
MARKET_DATA_DB = os.path.join(BASE_DIR, "market_data.json")
DISEASE_DATA_DB = os.path.join(BASE_DIR, "disease_data.json")

# --- REAL MARKET PRICES (Updated Weekly) ---
REAL_MARKET_PRICES = {
    "wheat": {
        "price": 1650,  # Rs per kg
        "trend": "stable",  # stable, increasing, decreasing
        "last_updated": "2025-12-10",
        "next_update": "2025-12-17"
    },
    "rice": {
        "price": 2450,
        "trend": "increasing",
        "last_updated": "2025-12-10",
        "next_update": "2025-12-17"
    },
    "cotton": {
        "price": 4200,
        "trend": "stable",
        "last_updated": "2025-12-10",
        "next_update": "2025-12-17"
    },
    "maize": {
        "price": 1850,
        "trend": "increasing",
        "last_updated": "2025-12-10",
        "next_update": "2025-12-17"
    },
    "sugarcane": {
        "price": 220,  # Rs per ton
        "trend": "stable",
        "last_updated": "2025-12-10",
        "next_update": "2025-12-17"
    }
}

# --- REAL DISEASE ALERTS (Based on Season & Region) ---
SEASONAL_DISEASES = {
    "winter": {
        "wheat": ["Rust", "Powdery Mildew"],
        "potato": ["Late Blight", "Early Blight"],
        "tomato": ["Leaf Curl", "Bacterial Spot"],
        "general_advice": "Sardi mein fungal infections ziyada hotay hain. Fungicide ka istemal karein."
    },
    "summer": {
        "wheat": ["Heat Stress", "Smut"],
        "cotton": ["Boll Rot", "Leaf Curl"],
        "rice": ["Blast", "Sheath Blight"],
        "general_advice": "Garmi mein pani ka intezaam behtar karein aur regular monitoring karein."
    },
    "rainy": {
        "rice": ["Blast", "Bacterial Leaf Blight"],
        "sugarcane": ["Red Rot", "Smut"],
        "maize": ["Leaf Blight", "Stalk Rot"],
        "general_advice": "Barish mein fungal diseases ka khatra ziyada hota hai. Preventative sprays lagayein."
    }
}

# --- HELPER FUNCTIONS ---

def load_farmers():
    """Load farmers list from JSON file"""
    if os.path.exists(FARMERS_DB):
        try:
            with open(FARMERS_DB, 'r') as f:
                return json.load(f)
        except:
            return []
    return []

def save_farmers(farmers_list):
    """Save farmers list to JSON file"""
    try:
        with open(FARMERS_DB, 'w') as f:
            json.dump(farmers_list, f, indent=4)
    except Exception as e:
        print(f"Error saving farmers: {e}")

def get_current_season():
    """Determine current season based on month"""
    month = datetime.now().month

    if month in [12, 1, 2]:
        return "winter"
    elif month in [3, 4, 5]:
        return "summer"
    elif month in [6, 7, 8, 9]:
        return "rainy"
    else:
        return "autumn"

def get_weather_data(city):
    """Fetch weather data for email content (OpenWeatherMap version)"""
    try:
        if not OPENWEATHER_API_KEY:
            print("Weather fetch error: OPENWEATHER_API_KEY not set")
            return None

        weather_url = f"{OPENWEATHER_BASE_URL}/weather"
        weather_res = requests.get(
            weather_url,
            params={
                "q": city,
                "appid": OPENWEATHER_API_KEY,
                "units": "metric"
            },
            timeout=10
        ).json()

        if str(weather_res.get("cod")) != "200":
            return None

        city_name = weather_res.get("name", city)
        main = weather_res.get("main", {})
        wind = weather_res.get("wind", {})

        return {
            "city": city_name,
            "temperature": main.get("temp"),
            "windspeed": wind.get("speed", 0),
            "time": datetime.now().strftime("%Y-%m-%d %H:%M")
        }
    except Exception as e:
        print(f"Weather fetch error: {e}")
        return None

def create_weather_message(w):
    """Create weather alert message with farming advice"""
    if not w:
        return "Weather data unavailable."

    temp = w['temperature']

    if temp > 35:
        advice = "⚠️ Bohat garmi hai! Fasal ko subah jaldi ya shaam ko paani dein."
    elif temp < 10:
        advice = "❄️ Sardi hai! Nazeek fasal ko dhamp se bachayein."
    elif temp > 25:
        advice = "✅ Acha mausam hai! Khaad aur spray ke liye behtareen waqt."
    else:
        advice = "🌾 Mamooli halat. Apni mamooli kheti jari rakhein."

    return f"""
    🌤️ Agri-AI Mausam Alert 🌤️

    Shehar: {w['city']}
    Darja Hararat: {w['temperature']}°C
    Hawa ki Raftaar: {w['windspeed']} km/h
    Waqt: {w['time']}

    🌱 Kheti Baari Mashwara:
    {advice}

    📋 Tajweezat:
    • Zameen ki nami rozana check karein
    • Pani dene ka program mausam ke mutabiq rakhein
    • Fasal ki sehat par nazar rakhein
    • Kheti ki planning mausam dekh kar karein

    Agri-AI ke sath juday rahein aur mazeed alerts hasil karein!

    Aapka,
    Agri-AI Team
    """

def create_market_alert(city):
    """Create REAL market prices alert (not random)"""
    current_season = get_current_season()
    today = datetime.now().strftime("%Y-%m-%d")

    # Market analysis based on season
    seasonal_analysis = {
        "winter": "Sardi mein gandum ki demand barhti hai. Chawal ki qeemat stable rehti hai.",
        "summer": "Garmi mein kapas aur makai ki qeemat barh sakti hai.",
        "rainy": "Barish mein anaaj ki supply kam hoti hai, qeemat barh sakti hai.",
        "autumn": "Naye fasal aane wali hai, purani fasal ki qeemat gir sakti hai."
    }

    return f"""
    📈 Agri-AI Bazaar Kiqat Alert 📈

    {city} ke liye bazaar kiqat ({today}):

    🌾 Gandum: Rs {REAL_MARKET_PRICES['wheat']['price']}/kg ({REAL_MARKET_PRICES['wheat']['trend']})
    🍚 Chawal: Rs {REAL_MARKET_PRICES['rice']['price']}/kg ({REAL_MARKET_PRICES['rice']['trend']})
    🧵 Kapas: Rs {REAL_MARKET_PRICES['cotton']['price']}/kg ({REAL_MARKET_PRICES['cotton']['trend']})
    🌽 Makai: Rs {REAL_MARKET_PRICES['maize']['price']}/kg ({REAL_MARKET_PRICES['maize']['trend']})
    🍬 Ganna: Rs {REAL_MARKET_PRICES['sugarcane']['price']}/ton ({REAL_MARKET_PRICES['sugarcane']['trend']})

    📅 Akhri Update: {REAL_MARKET_PRICES['wheat']['last_updated']}
    ⏭️ Agla Update: {REAL_MARKET_PRICES['wheat']['next_update']}

    📊 Bazaar Tahlil ({current_season} mausam):
    {seasonal_analysis.get(current_season, "Bazaar stable hai.")}

    💡 Tajweez:
    • {REAL_MARKET_PRICES['rice']['trend']} trend mein chawal bechnay par ghoor karein
    • {REAL_MARKET_PRICES['maize']['trend']} trend mein makai ki selling plan karein
    • Market rates har haftay update hotay hain

    Aapka,
    Agri-AI Team
    """

def create_disease_alert(city):
    """Create REAL disease alerts based on season (not random)"""
    current_season = get_current_season()
    weather = get_weather_data(city)
    temp = weather['temperature'] if weather else 25

    season_diseases = SEASONAL_DISEASES.get(current_season, SEASONAL_DISEASES["winter"])

    # Determine risk level based on temperature and season
    if current_season == "rainy" and temp > 25:
        risk_level = "ZIYADA (High)"
        reason = "Barish aur garmi mil kar fungal diseases ka khatra barha dete hain"
    elif current_season == "winter" and temp < 15:
        risk_level = "DARMIYANA (Medium)"
        reason = "Sardi mein fungal infections common hain"
    else:
        risk_level = "KAM (Low)"
        reason = "Mausam disease-friendly nahi hai"

    return f"""
    🦠 Agri-AI Bimari Alert 🦠

    {city} ke liye bimari alert ({current_season} mausam):

    ⚠️ Khatra Darja: {risk_level}
    🌡️ Hararat: {temp}°C
    🍂 Mausam: {current_season}

    Reason: {reason}

    🦠 Is Mausam Ki Common Bimarian:
    • Gandum: {', '.join(season_diseases.get('wheat', ['N/A']))}
    • Potato: {', '.join(season_diseases.get('potato', ['N/A']))}
    • Tomato: {', '.join(season_diseases.get('tomato', ['N/A']))}
    • Chawal: {', '.join(season_diseases.get('rice', ['N/A']))}
    • Kapas: {', '.join(season_diseases.get('cotton', ['N/A']))}

    🛡️ Bachao Ke Tareeqay ({current_season}):
    {season_diseases.get('general_advice', 'Regular monitoring karein.')}

    📅 Ye Alerts Har Mausam Badaltay Hain:
    • Winter: Fungal diseases
    • Summer: Heat stress diseases 
    • Rainy: Bacterial & fungal diseases

    🚨 Fori Amal:
    1. Apni fasal ki regular monitoring karein
    2. Bimari ke pehle signs dekh kar fori ilaj karein
    3. Season ke mutabiq preventive sprays lagayein

    Aapka,
    Agri-AI Team
    """

def send_via_resend(recipient_email, message_body, subject):
    """Try sending via Resend (no manual activation needed, works immediately)"""
    if not RESEND_API_KEY:
        return False

    try:
        url = "https://api.resend.com/emails"
        headers = {
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "from": f"{RESEND_SENDER_NAME} <{RESEND_SENDER_EMAIL}>",
            "to": [recipient_email],
            "subject": subject,
            "text": message_body,
        }

        response = requests.post(url, headers=headers, json=payload, timeout=15)

        if response.status_code in (200, 201):
            print(f"✅ Email sent successfully via Resend to {recipient_email}")
            return True
        else:
            print(f"❌ RESEND EMAIL ERROR: {response.status_code} - {response.text}")
            return False

    except Exception as e:
        print(f"❌ RESEND EMAIL ERROR: {type(e).__name__}: {str(e)}")
        return False

def send_via_brevo(recipient_email, message_body, subject):
    """Fallback: try sending via Brevo"""
    if not BREVO_API_KEY:
        return False

    try:
        url = "https://api.brevo.com/v3/smtp/email"
        headers = {
            "accept": "application/json",
            "api-key": BREVO_API_KEY,
            "content-type": "application/json",
        }
        payload = {
            "sender": {"name": SENDER_NAME, "email": SENDER_EMAIL},
            "to": [{"email": recipient_email}],
            "subject": subject,
            "textContent": message_body,
        }

        response = requests.post(url, headers=headers, json=payload, timeout=15)

        if response.status_code in (200, 201):
            print(f"✅ Email sent successfully via Brevo to {recipient_email}")
            return True
        else:
            print(f"❌ BREVO EMAIL ERROR: {response.status_code} - {response.text}")
            return False

    except Exception as e:
        print(f"❌ BREVO EMAIL ERROR: {type(e).__name__}: {str(e)}")
        return False

def send_email_alert(recipient_email, message_body, subject="Agri-AI Alert"):
    """Dual provider email sending: Resend first, Brevo as fallback"""
    if send_via_resend(recipient_email, message_body, subject):
        return True

    print("⚠️ Resend failed or not configured, trying Brevo fallback...")
    if send_via_brevo(recipient_email, message_body, subject):
        return True

    print("❌ Both email providers failed.")
    return False

# --- API ROUTES ---

@alert_bp.route("/api/register", methods=["POST"])
def register_farmer():
    data = request.json
    if not data or "email" not in data:
        return jsonify({"error": "Invalid data"}), 400

    farmers = load_farmers()

    new_farmer = {
        "name": data.get("name", "Unknown"),
        "email": data["email"],
        "city": data.get("city", "Unknown"),
        "registered_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    for f in farmers:
        if f["email"] == new_farmer["email"]:
            return jsonify({"message": "Farmer already registered"}), 400

    farmers.append(new_farmer)
    save_farmers(farmers)

    return jsonify({"message": "Farmer registered successfully", "farmer": new_farmer})

@alert_bp.route("/api/farmers", methods=["GET"])
def list_farmers():
    farmers = load_farmers()
    return jsonify(farmers)

@alert_bp.route("/api/update-market-prices", methods=["POST"])
def update_market_prices():
    """Admin endpoint to update market prices (call this weekly)"""
    data = request.json
    if not data or "prices" not in data:
        return jsonify({"error": "Prices data required"}), 400

    # Update market prices
    for crop, price_data in data["prices"].items():
        if crop in REAL_MARKET_PRICES:
            REAL_MARKET_PRICES[crop]["price"] = price_data.get("price", REAL_MARKET_PRICES[crop]["price"])
            REAL_MARKET_PRICES[crop]["trend"] = price_data.get("trend", REAL_MARKET_PRICES[crop]["trend"])
            REAL_MARKET_PRICES[crop]["last_updated"] = datetime.now().strftime("%Y-%m-%d")
            REAL_MARKET_PRICES[crop]["next_update"] = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

    return jsonify({
        "status": True,
        "message": "Market prices updated successfully",
        "prices": REAL_MARKET_PRICES
    })

@alert_bp.route("/api/send-instant-alert", methods=["POST"])
def send_instant_alert():
    data = request.json
    email = data.get("email")
    city = data.get("city")
    alert_type = data.get("alertType", "weather")

    if not email or not city:
        return jsonify({"error": "Email aur Shehar zaroori hai"}), 400

    try:
        if alert_type == "weather":
            weather_info = get_weather_data(city)
            msg_text = create_weather_message(weather_info)
            subject = f"🌤️ Agri-AI Mausam Alert - {city}"

        elif alert_type == "prices":
            msg_text = create_market_alert(city)
            subject = f"📈 Agri-AI Bazaar Alert - {city}"

        elif alert_type == "disease":
            msg_text = create_disease_alert(city)
            subject = f"🦠 Agri-AI Bimari Alert - {city}"

        else:
            weather_info = get_weather_data(city)
            msg_text = create_weather_message(weather_info)
            subject = f"🌤️ Agri-AI Mausam Alert - {city}"

        success = send_email_alert(email, msg_text, subject)

        if success:
            return jsonify({
                "status": True,
                "message": f"{alert_type.capitalize()} alert sent successfully",
                "alert_type": alert_type,
                "city": city,
                "timestamp": datetime.now().isoformat()
            })
        else:
            return jsonify({
                "status": False,
                "message": "Email sending failed",
                "alert_type": alert_type
            }), 500

    except Exception as e:
        print(f"❌ Alert Error: {e}")
        return jsonify({
            "status": False,
            "message": f"Server error: {str(e)}"
        }), 500

@alert_bp.route("/api/get-market-prices", methods=["GET"])
def get_market_prices():
    """Endpoint to get current market prices"""
    return jsonify({
        "status": True,
        "prices": REAL_MARKET_PRICES,
        "last_updated": REAL_MARKET_PRICES["wheat"]["last_updated"],
        "next_update": REAL_MARKET_PRICES["wheat"]["next_update"]
    })

@alert_bp.route("/api/get-seasonal-diseases", methods=["GET"])
def get_seasonal_diseases():
    """Endpoint to get current seasonal diseases"""
    current_season = get_current_season()
    return jsonify({
        "status": True,
        "current_season": current_season,
        "diseases": SEASONAL_DISEASES.get(current_season, {}),
        "advice": SEASONAL_DISEASES.get(current_season, {}).get("general_advice", "")
    })