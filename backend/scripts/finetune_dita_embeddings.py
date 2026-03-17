"""CLI script to fine-tune DITA embeddings with contrastive loss.

Usage:
  python -m scripts.finetune_dita_embeddings --epochs 3 --output models/dita_embeddings_v1
  python -m scripts.finetune_dita_embeddings --epochs 5 --batch-size 16
"""
import argparse
import sys
from pathlib import Path

backend = Path(__file__).resolve().parent.parent
if str(backend) not in sys.path:
    sys.path.insert(0, str(backend))

from backend.app.training.dita_contrastive_pairs import generate_input_output_pairs


def main():
    parser = argparse.ArgumentParser(description="Fine-tune DITA embedding model")
    parser.add_argument(
        "--epochs",
        type=int,
        default=3,
        help="Number of training epochs",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=16,
        help="Batch size for training",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="models/dita_embeddings_v1",
        help="Output directory for saved model",
    )
    parser.add_argument(
        "--base-model",
        type=str,
        default="all-MiniLM-L6-v2",
        help="Base model to fine-tune",
    )
    parser.add_argument(
        "--seed-path",
        type=str,
        default=None,
        help="Path to dita_spec_seed.json (default: app/storage/dita_spec_seed.json)",
    )
    parser.add_argument(
        "--max-pairs",
        type=int,
        default=None,
        help="Max number of training pairs (default: all)",
    )
    args = parser.parse_args()

    try:
        from sentence_transformers import SentenceTransformer
        from sentence_transformers.losses import MultipleNegativesRankingLoss
        from sentence_transformers import SentenceTransformerTrainer
        from sentence_transformers.training_args import SentenceTransformerTrainingArguments
        from datasets import Dataset
    except ImportError as e:
        print(f"Missing dependency: {e}")
        print("Install: pip install sentence-transformers datasets")
        sys.exit(1)

    seed_path = Path(args.seed_path) if args.seed_path else None
    pairs = generate_input_output_pairs(seed_path=seed_path, max_pairs=args.max_pairs)
    if not pairs:
        print("No training pairs generated. Check dita_spec_seed.json.")
        sys.exit(1)

    anchors = [p[0] for p in pairs]
    positives = [p[1] for p in pairs]
    train_dataset = Dataset.from_dict({"anchor": anchors, "positive": positives})

    print(f"Loaded {len(pairs)} training pairs")
    print(f"Base model: {args.base_model}")
    print(f"Epochs: {args.epochs}, Batch size: {args.batch_size}")

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = backend / "app" / "storage" / output_path
    output_path.mkdir(parents=True, exist_ok=True)

    model = SentenceTransformer(args.base_model)
    loss = MultipleNegativesRankingLoss(model)

    training_args = SentenceTransformerTrainingArguments(
        output_dir=str(output_path),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
    )

    trainer = SentenceTransformerTrainer(
        model=model,
        train_dataset=train_dataset,
        loss=loss,
        args=training_args,
    )
    trainer.train()
    model.save(str(output_path))
    print(f"Model saved to {output_path}")
    print(f"Set DITA_EMBEDDING_MODEL_PATH={output_path} to use the fine-tuned model")


if __name__ == "__main__":
    main()
