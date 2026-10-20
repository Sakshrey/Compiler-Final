from pathlib import Path
import os
import shutil
import subprocess
import tempfile

import pandas as pd
import plotly.express as px
import streamlit as st

# Page setup
st.set_page_config(
    page_title="Automatic Compiler Optimization",
    page_icon="⚙️",
    layout="wide",
)

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "bayesian"

st.title("⚙️ Automatic Compiler Optimization")
st.write(
    "Interactive dashboard for comparing Bayesian optimization "
    "with exhaustive search."
)

# Load CSV files
@st.cache_data
def load_csv(path, modified_time):
    return pd.read_csv(path)


def read_csv(filename):
    path = DATA_DIR / filename
    if not path.exists():
        return None
    return load_csv(str(path), path.stat().st_mtime)


def is_verified(df):
    if "verified" not in df.columns:
        return pd.Series(False, index=df.index)
    return df["verified"].astype(str).str.lower().isin(
        ["true", "1", "yes"]
    )


def get_scores(df):
    if "combined_tac_count" not in df.columns:
        return pd.Series(float("nan"), index=df.index)
    return pd.to_numeric(df["combined_tac_count"], errors="coerce")


# Read existing results
exhaustive = read_csv("exhaustive_search_results.csv")

bayesian_results = {
    seed: read_csv(f"optimization_results_seed_{seed}.csv")
    for seed in (2026, 2027, 2028)
}

# Sidebar navigation
page = st.sidebar.radio(
    "Navigate",
    [
        "Overview",
        "Try Your Code",
        "Exhaustive Search",
        "Bayesian Optimization",
        "Reports & Downloads",
    ],
)

st.sidebar.caption("Results are loaded from the bayesian folder.")

if st.sidebar.button("Refresh data"):
    st.cache_data.clear()
    st.rerun()

# Calculate exhaustive metrics
if exhaustive is not None:
    ex_verified = is_verified(exhaustive)
    ex_scores = get_scores(exhaustive)
    valid_scores = ex_scores[ex_verified].dropna()
    best_tac = valid_scores.min() if not valid_scores.empty else None

    baseline = None
    if "baseline_tac_count" in exhaustive.columns:
        baseline_values = pd.to_numeric(
            exhaustive["baseline_tac_count"], errors="coerce"
        ).dropna()
        if not baseline_values.empty:
            baseline = baseline_values.iloc[0]
else:
    ex_verified = None
    ex_scores = None
    best_tac = None
    baseline = None


# Compiler helpers shared by the custom-code page

def get_compiler():
    """Return a usable compiler binary, building from bundled C sources if needed."""
    bundled_exe = ROOT / "compiler.exe"
    if os.name == "nt" and bundled_exe.exists():
        return str(bundled_exe)

    gcc = shutil.which("gcc")
    if not gcc:
        raise RuntimeError(
            "A C compiler (gcc) is not available on this deployment. "
            "Add `build-essential` to the app's packages.txt and redeploy."
        )

    built = ROOT / "compiler"
    source_files = [
        ROOT / "parser.tab.c",
        ROOT / "lex.yy.c",
        ROOT / "ast" / "ast.c",
        ROOT / "ir" / "ir.c",
        ROOT / "optimizer" / "algebraic_simplification.c",
        ROOT / "optimizer" / "common_subexpression.c",
        ROOT / "optimizer" / "constant_folding.c",
        ROOT / "optimizer" / "dead_code_elimination.c",
        ROOT / "optimizer" / "pass_manager.c",
    ]
    missing = [str(item.name) for item in source_files if not item.exists()]
    if missing:
        raise RuntimeError("Compiler source files are missing: " + ", ".join(missing))

    newest_source = max(item.stat().st_mtime for item in source_files)
    if not built.exists() or built.stat().st_mtime < newest_source:
        command = [gcc, "-O2", "-o", str(built)] + [str(item) for item in source_files]
        result = subprocess.run(command, capture_output=True, text=True, timeout=60, cwd=str(ROOT))
        if result.returncode:
            raise RuntimeError("Could not build compiler:\n" + result.stderr[-5000:])
    return str(built)


