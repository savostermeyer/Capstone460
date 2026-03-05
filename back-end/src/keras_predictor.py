from pathlib import Path
import io
import numpy as np
from PIL import Image
import tensorflow as tf
from tensorflow.keras.applications.resnet50 import preprocess_input

# MUST match training order
CLASS_NAMES = ["akiec", "bcc", "bkl", "df", "mel", "nv", "vasc"]

MODEL_PATH = Path(__file__).parent / "models" / "resnet50_skin_disease_finetuned_v4.keras"


class KerasResNetPredictor:
    def __init__(self):
        self.model = tf.keras.models.load_model(MODEL_PATH, compile=False)


    def _preprocess(self, image_bytes: bytes) -> np.ndarray:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img = img.resize((224, 224))

        x = np.array(img, dtype=np.float32)   # 0..255
        x = np.expand_dims(x, axis=0)         # (1,224,224,3)

        x = preprocess_input(x)               # ResNet50 preprocessing

        return x

    def predict_topk(self, image_bytes: bytes, k: int = 3):
        import hashlib

        print("\n--- DEBUG ---")
        print("bytes length:", len(image_bytes))
        print("hash:", hashlib.sha256(image_bytes).hexdigest()[:16])

        x = self._preprocess(image_bytes)
        print("tensor mean:", float(x.mean()))

        preds = self.model.predict(x, verbose=0)[0]
        print("sum preds:", float(np.sum(preds)))

        top_idx = preds.argsort()[-k:][::-1]
        result = [{"label": CLASS_NAMES[i], "prob": float(preds[i])} for i in top_idx]

        print("top3:", result)
        print("-------------\n")

        return result