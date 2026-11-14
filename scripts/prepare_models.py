"""Prepare local-only full/merged-LoRA artifacts. Never download or publish weights."""

import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--thesis-root", type=Path, required=True)
    parser.add_argument(
        "--base-model",
        type=Path,
        required=True,
        help="Local Gemma snapshot with original weights",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "src" / "models",
    )
    args = parser.parse_args()
    import torch
    from peft import PeftModel
    from transformers import AutoTokenizer, Gemma3TextForSequenceClassification

    full = args.thesis_root / "thesis/experiments/full_finetuning/models/best_model"
    adapter = args.thesis_root / "thesis/experiments/lora/models/best_adapter"
    for path in (
        full / "model.safetensors",
        adapter / "adapter_model.safetensors",
        args.base_model / "model.safetensors",
    ):
        if not path.is_file():
            parser.error(f"Missing local artifact: {path}")
    if args.output.exists():
        parser.error("Output already exists; choose a new output directory")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=".prepare-", dir=args.output.parent))
    try:
        tokenizer = AutoTokenizer.from_pretrained(adapter, local_files_only=True)
        base = Gemma3TextForSequenceClassification.from_pretrained(
            args.base_model,
            local_files_only=True,
            dtype=torch.float32,
            num_labels=5,
            id2label={i: str(i - 2) for i in range(5)},
            label2id={str(i - 2): i for i in range(5)},
            problem_type="single_label_classification",
        )
        base.config.use_cache = False
        model = PeftModel.from_pretrained(base, adapter, local_files_only=True).eval()
        inputs = tokenizer(
            ["今日はとても楽しかった！", "最悪な一日だった", "明日は月曜日です"],
            padding=True,
            return_tensors="pt",
        )
        torch.set_num_threads(2)
        with torch.inference_mode():
            before = model(**inputs).logits.clone()
            merged = model.merge_and_unload().eval()
            after = merged(**inputs).logits
        torch.testing.assert_close(before, after, atol=1e-4, rtol=1e-4)
        if not torch.equal(before.argmax(-1), after.argmax(-1)):
            raise RuntimeError("Merge changed predicted classes")
        merged.save_pretrained(temp / "lora")
        tokenizer.save_pretrained(temp / "lora")
        (temp / "full").mkdir()
        for name in (
            "config.json",
            "model.safetensors",
            "tokenizer.json",
            "tokenizer_config.json",
            "special_tokens_map.json",
            "added_tokens.json",
        ):
            source = full / name
            if source.is_file():
                shutil.copy2(source, temp / "full" / name)
        for method, source in (
            ("lora", adapter / "adapter_model.safetensors"),
            ("full", full / "model.safetensors"),
        ):
            with source.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            manifest = {
                "model_version": digest[:12],
                "source_sha256": digest,
                "method": method,
                "max_tokens": 512,
                "precision": "float32",
            }
            (temp / method / "manifest.json").write_text(
                json.dumps(manifest, indent=2) + "\n"
            )
        temp.rename(args.output)
    except BaseException:
        shutil.rmtree(temp)
        raise
    print(
        f"Prepared {args.output}/lora and {args.output}/full; merge logits verified on 3 examples"
    )


if __name__ == "__main__":
    main()