def extract_tac(output, marker):
    if marker not in output:
        raise RuntimeError("Compiler output did not contain: " + marker)
    part = output.split(marker, 1)[1]
    if "Three Address Code:" in part:
        part = part.split("Three Address Code:", 1)[1]
    lines = []
    for line in part.splitlines():
        line = line.strip()
        if line in {"Executing Optimization Passes:", "After Optimization:"}:
            break
        if line and not line.startswith("Enter program:"):
            lines.append(line)
    return lines


# Interactive compiler page
if page == "Try Your Code":
    from itertools import permutations

    st.header("Find the Best Optimization Sequence")
    st.caption(
        "Enter a program in this project's small C-like integer language. "
        "The app will test all 24 orders of CF, AS, DCE and CSE and choose "
        "the order producing the fewest TAC instructions for this input."
    )

    default_source = """int a;
int b;
int c;
a = 10 + 20;
b = a * 2;
c = b + 0;
return c;
"""
    source_code = st.text_area(
        "Enter your program", value=default_source, height=240,
        help="Example: int x; x = 2 + 3; return x;",
    )
    st.info("You do not need to select a sequence. The app tests every permutation automatically.")

    if st.button("Find Best Optimization Sequence", type="primary"):
        if not source_code.strip():
            st.error("Enter a program first.")
        else:
            try:
                compiler = get_compiler()
                passes = ("CF", "AS", "DCE", "CSE")
                orders = list(permutations(passes))
                baseline_tac = None
                rows = []
                progress = st.progress(0, text="Preparing compiler search…")

                for index, order in enumerate(orders, start=1):
                    result = subprocess.run(
                        [compiler, *order], input=source_code,
                        capture_output=True, text=True, timeout=10, cwd=str(ROOT),
                    )
                    output = result.stdout
                    if result.returncode != 0:
                        rows.append({"sequence": " -> ".join(order), "count": None,
                                     "original": [], "optimized": [],
                                     "error": (result.stderr + "\n" + output).strip()[-2000:]})
                    else:
                        original = extract_tac(output, "Before Optimization:")
                        optimized = extract_tac(output, "After Optimization:")
                        if baseline_tac is None:
                            baseline_tac = original
                        rows.append({"sequence": " -> ".join(order), "count": len(optimized),
                                     "original": original, "optimized": optimized, "error": ""})
                    progress.progress(index / len(orders), text=f"Testing sequence {index}/{len(orders)}")

                progress.empty()
                successful = [row for row in rows if row["count"] is not None]
                if not successful:
                    st.error("The compiler could not process this program with any sequence.")
                    errors = [row["error"] for row in rows if row["error"]]
                    if errors:
                        st.code(errors[0], language="text")
                else:
                    best_count = min(row["count"] for row in successful)
                    best_rows = [row for row in successful if row["count"] == best_count]
                    best = best_rows[0]
                    original_count = len(best["original"])
                    reduction = ((original_count - best_count) / original_count * 100) if original_count else 0.0

                    st.success(f"Search complete: {len(successful)} of {len(orders)} sequences ran successfully.")
                    st.subheader("Best sequence found for your input")
                    st.code(best["sequence"], language="text")
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("Sequences tested", f"{len(successful)}/{len(orders)}")
                    m2.metric("Original TAC instructions", original_count)
                    m3.metric("Best TAC instructions", best_count)
                    m4.metric("TAC reduction", f"{reduction:.2f}%")

                    left, right = st.columns(2)
                    with left:
                        st.subheader("Original intermediate code")
                        st.code("\n".join(best["original"]) or "(no instructions)", language="text")
                    with right:
                        st.subheader("Best optimized intermediate code")
                        st.code("\n".join(best["optimized"]) or "(no instructions)", language="text")

                    st.subheader("Results for all sequences")
                    results_df = pd.DataFrame([
                        {"Sequence": row["sequence"], "Optimized TAC instructions": row["count"],
                         "Status": "Success" if row["count"] is not None else "Failed"}
                        for row in rows
                    ]).sort_values("Optimized TAC instructions", na_position="last")
                    st.dataframe(results_df, use_container_width=True, hide_index=True)
                    fig = px.bar(results_df.dropna(subset=["Optimized TAC instructions"]),
                                 x="Sequence", y="Optimized TAC instructions",
                                 title="TAC instruction count by optimization sequence")
                    fig.update_layout(xaxis_tickangle=-45)
                    st.plotly_chart(fig, use_container_width=True)

                    report = (
                        "SOURCE PROGRAM\n" + source_code +
                        "\n\nBEST SEQUENCE\n" + best["sequence"] +
                        "\n\nORIGINAL TAC\n" + "\n".join(best["original"]) +
                        "\n\nBEST OPTIMIZED TAC\n" + "\n".join(best["optimized"]) +
                        f"\n\nOriginal TAC instructions: {original_count}" +
                        f"\nBest TAC instructions: {best_count}" +
                        f"\nTAC reduction: {reduction:.2f}%" +
                        f"\nSuccessful sequences: {len(successful)}/{len(orders)}" +
                        "\n\nALL SEQUENCES\n" + results_df.to_string(index=False)
                    )
                    st.download_button("Download search report", report,
                                       file_name="best_optimization_sequence_report.txt", mime="text/plain")
                    st.caption("This ranks sequences by TAC instruction count. It does not independently prove semantic equivalence for every user program.")
            except (RuntimeError, subprocess.TimeoutExpired, OSError) as exc:
                st.error(str(exc))

