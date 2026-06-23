import os
import asyncio

import logging

import numpy as np


from keras.applications.mobilenet_v2 import preprocess_input
from flask import Flask, request, jsonify

from flask_cors import CORS

import requests

import joblib

import pickle



import keras

from alert_blueprint import alert_bp  # type: ignore

import base64

from io import BytesIO
from agent_engine.orchestration_core import run_agent
from PIL import Image



# ---------------------------------------------------------

# App Init

# ---------------------------------------------------------

app = Flask(__name__)

CORS(app, resources={r"/*": {"origins": "*"}})



# Logging

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)



# Register Blueprints

app.register_blueprint(alert_bp)



# ---------------------------------------------------------

# OpenWeatherMap Configuration

# ---------------------------------------------------------

OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY")
OPENWEATHER_BASE_URL = "https://api.openweathermap.org/data/2.5"



# ---------------------------------------------------------

# Safe Model Loader (ONLY for pickle / joblib models)

# ---------------------------------------------------------

def safe_load(path):

    try:

        return joblib.load(path)

    except:

        try:

            with open(path, "rb") as f:

                return pickle.load(f)

        except:

            return None



BASE_DIR = os.path.dirname(os.path.abspath(__file__))

MODEL_DIR = os.path.join(BASE_DIR, "models")



# ---------------------------------------------------------

# Load Models

# ---------------------------------------------------------

# ---------------------------------------------------------
# Lazy Model Loaders (load on first use, not on startup)
# ---------------------------------------------------------
adv_model = None
scaler = None
crop_yield_model = None
disease_model = None

def get_adv_model():
    global adv_model, scaler
    if adv_model is None:
        adv_model = safe_load(os.path.join(MODEL_DIR, "pesticide_yield_model.pkl"))
        scaler = safe_load(os.path.join(MODEL_DIR, "scaler.pkl"))
        logger.info("✅ Pesticide/Adv model loaded (lazy)")
    return adv_model, scaler

def get_crop_yield_model():
    global crop_yield_model
    if crop_yield_model is None:
        try:
            crop_yield_model = joblib.load(os.path.join(MODEL_DIR, "crop_yield_model.pkl"))
            logger.info("✅ Crop Yield V2 model loaded (lazy)")
        except Exception as e:
            logger.error(f"❌ Crop Yield V2 load failed: {e}")
    return crop_yield_model

def get_disease_model():
    global disease_model
    if disease_model is None:
        try:
            disease_model = keras.models.load_model(
                os.path.join(MODEL_DIR, "PlantDoctor_Final_v1.keras"),
                compile=False
            )
            print("✅ Disease model (PlantDoctor_Final_v1) loaded successfully (lazy)")
        except Exception as e:
            print(f"❌ Failed to load disease model: {e}")
    return disease_model

# ---------------------------------------------------------

# Disease Classes Mapping

# ---------------------------------------------------------

DISEASE_CLASSES = {

    0: "Apple - Apple scab",

    1: "Apple - Black rot",

    2: "Apple - Cedar apple rust",

    3: "Apple - Healthy",

    4: "Blueberry - Healthy",

    5: "Cherry (including sour) - Powdery mildew",

    6: "Cherry (including sour) - Healthy",

    7: "Corn (maize) - Cercospora leaf spot / Gray leaf spot",

    8: "Corn (maize) - Common rust",

    9: "Corn (maize) - Northern Leaf Blight",

    10: "Corn (maize) - Healthy",

    11: "Grape - Black rot",

    12: "Grape - Esca (Black Measles)",

    13: "Grape - Leaf blight (Isariopsis Leaf Spot)",

    14: "Grape - Healthy",

    15: "Orange - Haunglongbing (Citrus greening)",

    16: "Peach - Bacterial spot",

    17: "Peach - Healthy",

    18: "Pepper (bell) - Bacterial spot",

    19: "Pepper (bell) - Healthy",

    20: "Potato - Early blight",

    21: "Potato - Late blight",

    22: "Potato - Healthy",

    23: "Raspberry - Healthy",

    24: "Soybean - Healthy",

    25: "Squash - Powdery mildew",

    26: "Strawberry - Leaf scorch",

    27: "Strawberry - Healthy",

    28: "Tomato - Bacterial spot",

    29: "Tomato - Early blight",

    30: "Tomato - Late blight",

    31: "Tomato - Leaf Mold",

    32: "Tomato - Septoria leaf spot",

    33: "Tomato - Spider mites",

    34: "Tomato - Target Spot",

    35: "Tomato - Yellow Leaf Curl Virus",

    36: "Tomato - Mosaic Virus",

    37: "Tomato - Healthy"

}



