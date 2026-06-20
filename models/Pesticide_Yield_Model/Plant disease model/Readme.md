🌿 Plant Disease Detection 
Project Overview

This project uses deep learning to automatically detect plant leaf diseases from images.
It is trained on the PlantVillage dataset, which contains 38 classes across various crops (Tomato, Potato, Apple, Corn, etc.).

The model can classify both healthy and diseased leaves, helping farmers and researchers quickly identify plant health issues.

Key Features

Detects 38 types of leaf diseases and healthy leaves.

Uses MobileNetV2 (lightweight and fast) for CPU/GPU training.

Supports random leaf image prediction via Colab.

Provides top-3 predictions with confidence scores for uncertainty handling.

Easily fine-tunable for adding new crops or diseases.

Dataset

Source: PlantVillage Dataset

Structure:

plantvillage/
    PlantVillage/
        train/
            <38 class folders>
        val/
            <38 class folders>


Example classes:

Tomato: Early Blight, Late Blight, Leaf Mold, Septoria Leaf Spot, Bacterial Spot

Apple: Apple Scab, Black Rot, Cedar Apple Rust

Corn: Common Rust, Northern Leaf Blight

…and many more healthy and diseased classes




Install dependencies:

pip install tensorflow matplotlib numpy


Upload your trained model (plant_disease_model_final.keras) to the Colab environment.

Usage (Colab)

Upload a leaf image:

from google.colab import files
uploaded = files.upload()  # Select your leaf image


Predict disease:

from tensorflow.keras.models import load_model
from tensorflow.keras.preprocessing import image
import numpy as np

model = load_model("plant_disease_model_final.keras")
img_path = list(uploaded.keys())[0]

img = image.load_img(img_path, target_size=(128,128))
img_array = image.img_to_array(img)/255.0
img_array = np.expand_dims(img_array, axis=0)

pred = model.predict(img_array)[0]
class_labels = list(train_gen.class_indices.keys())

top3_idx = pred.argsort()[-3:][::-1]
print(f"Top predictions for {img_path}:")
for i in top3_idx:
    print(f"{class_labels[i]} → {pred[i]*100:.2f}% confidence")


Visualize training graphs:

import matplotlib.pyplot as plt

plt.plot(history.history['accuracy'], label='Train Acc')
plt.plot(history.history['val_accuracy'], label='Val Acc')
plt.legend()
plt.show()

Model Architecture

Base Model: MobileNetV2 (pretrained on ImageNet, alpha=0.35)

Custom Layers:

GlobalAveragePooling2D

Dropout (0.3)

Dense output layer (38 classes, softmax)

Optimizer: Adam

Loss: Categorical Crossentropy

Training: EarlyStopping on validation accuracy

Results

Early tests show ~95% validation accuracy after fine-tuning and augmentation.

Misclassifications usually occur between visually similar rust diseases, which can be reduced with further augmentation or fine-tuning.

Future Improvements

Implement Grad-CAM for visual explanations of predictions.

Add more augmentation for underrepresented classes (e.g., Apple Cedar-Apple Rust).

Integrate probability calibration to reduce overconfident predictions.

Deploy as a web or mobile application for real-time leaf disease detection.

References

PlantVillage Dataset

MobileNetV2 Paper

Keras Documentation