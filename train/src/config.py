from dataclasses import dataclass


def migrate(config: dict):
    # num_models_to_keepをnum_last_models_to_keepとnum_best_models_to_keepに分割
    if "num_models_to_keep" in config:
        config["num_last_models_to_keep"] = config["num_models_to_keep"]
        config["num_best_models_to_keep"] = config["num_models_to_keep"]
        del config["num_models_to_keep"]

    if "lr" not in config:
        config["lr"] = 0.9

    return config


@dataclass
class Config:
    train_data: str
    eval_data: str
    eval_max_words: int
    dim: int
    max_epochs: int
    num_last_models_to_keep: int
    num_best_models_to_keep: int
    seed: int
    lr: float

    @classmethod
    def from_dict(cls, config: dict):
        return cls(**migrate(config))
