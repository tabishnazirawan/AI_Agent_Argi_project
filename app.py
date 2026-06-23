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

# Weather API - IMPROVED VERSION

# ---------------------------------------------------------

@app.route("/weather", methods=["GET"])

def get_weather():

    city = request.args.get("city")

    if not city:

        return jsonify({"error": "City required"}), 400



    try:

        # Get coordinates for the city

        geo_response = requests.get(

            f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1",

            timeout=10

        ).json()

        

        if not geo_response.get("results"):

            return jsonify({"error": "City not found"}), 404



        lat = geo_response["results"][0]["latitude"]

        lon = geo_response["results"][0]["longitude"]

        found_city = geo_response["results"][0]["name"]

        region = geo_response["results"][0].get("admin1", "")

        country = geo_response["results"][0].get("country", "")



        # Get current weather AND forecast (3 days)

        weather_response = requests.get(

            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,wind_speed_10m,weather_code,is_day,wind_direction_10m&daily=temperature_2m_max,temperature_2m_min,weather_code&timezone=auto&forecast_days=3",

            timeout=10

        ).json()



        if "current" not in weather_response:

            return jsonify({"error": "Weather data not available"}), 500



        current = weather_response["current"]

        daily = weather_response.get("daily", {})

        

        # Get weather condition name from weather_code

        weathercode = int(current["weather_code"])

        condition_name = get_weather_condition(weathercode)

        

        # Since Open-Meteo doesn't provide humidity in free API, we'll simulate it

        # based on temperature and weather conditions

        humidity = simulate_humidity(weathercode, current["temperature_2m"])

        

        return jsonify({

            "city": found_city,

            "region": region,

            "country": country,

            "temperature": current["temperature_2m"],

            "feels_like": current["temperature_2m"],  # Same as temp for simplicity

            "humidity": humidity,

            "windspeed": current["wind_speed_10m"],

            "wind_direction": get_wind_direction(current.get("wind_direction_10m", 0)),

            "weathercode": weathercode,

            "condition": condition_name,

            "last_updated": "Now",

            "is_day": current.get("is_day", 1),

            "cloud": get_cloud_cover(weathercode),

            "pressure_mb": 1013,  # Default value

            "precip_mm": 0,  # Default value

            "uv": 5,  # Default value

            "forecast": get_forecast_data(daily) if daily else []

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

    """Convert WMO weather code to human-readable condition"""

    # WMO Weather interpretation codes (WW)

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

    """Estimate cloud cover percentage from weathercode"""

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

    """Simulate humidity based on weather conditions and temperature"""

    base_humidity = 50

    

    # Adjust based on weather

    if weathercode in [45, 48, 51, 53, 55, 61, 63, 65, 80, 81, 82]:

        base_humidity = 85  # Higher for rain/fog

    elif weathercode in [0, 1]:

        base_humidity = 30  # Lower for clear skies

    

    # Adjust based on temperature

    if temperature > 30:

        base_humidity -= 10

    elif temperature < 10:

        base_humidity += 15

    

    # Keep within reasonable bounds

    return max(20, min(base_humidity, 100))



def get_forecast_data(daily):

    """Extract forecast data from daily forecast"""

    if not daily or "time" not in daily:

        return []

    

    forecast = []

    for i in range(min(3, len(daily["time"]))):  # Get next 3 days

        day_name = get_day_name(i)

        forecast.append({

            "day": day_name,

            "max_temp": daily["temperature_2m_max"][i],

            "min_temp": daily["temperature_2m_min"][i],

            "weathercode": daily["weather_code"][i],

            "condition": get_weather_condition(daily["weather_code"][i])

        })

    

    return forecast



def get_day_name(offset):

    """Get day name for forecast"""

    from datetime import datetime, timedelta

    days = ["Aaj", "Kal", "Parsun"]

    if offset < len(days):

        return days[offset]

    

    # Fallback to actual day names

    target_date = datetime.now() + timedelta(days=offset)

    return target_date.strftime("%a")



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

    """Helper function to get weather for a specific city"""

    try:

        # Same logic as /weather endpoint but for a specific city

        geo_response = requests.get(

            f"https://geocoding-api.open-meteo.com/v1/search?name={city_name}&count=1",

            timeout=10

        ).json()

        

        if not geo_response.get("results"):

            return jsonify({"error": "City not found"}), 404



        lat = geo_response["results"][0]["latitude"]

        lon = geo_response["results"][0]["longitude"]

        found_city = geo_response["results"][0]["name"]



        weather_response = requests.get(

            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,wind_speed_10m,weather_code&timezone=auto",

            timeout=10

        ).json()



        current = weather_response["current"]

        weathercode = int(current["weather_code"])

        condition_name = get_weather_condition(weathercode)

        humidity = simulate_humidity(weathercode, current["temperature_2m"])

        

        return jsonify({

            "city": found_city,

            "temperature": current["temperature_2m"],

            "windspeed": current["wind_speed_10m"],

            "weathercode": weathercode,

            "condition": condition_name,

            "humidity": humidity

        })

        

    except Exception as e:

        return jsonify({"error": str(e)}), 500



# ---------------------------------------------------------

# Weather Forecast Endpoint (3-day forecast)

# ---------------------------------------------------------

@app.route("/forecast", methods=["GET"])

def get_forecast():

    """Get 3-day weather forecast"""

    city = request.args.get("city")

    if not city:

        return jsonify({"error": "City required"}), 400



    try:

        geo_response = requests.get(

            f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1",

            timeout=10

        ).json()

        

        if not geo_response.get("results"):

            return jsonify({"error": "City not found"}), 404



        lat = geo_response["results"][0]["latitude"]

        lon = geo_response["results"][0]["longitude"]

        found_city = geo_response["results"][0]["name"]



        weather_response = requests.get(

            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max,temperature_2m_min,weather_code,precipitation_sum&timezone=auto&forecast_days=3",

            timeout=10

        ).json()



        daily = weather_response.get("daily", {})

        forecast_data = []

        

        for i in range(min(3, len(daily.get("time", [])))):

            forecast_data.append({

                "date": daily["time"][i],

                "max_temp": daily["temperature_2m_max"][i],

                "min_temp": daily["temperature_2m_min"][i],

                "weathercode": daily["weather_code"][i],

                "condition": get_weather_condition(daily["weather_code"][i]),

                "precipitation": daily.get("precipitation_sum", [0, 0, 0])[i]

            })

        

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