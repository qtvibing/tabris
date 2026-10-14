from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

FALSE_PAIR_RATES = (1e-5, 1e-4, 1e-3)


def mean_from_histogram(histogram: np.ndarray) -> float:
    return float(np.dot(np.arange(len(histogram)), histogram) / histogram.sum())


def auc(positive: np.ndarray, negative: np.ndarray) -> float:
    positive_histogram = np.bincount(positive, minlength=len(negative))
    greater = np.cumsum(negative[::-1])[::-1] - negative
    favorable = positive_histogram * (greater + negative * 0.5)
    return float(favorable.sum() / (positive_histogram.sum() * negative.sum()))


def threshold_at(histogram: np.ndarray, target: float) -> tuple[int, float]:
    rates = np.cumsum(histogram) / histogram.sum()
    eligible = np.flatnonzero(rates <= target)
    if not len(eligible):
        return -1, 0.0
    threshold = int(eligible[-1])
    return threshold, float(rates[threshold])


def aggregate_groups(groups: np.ndarray) -> dict[str, list[int]]:
    result: dict[str, list[int]] = {}
    for index, group in enumerate(groups):
        result.setdefault(str(group), []).append(index)
    result["non_destructive"] = [
        index for index, group in enumerate(groups) if group != "destructive"
    ]
    return result


