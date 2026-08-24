# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Classification aggregation metrics.

Changes when scoring/aggregation strategies are added or modified.
"""

from collections import Counter


def compute_classification_objectives(items: list[tuple[str, str]]) -> dict[str, float]:
    """Compute precision, recall, F1, and accuracy from expected/predicted label pairs.

    For binary classification, auto-detects the positive class as the less
    frequent expected label (standard convention for imbalanced data).
    For multi-class, computes macro-averaged metrics across all classes.

    Args:
        items: List of (expected, predicted) string pairs.

    Returns:
        Dict with keys: accuracy, precision, recall, f1.
        Returns empty dict if input is empty.

    """
    if not items:
        return {}

    expected_labels, predicted_labels = zip(
        *[(str(e).strip().lower(), str(p).strip().lower()) for e, p in items],
        strict=True,
    )

    accuracy = sum(
        1 for e, p in zip(expected_labels, predicted_labels, strict=True) if e == p
    ) / len(items)

    all_labels = set(expected_labels) | set(predicted_labels)

    if len(all_labels) == 2:
        # Binary classification
        label_counts = Counter(expected_labels)
        pos = min(label_counts, key=lambda k: label_counts.get(k, 0))

        tp = sum(
            1
            for e, p in zip(expected_labels, predicted_labels, strict=True)
            if e == pos and p == pos
        )
        fp = sum(
            1
            for e, p in zip(expected_labels, predicted_labels, strict=True)
            if e != pos and p == pos
        )
        fn = sum(
            1
            for e, p in zip(expected_labels, predicted_labels, strict=True)
            if e == pos and p != pos
        )

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (
            (2 * precision * recall / (precision + recall))
            if (precision + recall) > 0
            else 0.0
        )
    else:
        # Multi-class
        per_class_precision = []
        per_class_recall = []
        per_class_f1 = []

        for label in all_labels:
            tp = sum(
                1
                for e, p in zip(expected_labels, predicted_labels, strict=True)
                if e == label and p == label
            )
            fp = sum(
                1
                for e, p in zip(expected_labels, predicted_labels, strict=True)
                if e != label and p == label
            )
            fn = sum(
                1
                for e, p in zip(expected_labels, predicted_labels, strict=True)
                if e == label and p != label
            )

            p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f = (2 * p * r / (p + r)) if (p + r) > 0 else 0.0

            per_class_precision.append(p)
            per_class_recall.append(r)
            per_class_f1.append(f)

        precision = sum(per_class_precision) / len(per_class_precision)
        recall = sum(per_class_recall) / len(per_class_recall)
        f1 = sum(per_class_f1) / len(per_class_f1)

    return {
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1-score": f1,
    }
