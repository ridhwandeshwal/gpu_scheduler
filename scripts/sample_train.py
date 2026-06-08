"""Real PyTorch training script — MNIST digit classifier on GPU.

Trains a small CNN on the MNIST handwritten digit dataset.
Automatically uses GPU if available, otherwise falls back to CPU.

Outputs:
  - training_metrics.csv     (epoch-level metrics)
  - model_checkpoint.pt      (trained PyTorch model)
  - training_summary.json    (final results summary)
  - /outputs/training_summary.json (NAS copy if mounted)
"""

import csv
import json
import os
import time

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.utils.data import DataLoader
from torchvision import datasets, transforms

# ── Configuration ─────────────────────────────────────────

EPOCHS = int(os.environ.get("EPOCHS", "3"))
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "64"))
LEARNING_RATE = float(os.environ.get("LEARNING_RATE", "0.001"))
DATA_DIR = os.environ.get("DATA_DIR", "/outputs/data")

print("=" * 60)
print("  GPU Job Scheduler — MNIST Training")
print("=" * 60)
print()

# ── Device selection ──────────────────────────────────────

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Device:        {device}")
if device.type == "cuda":
    print(f"GPU:           {torch.cuda.get_device_name(0)}")
    print(f"GPU Memory:    {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
print(f"Epochs:        {EPOCHS}")
print(f"Batch Size:    {BATCH_SIZE}")
print(f"Learning Rate: {LEARNING_RATE}")
print()


# ── Model ─────────────────────────────────────────────────

class MNISTNet(nn.Module):
    """Small CNN for MNIST classification."""

    def __init__(self):
        super().__init__()
        self.conv1 = nn.Conv2d(1, 32, 3, padding=1)
        self.conv2 = nn.Conv2d(32, 64, 3, padding=1)
        self.pool = nn.MaxPool2d(2, 2)
        self.dropout1 = nn.Dropout(0.25)
        self.dropout2 = nn.Dropout(0.5)
        self.fc1 = nn.Linear(64 * 7 * 7, 128)
        self.fc2 = nn.Linear(128, 10)

    def forward(self, x):
        x = F.relu(self.conv1(x))
        x = self.pool(x)
        x = F.relu(self.conv2(x))
        x = self.pool(x)
        x = self.dropout1(x)
        x = x.view(-1, 64 * 7 * 7)
        x = F.relu(self.fc1(x))
        x = self.dropout2(x)
        x = self.fc2(x)
        return F.log_softmax(x, dim=1)


# ── Data ──────────────────────────────────────────────────

print("Downloading MNIST dataset...")
transform = transforms.Compose([
    transforms.ToTensor(),
    transforms.Normalize((0.1307,), (0.3081,)),
])

train_dataset = datasets.MNIST(DATA_DIR, train=True, download=True, transform=transform)
test_dataset = datasets.MNIST(DATA_DIR, train=False, download=True, transform=transform)

train_loader = DataLoader(train_dataset, batch_size=BATCH_SIZE, shuffle=True, num_workers=2)
test_loader = DataLoader(test_dataset, batch_size=1000, shuffle=False, num_workers=2)

print(f"Training samples: {len(train_dataset)}")
print(f"Test samples:     {len(test_dataset)}")
print()

# ── Training ──────────────────────────────────────────────

model = MNISTNet().to(device)
optimizer = optim.Adam(model.parameters(), lr=LEARNING_RATE)

total_params = sum(p.numel() for p in model.parameters())
print(f"Model parameters: {total_params:,}")
print()

metrics = []
total_start = time.time()

for epoch in range(1, EPOCHS + 1):
    epoch_start = time.time()

    # Train
    model.train()
    train_loss = 0.0
    correct = 0
    total = 0

    for batch_idx, (data, target) in enumerate(train_loader):
        data, target = data.to(device), target.to(device)
        optimizer.zero_grad()
        output = model(data)
        loss = F.nll_loss(output, target)
        loss.backward()
        optimizer.step()

        train_loss += loss.item() * data.size(0)
        pred = output.argmax(dim=1)
        correct += pred.eq(target).sum().item()
        total += data.size(0)

        if batch_idx % 100 == 0:
            print(f"  Epoch {epoch} [{batch_idx * len(data):>5d}/{len(train_loader.dataset)}] "
                  f"loss: {loss.item():.4f}")

    train_loss /= total
    train_acc = correct / total

    # Evaluate
    model.eval()
    test_loss = 0.0
    correct = 0
    with torch.no_grad():
        for data, target in test_loader:
            data, target = data.to(device), target.to(device)
            output = model(data)
            test_loss += F.nll_loss(output, target, reduction="sum").item()
            pred = output.argmax(dim=1)
            correct += pred.eq(target).sum().item()

    test_loss /= len(test_loader.dataset)
    test_acc = correct / len(test_loader.dataset)

    epoch_time = time.time() - epoch_start

    metric = {
        "epoch": epoch,
        "train_loss": round(train_loss, 4),
        "train_accuracy": round(train_acc, 4),
        "test_loss": round(test_loss, 4),
        "test_accuracy": round(test_acc, 4),
        "epoch_time_s": round(epoch_time, 2),
    }
    metrics.append(metric)

    print(f"\nEpoch {epoch}/{EPOCHS} — "
          f"train_loss: {train_loss:.4f}, train_acc: {train_acc:.4f}, "
          f"test_loss: {test_loss:.4f}, test_acc: {test_acc:.4f} "
          f"({epoch_time:.1f}s)\n")

total_time = time.time() - total_start
print(f"Total training time: {total_time:.1f}s")
print()

# ── Save outputs ──────────────────────────────────────────

# Metrics CSV
metrics_path = "/outputs/training_metrics.csv"
with open(metrics_path, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=list(metrics[0].keys()))
    writer.writeheader()
    writer.writerows(metrics)
print(f"Saved metrics → {metrics_path}")

# Model checkpoint
model_path = "/outputs/model_checkpoint.pt"
torch.save({
    "model_state_dict": model.state_dict(),
    "optimizer_state_dict": optimizer.state_dict(),
    "epoch": EPOCHS,
    "test_accuracy": metrics[-1]["test_accuracy"],
}, model_path)
print(f"Saved model  → {model_path}")

# Summary JSON
summary = {
    "status": "completed",
    "device": str(device),
    "gpu_name": torch.cuda.get_device_name(0) if device.type == "cuda" else None,
    "model_parameters": total_params,
    "epochs": EPOCHS,
    "batch_size": BATCH_SIZE,
    "learning_rate": LEARNING_RATE,
    "final_train_accuracy": metrics[-1]["train_accuracy"],
    "final_test_accuracy": metrics[-1]["test_accuracy"],
    "final_test_loss": metrics[-1]["test_loss"],
    "total_time_seconds": round(total_time, 2),
    "metrics": metrics,
}

summary_path = "/outputs/training_summary.json"
with open(summary_path, "w") as f:
    json.dump(summary, f, indent=2)
print(f"Saved summary → {summary_path}")

# NAS /outputs copy (already saved to /outputs above, but keeping structure)
output_dir = "/outputs"
if os.path.isdir(output_dir):
    print(f"Saved to NAS  → {summary_path}")

print()
print("=" * 60)
print(f"  Training complete! Test accuracy: {metrics[-1]['test_accuracy']:.2%}")
print("=" * 60)