def write_report(measurements: Path, markdown: Path, summary_path: Path) -> None:
    data = np.load(measurements)
    methods = [str(value) for value in data["methods"]]
    widths = {name: int(data["widths"][index]) for index, name in enumerate(methods)}
    transform_names = data["transform_names"]
    transform_groups = data["transform_groups"]
    groups = aggregate_groups(transform_groups)

    summary: dict[str, object] = {
        "images": int(len(data["labels"])),
        "distinct_pairs": int(data[f"{methods[0]}_negative_hist"].sum()),
        "transform_source_images": int(len(data["transform_source_labels"])),
        "transformations": int(len(transform_names)),
        "transformed_variants": int(len(data["transform_source_labels"]) * len(transform_names)),
        "methods": {},
    }

    lines = [
        "# tabris quality report",
        "",
        f"- {len(data['labels']):,} pixel-unique originals",
        f"- {int(data[f'{methods[0]}_negative_hist'].sum()):,} exhaustive distinct-original pairs",
        f"- {len(data['transform_source_labels']):,} source images × "
        f"{len(transform_names)} transformations = "
        f"{len(data['transform_source_labels']) * len(transform_names):,} transformed variants",
        f"- {len(data['duplicate_labels']):,} exact decoded-pixel duplicates removed",
        "",
        "Distinct originals can still be semantic near-duplicates. the "
        "picsum-only column is a separate natural-photo slice.",
        "",
        "## discrimination",
        "",
        "| Method | Bits | Pair mean | Pair minimum | Picsum minimum | Exact collisions |",
        "|---|---:|---:|---:|---:|---:|",
    ]

    method_summaries: dict[str, object] = {}
    for name in methods:
        histogram = data[f"{name}_negative_hist"]
        natural = data[f"{name}_picsum_negative_hist"]
        pair_minimum = int(np.flatnonzero(histogram)[0])
        natural_minimum = int(np.flatnonzero(natural)[0])
        exact = int(histogram[0])
        method_summary: dict[str, object] = {
            "bits": widths[name],
            "pair_mean": mean_from_histogram(histogram),
            "pair_minimum": pair_minimum,
            "picsum_minimum": natural_minimum,
            "exact_collisions": exact,
            "auc": {},
            "fixed_pair_rate": {},
        }
        method_summaries[name] = method_summary
        lines.append(
            f"| {name} | {widths[name]} | {method_summary['pair_mean']:.2f} | "
            f"{pair_minimum} | {natural_minimum} | {exact} |"
        )

    lines += [
        "",
        "## roc auc",
        "",
        "| Method | " + " | ".join(groups) + " |",
        "|---|" + "---:|" * len(groups),
    ]
    for name in methods:
        negative = data[f"{name}_negative_hist"]
        distances = data[f"{name}_variant_distances"]
        values = []
        for group, indices in groups.items():
            score = auc(distances[:, indices].ravel(), negative)
            method_summaries[name]["auc"][group] = score
            values.append(f"{score:.6f}")
        lines.append(f"| {name} | " + " | ".join(values) + " |")

    lines += [
        "",
        "## recall at fixed distinct-original pair rates",
        "",
        "the threshold is selected separately for each method on the complete "
        "original-pair distribution.",
        "",
        "| Target rate | Method | Threshold | Actual rate | Non-destructive recall |",
        "|---:|---|---:|---:|---:|",
    ]
    useful = groups["non_destructive"]
    for target in FALSE_PAIR_RATES:
        for name in methods:
            negative = data[f"{name}_negative_hist"]
            threshold, actual = threshold_at(negative, target)
            distances = data[f"{name}_variant_distances"][:, useful]
            recall = float(np.mean(distances <= threshold)) if threshold >= 0 else 0.0
            method_summaries[name]["fixed_pair_rate"][str(target)] = {
                "threshold": threshold,
                "actual_rate": actual,
                "recall": recall,
            }
            lines.append(
                f"| {target:.0e} | {name} | {threshold} | {actual:.2e} | {recall:.2%} |"
            )

    tabris = data["tabris_variant_distances"]
    lines += [
        "",
        "## tabris transformations",
        "",
        "| Transformation | Group | Mean | P95 | P99 | Maximum |",
        "|---|---|---:|---:|---:|---:|",
    ]
    transforms: dict[str, object] = {}
    for index, transform in enumerate(transform_names):
        values = tabris[:, index]
        transform_summary = {
            "group": str(transform_groups[index]),
            "mean": float(values.mean()),
            "p95": float(np.quantile(values, 0.95)),
            "p99": float(np.quantile(values, 0.99)),
            "maximum": int(values.max()),
        }
        transforms[str(transform)] = transform_summary
        lines.append(
            f"| {transform} | {transform_summary['group']} | {transform_summary['mean']:.2f} | "
            f"{transform_summary['p95']:.0f} | {transform_summary['p99']:.0f} | "
            f"{transform_summary['maximum']} |"
        )

    bits = np.unpackbits(data["tabris_hashes"], axis=1, bitorder="little")
    rates = bits.mean(axis=0)
    correlation = np.corrcoef(bits, rowvar=False)
    off_diagonal = np.abs(correlation[np.triu_indices_from(correlation, 1)])
    bit_summary = {
        "mean_one_rate": float(rates.mean()),
        "minimum_one_rate": float(rates.min()),
        "maximum_one_rate": float(rates.max()),
        "mean_absolute_correlation": float(off_diagonal.mean()),
        "p95_absolute_correlation": float(np.quantile(off_diagonal, 0.95)),
        "maximum_absolute_correlation": float(off_diagonal.max()),
    }
    lines += [
        "",
        "## tabris bit statistics",
        "",
        f"- One-rate mean/min/max: {bit_summary['mean_one_rate']:.3f} / "
        f"{bit_summary['minimum_one_rate']:.3f} / {bit_summary['maximum_one_rate']:.3f}",
        f"- Absolute correlation mean/P95/max: {bit_summary['mean_absolute_correlation']:.3f} / "
        f"{bit_summary['p95_absolute_correlation']:.3f} / "
        f"{bit_summary['maximum_absolute_correlation']:.3f}",
    ]

    exact_pairs = data["tabris_exact_pairs"]
    if len(exact_pairs):
        lines += ["", "## exact tabris collisions", ""]
        for left, right in exact_pairs[:20]:
            lines.append(f"- `{data['labels'][left]}` ↔ `{data['labels'][right]}`")

    summary["methods"] = method_summaries
    summary["tabris_transforms"] = transforms
    summary["tabris_bits"] = bit_summary
    markdown.write_text("\n".join(lines) + "\n")
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="render an existing tabris quality measurement")
    parser.add_argument("measurements", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or args.measurements.with_name("report.md")
    write_report(args.measurements, output, output.with_name("summary.json"))


if __name__ == "__main__":
    main()
