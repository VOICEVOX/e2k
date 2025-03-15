# Description: Evaluate the model on the full dataset.
# and calculate the accuracy.
import os
import sys
import torch
import yaml
from config import Config
from evaluator import Evaluator
from train import Model, MyDataset

if len(sys.argv) < 2:
    print("Usage: python eval.py output")
    sys.exit(1)


output_dir = sys.argv[1]

models = [f for f in os.listdir(output_dir) if f.startswith("model-e")]
models.sort(key=lambda x: int(x.split("-")[1][1:-4]))
model = models[-1]
print(f"Using model: {model}")

use_cuda = torch.cuda.is_available()
device = torch.device("cuda" if use_cuda else "cpu")
print(f"Using device: {device}")

if use_cuda:
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.set_float32_matmul_precision("high")
    torch.backends.cudnn.allow_tf32 = True
    torch.backends.cudnn.benchmark = True
    torch.backends.cuda.matmul.allow_tf32 = True


config = Config.from_dict(yaml.safe_load(f"{output_dir}/config.yml"))
model_path = f"{output_dir}/{model}"

model = Model(config)
model.load_state_dict(torch.load(model_path, map_location=device))
model.to(device)
model.eval()

dataset = MyDataset(config.eval_data, device, max_words=None)
dataset.set_return_full(True)  # bleu score test

evaluator = Evaluator(dataset)

print(f"BLEU score: {evaluator.evaluate(model)}")
