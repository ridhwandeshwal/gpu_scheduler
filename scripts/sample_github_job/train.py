"""
Sample GitHub repo workload — CIFAR-10 classifier.

Entrypoint: train.py
Submit via:
  POST /jobs/github
  repo_url: https://github.com/<you>/clusterq-sample-job.git
  repo_branch: main
  entrypoint: train.py
  requested_gpu_count: 1
  requested_memory_mb: 8192
"""

import os
import sys
import json

print("=== CIFAR-10 smoke test ===")
print(f"Python {sys.version}")

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torchvision import datasets, transforms, models
    from torch.utils.data import DataLoader
except ImportError as e:
    sys.exit(f"Missing dependency: {e}")

OUTPUT_DIR = "/outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Device: {device}")
if device.type == "cuda":
    print(f"GPU: {torch.cuda.get_device_name(0)}")

# ── Data ──────────────────────────────────────────────────────────────────────
mean = (0.4914, 0.4822, 0.4465)
std  = (0.2470, 0.2435, 0.2616)

train_transform = transforms.Compose([
    transforms.RandomHorizontalFlip(),
    transforms.RandomCrop(32, padding=4),
    transforms.ToTensor(),
    transforms.Normalize(mean, std),
])
test_transform = transforms.Compose([
    transforms.ToTensor(),
    transforms.Normalize(mean, std),
])

train_ds = datasets.CIFAR10("/tmp/data", train=True,  download=True, transform=train_transform)
test_ds  = datasets.CIFAR10("/tmp/data", train=False, download=True, transform=test_transform)

train_loader = DataLoader(train_ds, batch_size=128, shuffle=True,  num_workers=2, pin_memory=True)
test_loader  = DataLoader(test_ds,  batch_size=256, shuffle=False, num_workers=2, pin_memory=True)

print(f"Train: {len(train_ds)} | Test: {len(test_ds)}")

# ── Model — lightweight ResNet18 ──────────────────────────────────────────────
model = models.resnet18(weights=None)
model.fc = nn.Linear(model.fc.in_features, 10)
model = model.to(device)

optimizer = optim.SGD(model.parameters(), lr=0.1, momentum=0.9, weight_decay=5e-4)
scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=5)
criterion = nn.CrossEntropyLoss()

print(f"Parameters: {sum(p.numel() for p in model.parameters()):,}")

# ── Training loop (5 epochs — enough to verify GPU runs end-to-end) ───────────
EPOCHS = 5
history = []

for epoch in range(1, EPOCHS + 1):
    model.train()
    total_loss, correct, total = 0.0, 0, 0
    for batch_idx, (data, target) in enumerate(train_loader):
        data, target = data.to(device), target.to(device)
        optimizer.zero_grad()
        out = model(data)
        loss = criterion(out, target)
        loss.backward()
        optimizer.step()
        total_loss += loss.item()
        correct += (out.argmax(1) == target).sum().item()
        total += target.size(0)
        if batch_idx % 100 == 0:
            print(f"  [{epoch}/{EPOCHS}] batch {batch_idx} loss={loss.item():.4f}")

    scheduler.step()

    # Eval
    model.eval()
    val_correct, val_total = 0, 0
    with torch.no_grad():
        for data, target in test_loader:
            data, target = data.to(device), target.to(device)
            val_correct += (model(data).argmax(1) == target).sum().item()
            val_total += target.size(0)

    train_acc = 100.0 * correct / total
    val_acc   = 100.0 * val_correct / val_total
    avg_loss  = total_loss / len(train_loader)
    print(f"Epoch {epoch}/{EPOCHS} — loss: {avg_loss:.4f} | train acc: {train_acc:.1f}% | val acc: {val_acc:.1f}%")
    history.append({"epoch": epoch, "loss": avg_loss, "train_acc": train_acc, "val_acc": val_acc})

# ── Save outputs ──────────────────────────────────────────────────────────────
torch.save(model.state_dict(), os.path.join(OUTPUT_DIR, "resnet18_cifar10.pt"))

with open(os.path.join(OUTPUT_DIR, "training_history.json"), "w") as f:
    json.dump(history, f, indent=2)

print(f"Final val accuracy: {history[-1]['val_acc']:.1f}%")
print("Outputs saved to /outputs")
print("=== Done ===")
