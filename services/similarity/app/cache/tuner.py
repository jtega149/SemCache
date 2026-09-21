from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

DEFAULT_THRESHOLDS = (0.90, 0.95, 0.98)
DEFAULT_FIXTURE = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "threshold_pairs.jsonl"
)


@dataclass(frozen=True)
class PromptPair:
    query: str
    cached_prompt: str
    same_intent: bool


@dataclass(frozen=True)
class ThresholdReport:
    threshold: float
    examples: int
    hits: int
    true_positives: int
    false_positives: int

    @property
    def hit_rate(self) -> float:
        if self.examples == 0:
            return 0.0
        return self.hits / self.examples

    @property
    def precision(self) -> float:
        if self.hits == 0:
            return 0.0
        return self.true_positives / self.hits


def cosine_score(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def load_pairs(path: Path) -> list[PromptPair]:
    pairs: list[PromptPair] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        pairs.append(
            PromptPair(
                query=row["query"],
                cached_prompt=row["cached_prompt"],
                same_intent=bool(row["same_intent"]),
            )
        )
    return pairs


def replay(
    scored: Sequence[tuple[float, bool]],
    thresholds: Sequence[float] = DEFAULT_THRESHOLDS,
) -> list[ThresholdReport]:
    reports: list[ThresholdReport] = []
    examples = len(scored)
    for threshold in thresholds:
        hits = 0
        true_positives = 0
        false_positives = 0
        for score, same_intent in scored:
            if score < threshold:
                continue
            hits += 1
            if same_intent:
                true_positives += 1
            else:
                false_positives += 1
        reports.append(
            ThresholdReport(
                threshold=threshold,
                examples=examples,
                hits=hits,
                true_positives=true_positives,
                false_positives=false_positives,
            )
        )
    return reports


def format_reports(reports: Sequence[ThresholdReport]) -> str:
    lines = [
        f"{'threshold':>10}  {'hit_rate':>8}  {'precision':>9}  {'hits':>5}  {'FP':>4}  {'n':>4}",
    ]
    for report in reports:
        lines.append(
            f"{report.threshold:10.2f}  {report.hit_rate:8.2%}  {report.precision:9.2%}  "
            f"{report.hits:5d}  {report.false_positives:4d}  {report.examples:4d}"
        )
    return "\n".join(lines)


async def score_pairs(pairs: Sequence[PromptPair]) -> list[tuple[float, bool]]:
    from app.embeddings.openai import embed

    scored: list[tuple[float, bool]] = []
    for pair in pairs:
        query_vec = await embed(pair.query)
        cached_vec = await embed(pair.cached_prompt)
        scored.append((cosine_score(query_vec, cached_vec), pair.same_intent))
    return scored


async def run_tuner(fixture: Path, thresholds: Sequence[float]) -> list[ThresholdReport]:
    pairs = load_pairs(fixture)
    scored = await score_pairs(pairs)
    return replay(scored, thresholds)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Replay cache hit thresholds against labeled prompt pairs."
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=DEFAULT_FIXTURE,
        help="JSONL of query, cached_prompt, same_intent",
    )
    args = parser.parse_args()
    reports = asyncio.run(run_tuner(args.fixture, DEFAULT_THRESHOLDS))
    print(format_reports(reports))


if __name__ == "__main__":
    main()