# ---------------------------------------------------------

# Debug Logs for Each Request

# ---------------------------------------------------------

@app.before_request

def log_request_info():

    print(f"➡️ Request: {request.method} {request.path}")



# ---------------------------------------------------------

# Routes

# ---------------------------------------------------------

@app.route("/", methods=["GET"])

def home():

    return jsonify({

        "status": "success",

        "message": "Agri-AI Flask Backend is running!",

        "server": "Disease Detection API",

        "version": "1.0"

    })



# ---------------------------------------------------------

# Yield Prediction

# ---------------------------------------------------------

@app.route("/predict_yield", methods=["POST"])
def predict_yield():
    try:
        import pandas as pd
        data = request.get_json()
        city       = data.get("city", "Lahore")
        crop       = data.get("crop_type", "Wheat")
        fertilizer = float(data.get("fertilizer", 65))
        temp       = float(data.get("temp", 28))
        N          = float(data.get("n", 70))
        P          = float(data.get("p", 21))
        K          = float(data.get("k", 18))
        NPK_total       = N + P + K
        fert_per_NPK    = fertilizer / (NPK_total + 1e-5)
        temp_N_interact = temp * N
        input_df = pd.DataFrame([{
            "city": city, "crop": crop,
            "Fertilizer": fertilizer, "temp": temp,
            "N": N, "P": P, "K": K,
            "NPK_total": NPK_total,
            "fert_per_NPK": fert_per_NPK,
            "temp_N_interact": temp_N_interact,
        }])
        crop_yield_model = get_crop_yield_model()
        if crop_yield_model:
            YIELD_CONVERSION = {"wheat": 135, "rice": 210, "maize": 220, "cotton": 120, "sugarcane": 2700}
            raw = crop_yield_model.predict(input_df)[0]
            factor = YIELD_CONVERSION.get(crop.lower(), 150)
            prediction = raw * factor
        else:
            prediction = NPK_total * 0.05
        return jsonify({"predicted_yield": round(float(prediction), 4)})
    except Exception as e:
        logger.error(f"Yield Prediction Error: {e}")
        return jsonify({"error": str(e)}), 500
# ---------------------------------------------------------

# Weather API - OpenWeatherMap Version

# ---------------------------------------------------------

@app.route("/weather", methods=["GET"])

