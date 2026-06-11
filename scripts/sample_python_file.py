"""
Sample workload — standalone Python file submission.

Downloads MNIST, trains a tiny CNN for 3 epochs, prints accuracy,
saves a checkpoint to /outputs.

Submit via:
  POST /jobs/python-file
  file=this file, metadata={"title":"MNIST smoke test","requested_gpu_count":1,"requested_memory_mb":4096}
"""

import os
import sys

print("=== MNIST smoke test ===")
print(f"Python {sys.version}")

# ── Deps check ────────────────────────────────────────────────────────────────
try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torchvision import datasets, transforms
    from torch.utils.data import DataLoader
except ImportError as e:
    sys.exit(f"Missing dependency: {e}. Make sure the container image has torchvision.")

OUTPUT_DIR = "/outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Device ────────────────────────────────────────────────────────────────────
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Device: {device}")
if device.type == "cuda":
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")

# ── Data ──────────────────────────────────────────────────────────────────────
transform = transforms.Compose([transforms.ToTensor(), transforms.Normalize((0.1307,), (0.3081,))])

# /tmp is writable in the container (tmpfs)
train_ds = datasets.MNIST("/tmp/data", train=True,  download=True, transform=transform)
test_ds  = datasets.MNIST("/tmp/data", train=False, download=True, transform=transform)

train_loader = DataLoader(train_ds, batch_size=256, shuffle=True,  num_workers=2)
test_loader  = DataLoader(test_ds,  batch_size=512, shuffle=False, num_workers=2)

print(f"Train: {len(train_ds)} samples | Test: {len(test_ds)} samples")

# ── Model ─────────────────────────────────────────────────────────────────────
class SmallCNN(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(1, 32, 3, padding=1), nn.ReLU(),
            nn.Conv2d(32, 64, 3, padding=1), nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Flatten(),
            nn.Linear(64 * 14 * 14, 128), nn.ReLU(),
            nn.Linear(128, 10),
        )
    def forward(self, x):
        return self.net(x)

model = SmallCNN().to(device)
optimizer = optim.Adam(model.parameters(), lr=1e-3)
criterion = nn.CrossEntropyLoss()

total_params = sum(p.numel() for p in model.parameters())
print(f"Parameters: {total_params:,}")

# ── Training ──────────────────────────────────────────────────────────────────
EPOCHS = 3

for epoch in range(1, EPOCHS + 1):
    model.train()
    total_loss = 0.0
    for batch_idx, (data, target) in enumerate(train_loader):
        data, target = data.to(device), target.to(device)
        optimizer.zero_grad()
        loss = criterion(model(data), target)
        loss.backward()
        optimizer.step()
        total_loss += loss.item()
        if batch_idx % 50 == 0:
            print(f"  Epoch {epoch} [{batch_idx * len(data)}/{len(train_ds)}] loss: {loss.item():.4f}")

    # Validation
    model.eval()
    correct = 0
    with torch.no_grad():
        for data, target in test_loader:
            data, target = data.to(device), target.to(device)
            correct += (model(data).argmax(dim=1) == target).sum().item()

    acc = 100.0 * correct / len(test_ds)
    print(f"Epoch {epoch} complete — avg loss: {total_loss / len(train_loader):.4f} | test acc: {acc:.2f}%")

# ── Save checkpoint ───────────────────────────────────────────────────────────
ckpt_path = os.path.join(OUTPUT_DIR, "mnist_cnn.pt")
torch.save({
    "epoch": EPOCHS,
    "model_state_dict": model.state_dict(),
    "optimizer_state_dict": optimizer.state_dict(),
}, ckpt_path)
print(f"Checkpoint saved to {ckpt_path}")
print("=== Done ===")
