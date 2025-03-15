from dataclasses import dataclass


@dataclass
class Config:
    train_data: str
    eval_data: str
    eval_max_words: int
    dim: int
    max_epochs: int
    num_models_to_keep: int
    seed: int

    @classmethod
    def from_dict(cls, config: dict):
        return cls(**config)