def get_weather():

    city = request.args.get("city")

    if not city:

        return jsonify({"error": "City required"}), 400



    if not OPENWEATHER_API_KEY:

        return jsonify({"error": "Weather service not configured"}), 500



    try:

        # Single call: current weather by city name (includes coordinates, country, etc.)

        weather_response = requests.get(

            f"{OPENWEATHER_BASE_URL}/weather",

            params={

                "q": city,

                "appid": OPENWEATHER_API_KEY,

                "units": "metric"

            },

            timeout=10

        ).json()



        if str(weather_response.get("cod")) != "200":

            return jsonify({"error": weather_response.get("message", "City not found")}), 404



        lat = weather_response["coord"]["lat"]

        lon = weather_response["coord"]["lon"]

        found_city = weather_response.get("name", city)

        country = weather_response.get("sys", {}).get("country", "")



        main = weather_response.get("main", {})

        wind = weather_response.get("wind", {})

        weather_arr = weather_response.get("weather", [{}])

        weather_id = weather_arr[0].get("id", 800) if weather_arr else 800

        condition_name = weather_arr[0].get("description", "Unknown").capitalize() if weather_arr else "Unknown"



        # Get 3-day forecast using the 5 day / 3 hour forecast endpoint

        forecast_response = requests.get(

            f"{OPENWEATHER_BASE_URL}/forecast",

            params={

                "lat": lat,

                "lon": lon,

                "appid": OPENWEATHER_API_KEY,

                "units": "metric"

            },

            timeout=10

        ).json()



        forecast_list = forecast_response.get("list", [])



        return jsonify({

            "city": found_city,

            "region": "",

            "country": country,

            "temperature": main.get("temp"),

            "feels_like": main.get("feels_like", main.get("temp")),

            "humidity": main.get("humidity", 50),

            "windspeed": wind.get("speed", 0),

            "wind_direction": get_wind_direction(wind.get("deg", 0)),

            "weathercode": weather_id,

            "condition": condition_name,

            "last_updated": "Now",

            "is_day": 1,

            "cloud": weather_response.get("clouds", {}).get("all", 0),

            "pressure_mb": main.get("pressure", 1013),

            "precip_mm": 0,

            "uv": 5,

            "forecast": get_forecast_data_owm(forecast_list) if forecast_list else []

        })



    except requests.exceptions.Timeout:

        return jsonify({"error": "Weather service timeout"}), 408

    except requests.exceptions.RequestException as e:

        logger.error(f"Weather API error: {e}")

        return jsonify({"error": f"Weather service error: {str(e)}"}), 500

    except Exception as e:

        logger.error(f"Server error in weather endpoint: {e}")

        return jsonify({"error": f"Server error: {str(e)}"}), 500



def get_weather_condition(weathercode):

    """Convert WMO weather code to human-readable condition (legacy helper, kept for compatibility)"""

    if weathercode == 0:

        return "Clear sky"

    elif weathercode == 1:

        return "Mainly clear"

    elif weathercode == 2:

        return "Partly cloudy"

    elif weathercode == 3:

        return "Overcast"

    elif weathercode in [45, 48]:

        return "Fog"

    elif weathercode in [51, 53, 55]:

        return "Drizzle"

    elif weathercode in [61, 63, 65]:

        return "Rain"

    elif weathercode in [71, 73, 75]:

        return "Snow"

    elif weathercode in [80, 81, 82]:

        return "Rain showers"

    elif weathercode in [85, 86]:

        return "Snow showers"

    elif weathercode in [95, 96, 99]:

        return "Thunderstorm"

    else:

        return "Unknown"



def get_wind_direction(degrees):

    """Convert wind degrees to direction"""

    directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]

    idx = round(degrees / 45) % 8

    return directions[idx]



def get_cloud_cover(weathercode):

    """Estimate cloud cover percentage from weathercode (legacy helper, kept for compatibility)"""

    if weathercode in [0, 1]:

        return 10

    elif weathercode == 2:

        return 40

    elif weathercode == 3:

        return 90

    elif weathercode in [45, 48]:

        return 100

    elif weathercode >= 51:

        return 80

    else:

        return 50



def simulate_humidity(weathercode, temperature):

    """Legacy helper, kept for compatibility (OpenWeatherMap provides real humidity now)"""

    base_humidity = 50

    if weathercode in [45, 48, 51, 53, 55, 61, 63, 65, 80, 81, 82]:

        base_humidity = 85

    elif weathercode in [0, 1]:

        base_humidity = 30

    if temperature > 30:

        base_humidity -= 10

    elif temperature < 10:

        base_humidity += 15

    return max(20, min(base_humidity, 100))



def get_day_name(offset):

    """Get day name for forecast"""

    from datetime import datetime, timedelta

    days = ["Aaj", "Kal", "Parsun"]

    if offset < len(days):

        return days[offset]

    target_date = datetime.now() + timedelta(days=offset)

    return target_date.strftime("%a")



