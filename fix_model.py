import h5py
import json
import numpy as np

model_path = "models/agriculture_disease_model.h5"
fixed_path = "models/agriculture_disease_model_fixed.h5"

import shutil
shutil.copy(model_path, fixed_path)

print("Fixing dtype issues in H5 file...")

def fix_dtype_config(config_str):
    try:
        config = json.loads(config_str)
        config_str_out = json.dumps(config)
        
        # Replace tuple dtype with string
        import re
        # Fix DTypePolicy
        config_str_out = config_str_out.replace(
            '"class_name": "DTypePolicy"',
            '"class_name": "str"'
        )
        return config_str_out
    except:
        return config_str

with h5py.File(fixed_path, 'r+') as f:
    if 'model_config' in f.attrs:
        config_str = f.attrs['model_config']
        if isinstance(config_str, bytes):
            config_str = config_str.decode('utf-8')
        
        config = json.loads(config_str)
        config_str_fixed = json.dumps(config)
        
        # Fix all dtype tuples
        import re
        config_str_fixed = re.sub(
            r'"dtype":\s*\{"module":\s*"keras"[^}]*"DTypePolicy"[^}]*\}',
            '"dtype": "float32"',
            config_str_fixed
        )
        
        f.attrs['model_config'] = config_str_fixed.encode('utf-8')
        print("Config fixed!")

# Ab load karo
import keras
try:
    model = keras.models.load_model(fixed_path, compile=False)
    print("Model loaded successfully!")
    model.save("models/agriculture_disease_model_final.keras")
    print("Saved as agriculture_disease_model_final.keras")
except Exception as e:
    print(f"Error: {e}")