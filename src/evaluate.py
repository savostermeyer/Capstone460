# src/evaluate.py
import os
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms, models
from PIL import Image
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score
import matplotlib.pyplot as plt
import numpy as np
from sklearn.model_selection import train_test_split

# === Config ===
CSV_PATH = "data/HAM10000_metadata.csv"
IMG_DIR = "data/HAM10000"
MODEL_PATH = "model_weights.pth"
BATCH_SIZE = 32
IMG_SIZE = 224  # Must match training (was 128)
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# === Dataset (must match training) ===
class SkinDataset(Dataset):
    def __init__(self, dataframe, transform=None, label_map=None):
        self.dataframe = dataframe.reset_index(drop=True)
        self.transform = transform
        self.label_map = label_map

    def __len__(self):
        return len(self.dataframe)

    def __getitem__(self, idx):
        row = self.dataframe.iloc[idx]
        img_path = os.path.join(IMG_DIR, row["image_id"] + ".jpg")
        image = Image.open(img_path).convert("RGB")
        if self.transform:
            image = self.transform(image)
        label = self.label_map[row["dx"]]
        return image, label

# === Load CSV and create label map ===
df = pd.read_csv(CSV_PATH)
labels_sorted = sorted(df["dx"].unique())
label_map = {label: idx for idx, label in enumerate(labels_sorted)}
inv_label_map = {v: k for k, v in label_map.items()}

# === Split dataset (same as training) ===
train_df, test_df = train_test_split(df, test_size=0.2, stratify=df["dx"], random_state=42)

# === Transformations (MUST match training) ===
transform = transforms.Compose([
    transforms.Resize((IMG_SIZE, IMG_SIZE)),
    transforms.ToTensor(),
])

# === Dataloader ===
test_dataset = SkinDataset(test_df, transform=transform, label_map=label_map)
test_loader = DataLoader(test_dataset, batch_size=BATCH_SIZE, shuffle=False)

print(f"✅ Test size: {len(test_dataset)} samples")
print(f"✅ Label mapping: {label_map}")

# === Load trained model ===
num_classes = len(labels_sorted)
model = models.efficientnet_b0(pretrained=False)
model.classifier[1] = nn.Linear(model.classifier[1].in_features, num_classes)
model.load_state_dict(torch.load(MODEL_PATH, map_location=DEVICE))
model.to(DEVICE)
model.eval()

# === Evaluate model ===
all_preds = []
all_targets = []

with torch.no_grad():
    for inputs, targets in test_loader:
        inputs, targets = inputs.to(DEVICE), targets.to(DEVICE)
        outputs = model(inputs)
        _, preds = torch.max(outputs, 1)
        all_preds.extend(preds.cpu().numpy())
        all_targets.extend(targets.cpu().numpy())

# === Metrics ===
acc = accuracy_score(all_targets, all_preds)
print(f"\n✅ Overall accuracy: {acc:.4f}\n")

target_names = [inv_label_map[i] for i in range(num_classes)]
report = classification_report(all_targets, all_preds, target_names=target_names, zero_division=0)
print("Classification Report:\n")
print(report)

cm = confusion_matrix(all_targets, all_preds)
print("Confusion Matrix (rows=true, cols=pred):")
print(cm)

# === Plot Confusion Matrix ===
def plot_confusion_matrix(cm, classes, normalize=False, cmap=plt.cm.Blues, out_path="confusion_matrix.png"):
    if normalize:
        cm = cm.astype("float") / cm.sum(axis=1)[:, np.newaxis]
        title = "Normalized Confusion Matrix"
    else:
        title = "Confusion Matrix (Counts)"

    plt.figure(figsize=(10, 8))
    plt.imshow(cm, interpolation="nearest", cmap=cmap)
    plt.title(title)
    plt.colorbar()
    tick_marks = np.arange(len(classes))
    plt.xticks(tick_marks, classes, rotation=45, ha="right")
    plt.yticks(tick_marks, classes)

    fmt = ".2f" if normalize else "d"
    thresh = cm.max() / 2.0
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            plt.text(j, i, format(cm[i, j], fmt),
                     horizontalalignment="center",
                     color="white" if cm[i, j] > thresh else "black")

    plt.ylabel("True label")
    plt.xlabel("Predicted label")
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()
    print(f"✅ Saved {out_path}")

plot_confusion_matrix(cm, target_names, normalize=False, out_path="confusion_matrix_counts.png")
plot_confusion_matrix(cm, target_names, normalize=True, out_path="confusion_matrix_normalized.png")

print("\n🎯 Evaluation complete.")