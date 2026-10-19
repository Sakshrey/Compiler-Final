import csv
import sys
from itertools import permutations
from pathlib import Path

# Reuse the existing compiler evaluation and verification logic.
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import optimizer as opt

OUTPUT_CSV = SCRIPT_DIR / "exhaustive_search_results.csv"


def main():
    if not opt.COMPILER.exists():
        raise FileNotFoundError(
            f"Compiler not found: {opt.COMPILER}\n"
            "Build compiler.exe before running this script."
        )

    print("Measuring baseline TAC and expected return values...")
    expected_values, baseline_counts = opt.measure_baseline()
    baseline_total = sum(baseline_counts)

    sequences = list(permutations(opt.PASSES))

    print(f"Baseline TAC: {baseline_total}")
    print(f"Total unique pass orders: {len(sequences)}")
    print("Starting exhaustive evaluation...\n")

    rows = []

    for index, sequence in enumerate(sequences, start=1):
        sequence_name = " -> ".join(sequence)
        print(f"[{index}/{len(sequences)}] Testing: {sequence_name}")

        try:
            score, program_counts, elapsed = opt.evaluate_sequence(
                sequence, expected_values, verbose=False
            )

            reduction = (
                (baseline_total - score) / baseline_total * 100
                if baseline_total else 0.0
            )

            row = {
                "sequence": sequence_name,
                "combined_tac_count": score,
                "baseline_tac_count": baseline_total,
                "tac_reduction_percent": round(reduction, 2),
                "compiler_elapsed_seconds": round(elapsed, 6),
                "verified": True,
                "error": "",
            }

            for program, count in zip(opt.TEST_PROGRAMS, program_counts):
                row[f"tac_{program['name']}"] = count

            print(
                f"    VERIFIED | TAC={score} | "
                f"Reduction={reduction:.2f}% | "
                f"Time={elapsed:.4f}s"
            )

        except Exception as error:
            row = {
                "sequence": sequence_name,
                "combined_tac_count": "",
                "baseline_tac_count": baseline_total,
                "tac_reduction_percent": "",
                "compiler_elapsed_seconds": "",
                "verified": False,
                "error": str(error).replace("\n", " "),
            }

            for program in opt.TEST_PROGRAMS:
                row[f"tac_{program['name']}"] = ""

            print(f"    FAILED | {error}")

        rows.append(row)

    fieldnames = [
        "sequence",
        "combined_tac_count",
        "baseline_tac_count",
        "tac_reduction_percent",
        "compiler_elapsed_seconds",
        "verified",
        "error",
    ] + [
        f"tac_{program['name']}" for program in opt.TEST_PROGRAMS
    ]

    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    verified_rows = [
        row for row in rows
        if row["verified"] and row["combined_tac_count"] != ""
    ]

    print("\n========== EXHAUSTIVE SEARCH SUMMARY ==========")
    print(f"Orders attempted: {len(rows)}")
    print(f"Verified orders: {len(verified_rows)}")
    print(f"Failed orders: {len(rows) - len(verified_rows)}")
    print(f"Baseline TAC: {baseline_total}")

    if verified_rows:
        best_score = min(
            int(row["combined_tac_count"]) for row in verified_rows
        )
        best_orders = [
            row["sequence"] for row in verified_rows
            if int(row["combined_tac_count"]) == best_score
        ]
        reduction = (baseline_total - best_score) / baseline_total * 100

        print(f"Best verified TAC: {best_score}")
        print(f"TAC reduction: {reduction:.2f}%")
        print("Best sequence(s):")
        for order in best_orders:
            print(f"  {order}")

    print(f"\nFull results saved to:\n{OUTPUT_CSV}")


if __name__ == "__main__":
    main()
