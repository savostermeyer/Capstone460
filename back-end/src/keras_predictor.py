from pathlib import Path
import io
import numpy as np
from PIL import Image
import tensorflow as tf

# MUST match training order
CLASS_NAMES = ["akiec", "bcc", "bkl", "df", "mel", "nv", "vasc"]

MODEL_PATH = Path(__file__).parent / "models" / "resnet50_skin_disease_finetuned.keras"

class KerasResNetPredictor:
    def __init__(self):
        self.model = tf.keras.models.load_model(MODEL_PATH, compile=False)

    def _preprocess(self, image_bytes: bytes) -> np.ndarray:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img = img.resize((224, 224))
        x = np.array(img) / 255.0
        x = np.expand_dims(x, axis=0)
        return x

    def predict_topk(self, image_bytes: bytes, k: int = 3):
        x = self._preprocess(image_bytes)
        preds = self.model.predict(x)[0]

        top_idx = preds.argsort()[-k:][::-1]
        return [
            {"label": CLASS_NAMES[i], "prob": float(preds[i])}
            for i in top_idx
        ]