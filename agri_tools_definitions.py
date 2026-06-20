# =========================================================================
# File: agri_tools_definitions.py (CORRECTED)
# =========================================================================
import os, requests, json, base64, io, numpy as np
from langchain.tools import tool
from PIL import Image
from tensorflow.keras.models import load_model
from tensorflow.keras.applications.mobilenet_v2 import preprocess_input
from tensorflow.keras.preprocessing import image

# 1. REMEDIES DICTIONARY (Functions ke bahar)
REMEDY_MAP = {
    "Tomato - Early Blight": "Fungicide (Mancozeb) ka spray karein aur infected pattiyan fori tor kar jala dein. 🌱",
    "Potato - Late Blight": "Metalaxyl ya Copper-based fungicide ka istemal karein, zameen ki nami control rakhein. 🥔",
    "Corn - Common Rust": "Resistant varieties boyein aur field mein hawa ka guzara (ventilation) behtar banayein. 🌽",
    "Healthy Wheat": "Fasal bilkul theek hai! Bas regular monitoring jari rakhein. 🌾"
}

@tool
def micro_climate_weather_fetcher(city: str) -> str:
    """Fetches real-time micro-climate weather details for a specific city in Pakistan."""
    # ... (Aapka existing weather code) ...
    # Make sure your try-except block ends here, get_remedy bahar hona chahiye!

# 2. IMAGE DISEASE ANALYZER (Corrected scope)
@tool
def image_disease_analyzer(image_base64: str) -> str:
    """Analyzes a leaf image, diagnoses disease, and provides a treatment plan."""
    try:
        global disease_model
        if 'disease_model' not in globals():
            model_path = os.path.join(os.path.dirname(__file__), "models", "PlantDoctor_Final_v1.keras")
            disease_model = load_model(model_path)
            
        class_indices = ["Tomato - Early Blight", "Potato - Late Blight", "Corn - Common Rust", "Healthy Wheat"]
        
        # Image processing
        img_data = base64.b64decode(image_base64)
        img = Image.open(io.BytesIO(img_data)).convert('RGB').resize((224, 224))
        x = np.expand_dims(image.img_to_array(img), axis=0)
        x = preprocess_input(x)
        
        preds = disease_model.predict(x)
        idx = np.argmax(preds[0])
        diagnosis = class_indices[idx]
        
        return json.dumps({
            "status": "success", 
            "predicted_class": diagnosis,
            "confidence": f"{float(preds[0][idx]) * 100:.2f}%",
            "remedy": REMEDY_MAP.get(diagnosis, "Expert se consult karein.")
        })
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})

# ... (Baki computational_yield_matrix aur diary_logger niche rakhein)
        
    except Exception as e:
        return json.dumps({"status": "error", "message": f"Vision layer crash: {str(e)}"})@tool
def computational_yield_matrix(area_acres: float, crop_type: str) -> str:
    """Calculates the expected total production yield and optimal seed matrix calculations."""
    try:
        metrics = {"avg_bags_per_acre": 40, "seed_req_kg": 50}
        return json.dumps({
            "crop": crop_type, "total_estimated_yield_bags": metrics["avg_bags_per_acre"] * area_acres,
            "total_seed_required_kg": metrics["seed_req_kg"] * area_acres, "status": "success"
        })
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})

@tool
def autonomous_diary_logger(diary_note: str) -> str:
    """Silently logs a transaction summary or advisory notice inside the local farmer's data file."""
    try:
        file_path = os.path.join(os.path.dirname(__file__), "farmers_data.json")
        diary_records = []
        if os.path.exists(file_path):
            with open(file_path, "r") as f:
                try: diary_records = json.load(f)
                except: diary_records = []
        diary_records.append({"timestamp": "2026-05-19", "log_data": diary_note})
        with open(file_path, "w") as f: json.dump(diary_records, f, indent=4)
        return json.dumps({"status": "committed", "message": "Statement auto-saved to Kisan Diary database."})
    except Exception as e:
        return json.dumps({"status": "failed", "message": str(e)})