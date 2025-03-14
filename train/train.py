# we train a s2s model to predict the katakana phonemes from
# English phonemes
import json
import argparse
from functools import partial
from os import path
from random import randint

import torch
from torch import nn
from torch.utils.data import random_split, Dataset, DataLoader
from torch.nn.utils.rnn import pad_sequence
from torch.optim.lr_scheduler import ExponentialLR
from torch.utils.tensorboard import SummaryWriter
from tqdm.auto import tqdm

from g2p_en import G2p

from constants import kanas, en_phones, ascii_entries, PAD_IDX, SOS_IDX, EOS_IDX


SEED = 3407
DIM = 256


class Model(nn.Module):
    def __init__(self, p2k: bool = False):
        super(Model, self).__init__()
        if p2k:
            self.e_emb = nn.Embedding(len(en_phones), DIM)
        else:
            self.e_emb = nn.Embedding(len(ascii_entries), DIM)
        self.k_emb = nn.Embedding(len(kanas), DIM)
        self.encoder = nn.GRU(DIM, DIM, batch_first=True, bidirectional=True)
        self.encoder_fc = nn.Sequential(
            nn.Linear(2 * DIM, DIM),
            nn.Tanh(),
        )
        self.pre_decoder = nn.GRU(DIM, DIM, batch_first=True)
        self.post_decoder = nn.GRU(2 * DIM, DIM, batch_first=True)
        self.attn = nn.MultiheadAttention(DIM, 4, batch_first=True, dropout=0.1)
        self.fc = nn.Linear(DIM, len(kanas))

    def forward(self, src, tgt, src_mask=None, tgt_mask=None):
        """
        src: [B, Ts]
        tgt: [B, Tt]
        src_mask: [B, Ts]
        tgt_mask: [B, Tt]
        """
        e_emb = self.e_emb(src)
        k_emb = self.k_emb(tgt)
        k_emb = k_emb[:, :-1]
        enc_out, _ = self.encoder(e_emb)
        enc_out = self.encoder_fc(enc_out)
        dec_out, _ = self.pre_decoder(k_emb)
        attn_out, _ = self.attn.forward(
            dec_out, enc_out, enc_out, key_padding_mask=~src_mask
        )
        x = torch.cat([dec_out, attn_out], dim=-1)
        x, _ = self.post_decoder(x)
        x = self.fc(x)
        return x

    def inference(self, src):
        # Assume both src and tgt are unbatched
        sos_idx = SOS_IDX
        eos_idx = EOS_IDX
        src = src.unsqueeze(0)
        src_emb = self.e_emb(src)
        enc_out, _ = self.encoder(src_emb)
        enc_out = self.encoder_fc(enc_out)
        res = [sos_idx]
        h1 = None
        h2 = None
        count = 0
        while res[-1] != eos_idx and count < 16:
            dec = torch.tensor([res[-1]]).unsqueeze(0).to(src.device)
            dec_emb = self.k_emb(dec)
            dec_out, h1 = self.pre_decoder(dec_emb, h1)
            attn_out, _ = self.attn(dec_out, enc_out, enc_out)
            x = torch.cat([dec_out, attn_out], dim=-1)
            x, h2 = self.post_decoder(x, h2)
            x = self.fc(x)
            idx = torch.argmax(x, dim=-1)
            res.append(idx.cpu().item())
            count += 1
        return res


class MyDataset(Dataset):
    def __init__(self, path, device, p2k: bool = True):
        """
        reads a json line file
        """
        super().__init__()
        self.g2p = G2p()
        with open(path, "r") as file:
            lines = file.readlines()
        self.data = [json.loads(line) for line in lines]
        self.device = device
        self.eng_dict = {c: i for i, c in enumerate(en_phones)}
        self.c_dict = {c: i for i, c in enumerate(ascii_entries)}
        self.kata_dict = {c: i for i, c in enumerate(kanas)}
        self.pad_idx = PAD_IDX
        self.sos_idx = SOS_IDX
        self.eos_idx = EOS_IDX
        self.cache_en = {}
        self.cache_kata = {}
        self.p2k_flag = p2k
        self.return_full = False

    def __len__(self):
        return len(self.data)

    def p2k(self, eng):
        phonemes = self.g2p(eng)
        # phonemes = [p[:-1] if p[-1] in "012" else p for p in phonemes]
        phonemes = list(filter(lambda x: x in self.eng_dict, phonemes))
        eng = [self.eng_dict[c] for c in phonemes]
        return eng

    def c2k(self, eng):
        eng = [self.c_dict[c] for c in eng]
        return eng

    def set_return_full(self, flag: bool):
        """
        Returns the full dataset, it's for bleu score calculation
        """
        self.return_full = flag

    def __getitem__(self, idx):
        if idx in self.cache_en:
            return self.cache_en[idx], self.cache_kata[idx]
        item = self.data[idx]
        eng = item["word"]
        katas = item["kata"]
        if self.p2k_flag:
            eng = self.p2k(eng)
        else:
            eng = self.c2k(eng)
        eng = [self.sos_idx] + eng + [self.eos_idx]
        # katas is a list of katakana words
        # if not return_full, we randomly select one of them
        # else we return all of them
        if not self.return_full:
            kata = katas[randint(0, len(katas) - 1)]
            kata = [self.kata_dict[c] for c in kata]
            kata = [self.sos_idx] + kata + [self.eos_idx]
            en = torch.tensor(eng).to(self.device)
            kana = torch.tensor(kata).to(self.device)
            self.cache_en[idx] = en
            self.cache_kata[idx] = kana
            return en, kana
        else:
            kata = []
            for k in katas:
                k = [self.kata_dict[c] for c in k]
                k = [self.sos_idx] + k + [self.eos_idx]
                kata.append(torch.tensor(k).to(self.device))
            en = torch.tensor(eng).to(self.device)
            self.cache_en[idx] = en
            self.cache_kata[idx] = kata
            return en, kata


