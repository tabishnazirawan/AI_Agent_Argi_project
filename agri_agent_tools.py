from dotenv import load_dotenv
load_dotenv()  # ← yeh line add karo, imports ke baad

from key_manager import KeyManager
import os, base64, io, json, threading
import numpy as np
from PIL import Image
from langchain.tools import tool
from tensorflow.keras.applications.mobilenet_v2 import preprocess_input
import keras
import requests
from key_manager import KeyManager  # ✅ Already exist karta hai

# ---------------------------------------------------------
# Round Robin Key Managers (keys loaded from environment, comma-separated)
# ---------------------------------------------------------
kindwise_keys = KeyManager([
    k.strip() for k in os.environ.get("KINDWISE_KEYS", "").split(",") if k.strip()
])

gemini_keys = KeyManager([
    k.strip() for k in os.environ.get("GEMINI_KEYS", "").split(",") if k.strip()
])

# ---------------------------------------------------------
# Disease Classes & Remedies (same as before)
# ---------------------------------------------------------
CLASS_INDICES = [
    "Apple - Apple scab", "Apple - Black rot", "Apple - Cedar apple rust", "Apple - Healthy",
    "Blueberry - Healthy", "Cherry - Powdery mildew", "Cherry - Healthy",
    "Corn - Cercospora leaf spot", "Corn - Common rust", "Corn - Northern Leaf Blight", "Corn - Healthy",
    "Grape - Black rot", "Grape - Esca", "Grape - Leaf blight", "Grape - Healthy",
    "Orange - Haunglongbing", "Peach - Bacterial spot", "Peach - Healthy",
    "Pepper - Bacterial spot", "Pepper - Healthy",
    "Potato - Early blight", "Potato - Late blight", "Potato - Healthy",
    "Raspberry - Healthy", "Soybean - Healthy", "Squash - Powdery mildew",
    "Strawberry - Leaf scorch", "Strawberry - Healthy",
    "Tomato - Bacterial spot", "Tomato - Early blight", "Tomato - Late blight",
    "Tomato - Leaf Mold", "Tomato - Septoria leaf spot", "Tomato - Spider mites",
    "Tomato - Target Spot", "Tomato - Yellow Leaf Curl Virus",
    "Tomato - Mosaic Virus", "Tomato - Healthy"
]

REMEDY_MAP = {
    "Potato - Early blight":           "Mancozeb fungicide spray karein, infected pattiyan jala dein. 🌱",
    "Potato - Late blight":            "Metalaxyl ya Copper fungicide istemal karein, nami control rakhein. 🥔",
    "Corn - Common rust":              "Resistant varieties boyein, hawa ka guzara behtar banayein. 🌽",
    "Corn - Northern Leaf Blight":     "Resistant variety choosein, Propiconazole spray karein. 🌽",
    "Tomato - Early blight":           "Chlorothalonil spray karein, zameen se pattiyan door rakhein. 🍅",
    "Tomato - Late blight":            "Copper-based fungicide lagayein, barish mein spray band karein. 🍅",
    "Tomato - Bacterial spot":         "Copper spray karein, upar se paani dena band karein. 🍅",
    "Tomato - Leaf Mold":              "Ventilation behtar karein, Mancozeb spray karein. 🍅",
    "Tomato - Septoria leaf spot":     "Fungicide spray karein, infected pattiyan hata dein. 🍅",
    "Tomato - Spider mites":           "Miticide spray karein, paani se pattiyan saaf karein. 🕷️",
    "Tomato - Yellow Leaf Curl Virus": "White fly control karein, infected plants hata dein. 🍅",
    "Apple - Apple scab":              "Captan ya Mancozeb spray karein, giri pattiyan jala dein. 🍎",
    "Apple - Black rot":               "Infected hissay kaat dein, Captan fungicide lagayein. 🍎",
    "Grape - Black rot":               "Mancozeb spray karein, infected angoor hata dein. 🍇",
    "Cherry - Powdery mildew":         "Sulfur-based fungicide spray karein, hawa ka intezaam karein. 🍒",
}

# ---------------------------------------------------------
# Local Model (lazy load)
# ---------------------------------------------------------
disease_model = None

def load_local_model():
    global disease_model
    if disease_model is None:
        model_path = os.path.join(os.path.dirname(__file__), "models", "PlantDoctor_Final_v1.keras")
        disease_model = keras.models.load_model(model_path, compile=False)
    return disease_model

# ---------------------------------------------------------
# Fallback Layer 1 — Local Model
# ---------------------------------------------------------
def try_local_model(clean_b64: str) -> dict | None:
    try:
        model = load_local_model()
        img_data = base64.b64decode(clean_b64)
        img = Image.open(io.BytesIO(img_data)).convert('RGB').resize((224, 224))
        img_array = np.expand_dims(preprocess_input(np.array(img, dtype=np.float32)), axis=0)

        preds = model.predict(img_array)
        idx = int(np.argmax(preds[0]))
        confidence = float(preds[0][idx])

        if confidence < 0.75:  # Low confidence → next fallback
            print(f"⚠️ Local model low confidence: {confidence:.2f} → trying Kindwise")
            return None

        classes = CLASS_INDICES[:preds.shape[1]]
        diagnosis = classes[idx] if idx < len(classes) else "Unknown"
        return {
            "predicted_class": diagnosis,
            "confidence": f"{confidence * 100:.1f}%",
            "remedy": REMEDY_MAP.get(diagnosis, "Agri-expert se consult karein. 🌿"),
            "source": "local_model"
        }
    except Exception as e:
        print(f"❌ Local model failed: {e}")
        return None

