"""Compare screening output with synthetic ground truth.

Metrics are calculated from the two inputs. They are not operational accuracy
and they are not evidence of real-world fraud detection performance.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.domain import RULES
from src.utils.frames import PRIMARY_KEYS


def _ids(frame: pd.DataFrame, column: str) -> set[str]:
    if frame.empty or column not in frame.columns:
        return set()
    return {str(value) for value in frame[column].dropna() if str(value) not in {"", "nan"}}


def confusion(positives: set[str], predicted: set[str], universe: set[str]) -> dict[str, float | int | None]:
    positives = positives & universe
    predicted = predicted & universe
    true_positive = positives & predicted
    false_positive = predicted - positives
    false_negative = positives - predicted
    true_negative = universe - positives - predicted
    precision = _rate(len(true_positive), len(true_positive) + len(false_positive))
    recall = _rate(len(true_positive), len(true_positive) + len(false_negative))
    false_positive_rate = _rate(len(false_positive), len(false_positive) + len(true_negative))
    if precision is None or recall is None or (precision + recall) == 0:
        f1 = None
    else:
        f1 = 2 * precision * recall / (precision + recall)
    return {
        "universe": len(universe),
        "positives": len(positives),
        "predicted": len(predicted),
        "true_positives": len(true_positive),
        "false_positives": len(false_positive),
        "true_negatives": len(true_negative),
        "false_negatives": len(false_negative),
        "precision": precision,
        "recall": recall,
        "f1_score": f1,
        "false_positive_rate": false_positive_rate,
    }


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def evaluate_rules(
    alerts: pd.DataFrame,
    labels: pd.DataFrame,
    tables: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """Score each rule on its own entity population.

    A labeled benign control is a negative. An unlabeled operational record is
    also a negative, because the generator did not plant that pattern on it.
    """
    rows = []
    population_keys = {
        "invoice": ("invoices", "invoice_id"),
        "purchase_order": ("purchase_orders", "po_id"),
        "payment": ("payments", "payment_id"),
        "employee_expense": ("employee_expenses", "expense_id"),
        "approval_record": ("approval_records", "approval_id"),
        "vendor": ("vendors", "vendor_id"),
        "employee": ("employees", "employee_id"),
    }
    for rule_code, rule in RULES.items():
        table_name, key = population_keys[rule["entity_type"]]
        universe = _ids(tables[table_name].drop_duplicates(key), key)
        rule_labels = labels[
            (labels["entity_type"] == rule["entity_type"])
            & (labels["pattern_code"].isin(rule["positive_patterns"]))
            & (labels["is_suspicious"].astype(bool))
        ]
        positives = _ids(rule_labels, "entity_id") & universe
        predicted = _ids(alerts[alerts["rule_code"] == rule_code], "entity_id") if not alerts.empty else set()
        metrics = confusion(positives, predicted, universe)
        benign_related = labels[
            (labels["entity_type"] == rule["entity_type"])
            & (labels["is_benign_control"].astype(bool))
        ]
        benign_ids = _ids(benign_related, "entity_id") & universe
        metrics.update(
            {
                "rule_code": rule_code,
                "rule_name": rule["name"],
                "entity_type": rule["entity_type"],
                "benign_controls_in_population": len(benign_ids),
                "benign_controls_flagged": len(benign_ids & predicted),
            }
        )
        rows.append(metrics)
    columns = [
        "rule_code",
        "rule_name",
        "entity_type",
        "universe",
        "positives",
        "predicted",
        "true_positives",
        "false_positives",
        "true_negatives",
        "false_negatives",
        "precision",
        "recall",
        "f1_score",
        "false_positive_rate",
        "benign_controls_in_population",
        "benign_controls_flagged",
    ]
    return pd.DataFrame(rows)[columns]


def render_evaluation_report(metrics: pd.DataFrame, path: Path) -> None:
    """Write the metric table without rounding away a zero or inventing a score."""
    lines = [
        "# Synthetic detection evaluation",
        "",
        "These figures compare the screening rules with planted synthetic labels.",
        "They are not a real-world fraud-detection accuracy rate, and no alert is a confirmed fraud.",
        "A false positive here includes benign controls and ordinary records the generator did not mark as suspicious.",
        "A false negative includes planted suspicious records the rule is designed to miss, such as near-duplicates that use the next serial invoice number.",
        "",
        "| Rule | Positives | Alerts | TP | FP | FN | TN | Precision | Recall | F1 | FPR | Benign controls flagged |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for _, row in metrics.iterrows():
        lines.append(
            "| {rule} | {positives} | {predicted} | {tp} | {fp} | {fn} | {tn} | {precision} | {recall} | {f1} | {fpr} | {benign} |".format(
                rule=row["rule_code"],
                positives=int(row["positives"]),
                predicted=int(row["predicted"]),
                tp=int(row["true_positives"]),
                fp=int(row["false_positives"]),
                fn=int(row["false_negatives"]),
                tn=int(row["true_negatives"]),
                precision=_fmt(row["precision"]),
                recall=_fmt(row["recall"]),
                f1=_fmt(row["f1_score"]),
                fpr=_fmt(row["false_positive_rate"]),
                benign=int(row["benign_controls_flagged"]),
            )
        )
    scored = metrics.dropna(subset=["f1_score"])
    lines.extend(
        [
            "",
            "## How to read the macro average",
            "",
            "The unweighted mean of available F1 scores treats a date-logic rule and a judgmental rule as equal.",
            "It is a summary of this synthetic test, not a claim about operational performance.",
            "",
        ]
    )
    if scored.empty:
        lines.append("No rule produced an F1 score.")
    else:
        lines.append(f"Unweighted mean F1 across {len(scored)} rules with a defined score: {scored['f1_score'].mean():.4f}.")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _fmt(value: object) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):.4f}"


def entity_column_for_tables() -> dict[str, str]:
    return dict(PRIMARY_KEYS)