def get_forecast_data_owm(forecast_list):

    """Extract a 3-day forecast (one entry per day, around midday) from OpenWeatherMap's 3-hourly list"""

    if not forecast_list:

        return []



    daily_buckets = {}

    for entry in forecast_list:

        date_str = entry["dt_txt"].split(" ")[0]

        daily_buckets.setdefault(date_str, []).append(entry)



    forecast = []

    for i, (date_str, entries) in enumerate(list(daily_buckets.items())[:3]):

        temps = [e["main"]["temp"] for e in entries]

        # Prefer the entry closest to midday for the representative weather code

        midday_entry = min(entries, key=lambda e: abs(int(e["dt_txt"].split(" ")[1].split(":")[0]) - 12))

        weather_id = midday_entry["weather"][0]["id"] if midday_entry.get("weather") else 800

        condition = midday_entry["weather"][0]["description"].capitalize() if midday_entry.get("weather") else "Unknown"

        forecast.append({

            "day": get_day_name(i),

            "max_temp": round(max(temps), 1),

            "min_temp": round(min(temps), 1),

            "weathercode": weather_id,

            "condition": condition

        })



    return forecast



# ---------------------------------------------------------

# Simple Weather by Coordinates (for testing)

# ---------------------------------------------------------

@app.route("/weather_by_coords", methods=["GET"])

def get_weather_by_coords():

    """Simple endpoint for testing - just uses city weather"""

    lat = request.args.get("lat")

    lon = request.args.get("lon")

    

    if not lat or not lon:

        return jsonify({"error": "Latitude and longitude required"}), 400

    

    # For simplicity, use a default city

    return jsonify({

        "message": "Coordinates received",

        "note": "Using Islamabad as default for testing",

        "suggestion": "Use /weather?city=YourCity for full weather data"

    })



# ---------------------------------------------------------

# Current Location Weather (simple version)

# ---------------------------------------------------------

@app.route("/weather_current", methods=["GET"])

def get_current_location_weather():

    """Simple current location endpoint"""

    # For testing, return Islamabad weather

    return get_weather_by_city_name("Islamabad")



def get_weather_by_city_name(city_name):

    """Helper function to get weather for a specific city (OpenWeatherMap version)"""

    try:

        if not OPENWEATHER_API_KEY:

            return jsonify({"error": "Weather service not configured"}), 500



        weather_response = requests.get(

            f"{OPENWEATHER_BASE_URL}/weather",

            params={

                "q": city_name,

                "appid": OPENWEATHER_API_KEY,

                "units": "metric"

            },

            timeout=10

        ).json()



        if str(weather_response.get("cod")) != "200":

            return jsonify({"error": weather_response.get("message", "City not found")}), 404



        found_city = weather_response.get("name", city_name)

        main = weather_response.get("main", {})

        wind = weather_response.get("wind", {})

        weather_arr = weather_response.get("weather", [{}])

        weather_id = weather_arr[0].get("id", 800) if weather_arr else 800

        condition_name = weather_arr[0].get("description", "Unknown").capitalize() if weather_arr else "Unknown"



        return jsonify({

            "city": found_city,

            "temperature": main.get("temp"),

            "windspeed": wind.get("speed", 0),

            "weathercode": weather_id,

            "condition": condition_name,

            "humidity": main.get("humidity", 50)

        })



    except Exception as e:

        return jsonify({"error": str(e)}), 500



# ---------------------------------------------------------

# Weather Forecast Endpoint (3-day forecast)

# ---------------------------------------------------------

@app.route("/forecast", methods=["GET"])

