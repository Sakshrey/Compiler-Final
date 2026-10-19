
from pathlib import Path

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
