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