def get_forecast():

    """Get 3-day weather forecast (OpenWeatherMap version)"""

    city = request.args.get("city")

    if not city:

        return jsonify({"error": "City required"}), 400



    if not OPENWEATHER_API_KEY:

        return jsonify({"error": "Weather service not configured"}), 500



    try:

        current_response = requests.get(

            f"{OPENWEATHER_BASE_URL}/weather",

            params={

                "q": city,

                "appid": OPENWEATHER_API_KEY,

                "units": "metric"

            },

            timeout=10

        ).json()



        if str(current_response.get("cod")) != "200":

            return jsonify({"error": current_response.get("message", "City not found")}), 404



        found_city = current_response.get("name", city)

        lat = current_response["coord"]["lat"]

        lon = current_response["coord"]["lon"]



        forecast_response = requests.get(

            f"{OPENWEATHER_BASE_URL}/forecast",

            params={

                "lat": lat,

                "lon": lon,

                "appid": OPENWEATHER_API_KEY,

                "units": "metric"

            },

            timeout=10

        ).json()



        forecast_list = forecast_response.get("list", [])

        forecast_data = get_forecast_data_owm(forecast_list)



        return jsonify({

            "city": found_city,

            "forecast": forecast_data

        })



    except requests.exceptions.Timeout:

        return jsonify({"error": "Weather service timeout"}), 408

    except requests.exceptions.RequestException as e:

        logger.error(f"Forecast API error: {e}")

        return jsonify({"error": f"Weather service error: {str(e)}"}), 500

    except Exception as e:

        logger.error(f"Server error in forecast endpoint: {e}")

        return jsonify({"error": f"Server error: {str(e)}"}), 500

# ---------------------------------------------------------

# Disease Prediction (Base64 Image)

# ---------------------------------------------------------

@app.route("/predict_disease", methods=["POST"])

def predict_disease():

    try:

        data = request.get_json()

        base64_img_data = data.get("image")



        if not base64_img_data:

            return jsonify({"error": "No image found"}), 400



        if "base64," in base64_img_data:

            base64_img_data = base64_img_data.split("base64,", 1)[1]



        image_bytes = base64.b64decode(base64_img_data)

        pil_img = Image.open(BytesIO(image_bytes))



        if pil_img.mode != 'RGB':

            pil_img = pil_img.convert('RGB')



        pil_img = pil_img.resize((224, 224))

        
        img_array = np.array(pil_img, dtype=np.float32)
        img_array = preprocess_input(img_array)  # scales to [-1, 1]
        img_array = np.expand_dims(img_array, axis=0)



        disease_model = get_disease_model()


        if not disease_model:

            return jsonify({"error": "Disease model not loaded"}), 500



        preds = disease_model.predict(img_array)



        if preds.shape[1] != len(DISEASE_CLASSES):

            return jsonify({"error": "Model output mismatch"}), 500



        class_idx = int(np.argmax(preds))

        confidence = float(np.max(preds))



        result = DISEASE_CLASSES.get(class_idx, f"Unknown Disease ({class_idx})")



        return jsonify({

            "predicted_class": result,

            "confidence": confidence,

            "class_index": class_idx

        })



    except Exception as e:

        logger.error(f"Disease Prediction Error: {e}")

        return jsonify({"error": str(e)}), 500



# ---------------------------------------------------------

# Test Endpoint

# ---------------------------------------------------------

@app.route("/test", methods=["GET"])

def test():

    from datetime import datetime

    return jsonify({

        "status": "success",

        "message": "Backend connection successful!",

        "backend_url": request.host_url,

        "timestamp": str(datetime.now()),

        "endpoints": {

            "predict_disease": "/predict_disease",

            "predict_yield": "/predict_yield",

            "weather": "/weather",

            "test": "/test"

        }

    })

# ---------------------------------------------------------
# # ---------------------------------------------------------
# Dynamic AI Agent Interface Layer Integration Endpoint
# ---------------------------------------------------------
# ---------------------------------------------------------
# Dynamic AI Agent Interface Layer Integration Endpoint
# ---------------------------------------------------------
@app.route("/api/v1/agent/orchestrate", methods=["POST"])
def delegate_agent_orchestration_loop():
    try:
        from agent_engine.orchestration_core import run_agent

        payload = request.get_json() or {}
        result = run_agent(
            user_message=payload.get("message", ""),
            base64_image=payload.get("image", None),
            language=payload.get("language", "roman_urdu")  # ✅ Language parameter extracted here
        )
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Agent Framework Instance Crashed: {e}")
        return jsonify({
            "agent_response": "Server error. 🌱",
            "metadata": {"status": "error", "detail": str(e)}
        }), 500
# ---------------------------------------------------------
if __name__ == "__main__":

    app.run(host="0.0.0.0", port=5000, debug=True)


# ── Crop Yield V2 (crop_yield_model.pkl) ─────────────────────