# Overview
if page == "Overview":
    st.header("Project Overview")

    if exhaustive is None:
        st.error(
            "Could not find bayesian/exhaustive_search_results.csv"
        )
        st.stop()

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Baseline TAC",
        int(baseline) if baseline is not None else "N/A",
    )
    col2.metric(
        "Best TAC",
        int(best_tac) if best_tac is not None else "N/A",
    )

    if baseline is not None and best_tac is not None and baseline:
        reduction = (baseline - best_tac) / baseline * 100
        col3.metric("TAC Reduction", f"{reduction:.2f}%")
    else:
        col3.metric("TAC Reduction", "N/A")

    col4.metric(
        "Verified Exhaustive Orders",
        f"{int(ex_verified.sum())}/{len(exhaustive)}",
    )

    st.subheader("Bayesian Optimization Summary")

    summary = []
    for seed, df in bayesian_results.items():
        if df is None:
            continue

        verified = is_verified(df)
        scores = get_scores(df)[verified].dropna()

        summary.append({
            "Seed": seed,
            "Candidates": len(df),
            "Verified": int(verified.sum()),
            "Best TAC": int(scores.min()) if not scores.empty else None,
            "Matches exhaustive best": (
                bool(scores.min() == best_tac)
                if not scores.empty and best_tac is not None
                else None
            ),
        })

    if summary:
        summary_df = pd.DataFrame(summary)
        st.dataframe(
            summary_df, use_container_width=True, hide_index=True
        )

        fig = px.bar(
            summary_df,
            x="Seed",
            y="Best TAC",
            title="Best TAC count by Bayesian random seed",
            text="Best TAC",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("No Bayesian result files were found.")

    st.info(
        "TAC reduction measures instruction-count reduction, "
        "not necessarily runtime speedup."
    )


# Exhaustive search page
elif page == "Exhaustive Search":
    st.header("Exhaustive Search Results")

    if exhaustive is None:
        st.error("Exhaustive result CSV not found.")
        st.stop()

    verified = is_verified(exhaustive)
    scores = get_scores(exhaustive)

    st.write(f"Orders tested: **{len(exhaustive)}**")
    st.write(f"Verified: **{int(verified.sum())}**")
    st.write(f"Failed or unverified: **{int((~verified).sum())}**")

    best_rows = exhaustive.loc[verified & scores.eq(best_tac)]

    st.subheader("Best Sequences")
    st.dataframe(best_rows, use_container_width=True, hide_index=True)

    plot_df = exhaustive.copy()
    plot_df["TAC Count"] = get_scores(plot_df)
    plot_df["Status"] = is_verified(plot_df).map({
        True: "Verified",
        False: "Not verified",
    })

    fig = px.bar(
        plot_df,
        x="sequence",
        y="TAC Count",
        color="Status",
        title="TAC count for all pass orderings",
        hover_data=["sequence"],
    )
    fig.update_layout(xaxis_tickangle=-45)
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("All Results")
    st.dataframe(exhaustive, use_container_width=True, hide_index=True)

    st.download_button(
        "Download exhaustive results CSV",
        exhaustive.to_csv(index=False).encode("utf-8"),
        file_name="exhaustive_search_results.csv",
        mime="text/csv",
    )


# Bayesian results page
elif page == "Bayesian Optimization":
    st.header("Bayesian Optimization Results")

    seed = st.selectbox("Select random seed", [2026, 2027, 2028])
    df = bayesian_results[seed]

    if df is None:
        st.warning(f"Results for seed {seed} were not found.")
        st.stop()

    verified = is_verified(df)
    scores = get_scores(df)[verified].dropna()

    c1, c2, c3 = st.columns(3)
    c1.metric("Candidates", len(df))
    c2.metric("Verified", f"{int(verified.sum())}/{len(df)}")
    c3.metric(
        "Best TAC",
        int(scores.min()) if not scores.empty else "N/A",
    )

    st.subheader("Candidate Results")
    st.dataframe(df, use_container_width=True, hide_index=True)

    plot_df = df.copy()
    plot_df["TAC Count"] = get_scores(plot_df)
    plot_df["Status"] = is_verified(plot_df).map({
        True: "Verified",
        False: "Not verified",
    })

    fig = px.bar(
        plot_df,
        x="sequence",
        y="TAC Count",
        color="Status",
        title=f"Bayesian candidates — seed {seed}",
        hover_data=["sequence"],
    )
    fig.update_layout(xaxis_tickangle=-45)
    st.plotly_chart(fig, use_container_width=True)

    st.download_button(
        f"Download seed {seed} CSV",
        df.to_csv(index=False).encode("utf-8"),
        file_name=f"optimization_results_seed_{seed}.csv",
        mime="text/csv",
    )

    image_path = DATA_DIR / f"optimization_results_seed_{seed}.png"
    if image_path.exists():
        st.subheader("Saved Optimization Plot")
        st.image(str(image_path), use_container_width=True)


# Reports and downloads
elif page == "Reports & Downloads":
    st.header("Reports & Downloads")

    for seed in (2026, 2027, 2028):
        report_path = DATA_DIR / f"optimization_report_seed_{seed}.txt"

        if report_path.exists():
            with st.expander(f"Optimization report — seed {seed}"):
                report_text = report_path.read_text(
                    encoding="utf-8", errors="replace"
                )
                st.text(report_text)

                st.download_button(
                    f"Download report {seed}",
                    report_text,
                    file_name=f"optimization_report_seed_{seed}.txt",
                    mime="text/plain",
                    key=f"report_{seed}",
                )

    st.subheader("All Available Result Files")

    for path in sorted(DATA_DIR.iterdir()):
        if not path.is_file():
            continue

        if path.suffix.lower() in [".csv", ".txt", ".png"]:
            st.write(f"**{path.name}** ({path.stat().st_size:,} bytes)")

            if path.suffix.lower() == ".png":
                with st.expander(f"Preview {path.name}"):
                    st.image(str(path), use_container_width=True)
            else:
                st.download_button(
                    f"Download {path.name}",
                    data=path.read_bytes(),
                    file_name=path.name,
                    key=f"download_{path.name}",
                )