# ---------------------------------------------------------
# Fallback Layer 2 — Kindwise Round Robin
# ---------------------------------------------------------
def try_kindwise(clean_b64: str) -> dict | None:
    for attempt in range(kindwise_keys._keys.__len__()):
        key = kindwise_keys.get_key()
        try:
            res = requests.post(
                "https://crop.kindwise.com/api/v1/identification",
                headers={"Api-Key": key, "Content-Type": "application/json"},
                json={"images": [clean_b64], "similar_images": False},
                timeout=15
            )

            if res.status_code == 429:
                print(f"⚠️ Kindwise key rate limited, rotating...")
                continue

            data = res.json()
            suggestions = data.get("result", {}).get("disease", {}).get("suggestions", [])

            if not suggestions:
                return None

            top = suggestions[0]
            diagnosis = top.get("name", "Unknown")
            confidence = float(top.get("probability", 0))
            return {
                "predicted_class": diagnosis,
                "confidence": f"{confidence * 100:.1f}%",
                "remedy": REMEDY_MAP.get(diagnosis, "Agri-expert se consult karein. 🌿"),
                "source": "kindwise_api"
            }
        except Exception as e:
            print(f"❌ Kindwise attempt {attempt + 1} failed: {e}")
            continue

    print("❌ All Kindwise keys failed → trying Gemini")
    return None

# ---------------------------------------------------------
# Fallback Layer 3 — Gemini Round Robin
# ---------------------------------------------------------
def try_gemini(clean_b64: str) -> dict | None:
    prompt = (
        "You are a plant disease expert. Analyze this leaf image carefully. "
        "Respond ONLY in this exact JSON format, nothing else:\n"
        '{"disease": "disease name here", "confidence": "85%", "treatment": "treatment steps here"}'
    )

    for attempt in range(gemini_keys._keys.__len__()):
        key = gemini_keys.get_key()
        try:
            res = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={key}",
                json={"contents": [{"parts": [
                    {"inline_data": {"mime_type": "image/jpeg", "data": clean_b64}},
                    {"text": prompt}
                ]}]},
                timeout=20
            )

            if res.status_code == 429:
                print(f"⚠️ Gemini key rate limited, rotating...")
                continue

            raw_text = res.json()["candidates"][0]["content"]["parts"][0]["text"]
            clean_text = raw_text.strip().replace("```json", "").replace("```", "").strip()
            parsed = json.loads(clean_text)

            diagnosis = parsed.get("disease", "Unknown")
            return {
                "predicted_class": diagnosis,
                "confidence": parsed.get("confidence", "N/A"),
                "remedy": parsed.get("treatment", REMEDY_MAP.get(diagnosis, "Agri-expert se consult karein. 🌿")),
                "source": "gemini_api"
            }
        except Exception as e:
            print(f"❌ Gemini attempt {attempt + 1} failed: {e}")
            continue

    print("❌ All Gemini keys also failed")
    return None

# ---------------------------------------------------------
# Main Tool — Fallback Chain
# ---------------------------------------------------------
disease_model_instance = None

@tool
def image_disease_analyzer(image_base64: str) -> str:
    """Analyzes a leaf image, diagnoses disease, and provides a treatment plan."""
    try:
        clean_b64 = image_base64.split("base64,")[-1].strip()

        result = (
            try_local_model(clean_b64) or
            try_kindwise(clean_b64)    or
            try_gemini(clean_b64)
        )

        if not result:
            return json.dumps({
                "status": "error",
                "message": "Tasveer analyze nahi ho saki. Saaf tasveer bhejein. 📸"
            })

        print(f"✅ Detection source: {result['source']}")
        return json.dumps({
            "status": "success",
            "predicted_class": result["predicted_class"],
            "confidence": result["confidence"],
            "remedy": result["remedy"],
            "source": result["source"]
        })

    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


@tool
def micro_climate_weather_fetcher(city: str) -> str:
    """Fetches real-time weather for a city in Pakistan."""
    try:
        geo = requests.get(
            f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1",
            timeout=10
        ).json()
        if not geo.get("results"):
            return json.dumps({"status": "error", "message": "City not found"})

        lat = geo["results"][0]["latitude"]
        lon = geo["results"][0]["longitude"]
        city_name = geo["results"][0]["name"]

        weather = requests.get(
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true",
            timeout=10
        ).json()
        current = weather["current_weather"]

        return json.dumps({
            "status": "success",
            "city": city_name,
            "temperature": f"{current['temperature']}°C",
            "windspeed": f"{current['windspeed']} km/h",
            "condition": "Saaf" if current["weathercode"] <= 3 else "Baadal"
        })
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


@tool
def computational_yield_matrix(area_acres: float, crop_type: str) -> str:
    """Calculates expected yield and seed requirements."""
    try:
        return json.dumps({
            "status": "success",
            "crop": crop_type,
            "total_estimated_yield_bags": 40 * area_acres,
            "total_seed_required_kg": 50 * area_acres
        })
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


@tool
def autonomous_diary_logger(diary_note: str) -> str:
    """Logs a transaction summary to the farmer's diary."""
    try:
        from datetime import datetime
        file_path = os.path.join(os.path.dirname(__file__), "farmers_data.json")
        records = []
        if os.path.exists(file_path):
            with open(file_path, "r") as f:
                try:
                    records = json.load(f)
                except:
                    records = []
        records.append({"timestamp": datetime.now().isoformat(), "log_data": diary_note})
        with open(file_path, "w") as f:
            json.dump(records, f, indent=4)
        return json.dumps({"status": "committed"})
    except Exception as e:
        return json.dumps({"status": "failed", "message": str(e)})