def lens2mask(lens, max_len):
    mask = torch.zeros(len(lens), max_len).bool()
    for i, le in enumerate(lens):
        mask[i, :le] = True
    return mask


def collate_fn(batch, device):
    engs = [x[0] for x in batch]
    katas = [x[1] for x in batch]
    eng_lens = [len(x) for x in engs]
    kata_lens = [len(x) for x in katas]
    eng_mask = lens2mask(eng_lens, max(eng_lens))
    kata_mask = lens2mask(kata_lens, max(kata_lens))
    engs = pad_sequence(engs, batch_first=True, padding_value=0)
    katas = pad_sequence(katas, batch_first=True, padding_value=0)
    engs, katas, eng_mask, kata_mask = [
        x.to(device) for x in [engs, katas, eng_mask, kata_mask]
    ]
    return engs, katas, eng_mask, kata_mask


def infer(src, model, p2k):
    model = model.eval()
    res = model.inference(src)
    # return to words
    res = [kanas[i] for i in res]
    # also for english phonemes
    if p2k:
        src = [en_phones[i] for i in src]
    else:
        src = [ascii_entries[i] for i in src]
    return src, res


def train():
    torch.manual_seed(SEED)
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=str, default="./vendor/data.jsonl")
    parser.add_argument("--p2k", action="store_true")
    parser.add_argument("--batch_size", type=int)
    args = parser.parse_args()

    print(f"Training {'p2k' if args.p2k else 'c2k'}")

    use_cuda = torch.cuda.is_available()
    device = torch.device("cuda" if use_cuda else "cpu")
    print(f"Using device: {device}")

    if use_cuda:
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.set_float32_matmul_precision("high")
        torch.backends.cudnn.allow_tf32 = True
        torch.backends.cudnn.benchmark = True
        torch.backends.cuda.matmul.allow_tf32 = True

    model = Model(p2k=args.p2k).to(device)
    dataset = MyDataset(args.data, device, p2k=args.p2k)
    train_ds, val_ds = random_split(dataset, [0.95, 0.05])

    batch_size = args.batch_size or (256 if use_cuda else 64)
    print(f"Batch size: {batch_size}")

    train_dl = DataLoader(
        train_ds,
        batch_size=batch_size,
        shuffle=True,
        collate_fn=partial(collate_fn, device=device),
    )
    val_dl = DataLoader(
        val_ds,
        batch_size=batch_size,
        shuffle=True,
        collate_fn=partial(collate_fn, device=device),
    )

    criterion = nn.CrossEntropyLoss(ignore_index=0)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    scheduler = ExponentialLR(optimizer, 0.8)
    writer = SummaryWriter()
    epochs = 10
    steps = 0
    for epoch in range(1, epochs + 1):
        model.train()
        for eng, kata, e_mask, k_mask in tqdm(train_dl, desc=f"Epoch {epoch} train"):
            optimizer.zero_grad()
            out = model(eng, kata, e_mask, k_mask)
            loss = criterion(out.transpose(1, 2), kata[:, 1:])
            writer.add_scalar("Loss/train", loss.item(), steps)
            loss.backward()
            optimizer.step()
            steps += 1
        model.eval()
        total_loss = 0
        count = 0
        with torch.no_grad():
            for eng, kata, e_mask, k_mask in tqdm(val_dl, desc=f"Epoch {epoch} val"):
                out = model(eng, kata, e_mask, k_mask)
                loss = criterion(out.transpose(1, 2), kata[:, 1:])
                total_loss += loss.item()
                count += 1
        # take a sample and inference it
        sample = val_ds[randint(0, len(val_ds) - 1)]
        src, tgt = sample
        src, pred = infer(src, model, args.p2k)
        print(f"Epoch {epoch} Sample: {src} -> {pred}")
        writer.add_scalar("Loss/val", total_loss / count, epoch)
        print(f"Epoch {epoch} Loss: {total_loss / count}")
        scheduler.step()
        name = "p2k" if args.p2k else "c2k"
    else:
        torch.save(
            model.state_dict(),
            path.join("vendor", f"model-{name}-e{epoch}.pth"),
        )


if __name__ == "__main__":
    train()
