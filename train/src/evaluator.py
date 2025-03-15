from typing import TYPE_CHECKING
import torch
from torcheval.metrics import BLEUScore
from tqdm.auto import tqdm

if TYPE_CHECKING:
    # 循環インポートになるのでTYPE_CHECKINGを使って回避。
    # FIXME: 本来はModelやMyDatasetはtrain.pyではなく他のファイルに定義すべき。
    from train import Model, MyDataset


def tensor2str(t: torch.Tensor):
    return " ".join([str(int(x)) for x in t])


class Evaluator:
    def __init__(self, dataset: "MyDataset"):
        self.dataset = dataset

    def evaluate(self, model: "Model"):
        bleu = BLEUScore(n_gram=3)

        with torch.no_grad():
            for eng, kata in tqdm(self.dataset, desc="Evaluating"):
                res = model.inference(eng)
                pred_kana = tensor2str(res)
                kana = (
                    [[tensor2str(kata)]]
                    if isinstance(kata, torch.Tensor)
                    else [[tensor2str(k) for k in kata]]
                )
                bleu.update(pred_kana, kana)

        return bleu.compute()
