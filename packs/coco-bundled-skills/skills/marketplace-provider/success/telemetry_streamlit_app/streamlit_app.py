import streamlit as st
import pandas as pd
from datetime import date, timedelta

# st.connection works on both container and warehouse runtimes and is thread-safe
# on container runtime (where all viewers share one app process). Prefer it over
# get_active_session(), which is not thread-safe on container runtime.
session = st.connection("snowflake").session()

st.set_page_config(page_title="Listing Telemetry", page_icon="❄️", layout="wide")

today = date.today()


@st.cache_data(ttl=600)
def load_consumption(days):
    return session.sql(f"""
        SELECT
            EVENT_DATE,
            CONSUMER_ACCOUNT_NAME,
            COALESCE(CONSUMER_NAME, CONSUMER_ORGANIZATION) AS CONSUMER_ORGANIZATION,
            LISTING_DISPLAY_NAME,
            SNOWFLAKE_REGION,
            SUM(JOBS) AS JOBS,
            SUM(UNIQUE_USERS_1D) AS UNIQUE_USERS_1D
        FROM SNOWFLAKE.DATA_SHARING_USAGE.LISTING_CONSUMPTION_DAILY
        WHERE EVENT_DATE >= DATEADD('day', -{days}, CURRENT_DATE())
        GROUP BY ALL
        ORDER BY EVENT_DATE
    """).to_pandas()


@st.cache_data(ttl=600)
def load_events(days):
    return session.sql(f"""
        SELECT
            EVENT_DATE,
            EVENT_TYPE,
            LISTING_NAME,
            CONSUMER_ACCOUNT_NAME,
            COALESCE(CONSUMER_NAME, CONSUMER_ORGANIZATION) AS CONSUMER_ORGANIZATION,
            CONSUMER_EMAIL,
            CONSUMER_MCD_STATUS,
            CONSUMER_MCD_OPT_IN_DATE
        FROM SNOWFLAKE.DATA_SHARING_USAGE.LISTING_EVENTS_DAILY
        WHERE EVENT_DATE >= DATEADD('day', -{days}, CURRENT_DATE())
        ORDER BY EVENT_DATE
    """).to_pandas()


@st.cache_data(ttl=600)
def load_telemetry(days):
    return session.sql(f"""
        SELECT
            EVENT_DATE,
            LISTING_NAME,
            EVENT_TYPE,
            SUM(EVENT_COUNT) AS EVENT_COUNT
        FROM SNOWFLAKE.DATA_SHARING_USAGE.LISTING_TELEMETRY_DAILY
        WHERE EVENT_DATE >= DATEADD('day', -{days}, CURRENT_DATE())
        GROUP BY EVENT_DATE, LISTING_NAME, EVENT_TYPE
        ORDER BY EVENT_DATE
    """).to_pandas()


@st.cache_data(ttl=600)
def load_access_history(days):
    return session.sql(f"""
        SELECT
            QUERY_DATE,
            QUERY_TOKEN,
            CONSUMER_ACCOUNT_NAME,
            SNOWFLAKE_REGION,
            LISTING_GLOBAL_NAME
        FROM SNOWFLAKE.DATA_SHARING_USAGE.LISTING_ACCESS_HISTORY
        WHERE QUERY_DATE >= DATEADD('day', -{days}, CURRENT_DATE())
        ORDER BY QUERY_DATE
    """).to_pandas()


with st.sidebar:
    st.title("❄️ Listing Telemetry")
    st.caption("Marketplace usage analytics")
    st.divider()
    period = st.radio("Time Period", ["7 days", "30 days", "90 days"], index=1)
    period_days = int(period.split()[0])

cd = load_consumption(period_days)
events = load_events(period_days)
telemetry = load_telemetry(period_days)
ah = load_access_history(period_days)

prev_cd = load_consumption(period_days * 2)
if not prev_cd.empty:
    prev_cd = prev_cd[prev_cd["EVENT_DATE"] < (today - timedelta(days=period_days))]

listing_filter = []
if not cd.empty:
    all_listings = sorted(cd["LISTING_DISPLAY_NAME"].unique())
    with st.sidebar:
        st.divider()
        listing_filter = st.multiselect("Filter Listings", all_listings, default=all_listings)
    cd = cd[cd["LISTING_DISPLAY_NAME"].isin(listing_filter)]
    if not prev_cd.empty:
        prev_cd = prev_cd[prev_cd["LISTING_DISPLAY_NAME"].isin(listing_filter)]


def delta_pct(curr, prev):
    if prev == 0:
        return None
    return f"{(curr - prev) / prev * 100:+.0f}%"


tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Overview",
    "Consumption",
    "Consumers",
    "Events & Funnel",
    "Leads",
])

# --- TAB 1: OVERVIEW ---
with tab1:
    st.header("Listing Performance Overview")

    total_jobs = int(cd["JOBS"].sum()) if not cd.empty else 0
    total_users = int(cd["UNIQUE_USERS_1D"].sum()) if not cd.empty else 0
    unique_consumers = cd["CONSUMER_ORGANIZATION"].nunique() if not cd.empty else 0
    active_listings = cd["LISTING_DISPLAY_NAME"].nunique() if not cd.empty else 0
    total_views = int(telemetry[telemetry["EVENT_TYPE"] == "LISTING VIEW"]["EVENT_COUNT"].sum()) if not telemetry.empty else 0
    total_gets = len(events[events["EVENT_TYPE"] == "GET"]) if not events.empty else 0

    prev_jobs = int(prev_cd["JOBS"].sum()) if not prev_cd.empty else 0
    prev_users = int(prev_cd["UNIQUE_USERS_1D"].sum()) if not prev_cd.empty else 0
    prev_consumers = prev_cd["CONSUMER_ORGANIZATION"].nunique() if not prev_cd.empty else 0

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Active Orgs", f"{unique_consumers:,}", delta=delta_pct(unique_consumers, prev_consumers))
    c2.metric("Total Jobs", f"{total_jobs:,}", delta=delta_pct(total_jobs, prev_jobs))
    c3.metric("User Sessions", f"{total_users:,}", delta=delta_pct(total_users, prev_users))
    c4.metric("Listing Views", f"{total_views:,}")
    c5.metric("GETs", f"{total_gets:,}")
    c6.metric("Active Listings", f"{active_listings:,}")

    if total_views > 0 and total_gets > 0:
        conv = total_gets / total_views * 100
        st.info(f"**View → GET conversion rate: {conv:.1f}%** over the last {period_days} days")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Daily Jobs")
        if not cd.empty:
            daily_jobs = cd.groupby("EVENT_DATE").agg(JOBS=("JOBS", "sum")).reset_index()
            daily_jobs = daily_jobs.rename(columns={"EVENT_DATE": "Date", "JOBS": "Jobs"})
            st.bar_chart(daily_jobs, x="Date", y="Jobs")

    with col2:
        st.subheader("Daily Views & Clicks")
        if not telemetry.empty:
            views_df = telemetry[telemetry["EVENT_TYPE"].isin(["LISTING VIEW", "LISTING CLICK"])]
            tel_agg = views_df.pivot_table(
                index="EVENT_DATE", columns="EVENT_TYPE", values="EVENT_COUNT", aggfunc="sum"
            ).fillna(0).reset_index().rename(columns={"EVENT_DATE": "Date", "LISTING VIEW": "Views", "LISTING CLICK": "Clicks"})
            y_cols = [c for c in ["Views", "Clicks"] if c in tel_agg.columns]
            if y_cols:
                st.bar_chart(tel_agg, x="Date", y=y_cols)


# --- TAB 2: CONSUMPTION ---
with tab2:
    st.header("Consumption Analytics")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Daily Jobs & Users")
        if not cd.empty:
            daily_agg = cd.groupby("EVENT_DATE").agg(
                Jobs=("JOBS", "sum"),
                Users=("UNIQUE_USERS_1D", "sum"),
            ).reset_index().rename(columns={"EVENT_DATE": "Date"})
            st.line_chart(daily_agg, x="Date", y=["Jobs", "Users"])

    with col2:
        st.subheader("Consumption by Listing")
        if not cd.empty:
            by_listing = cd.groupby("LISTING_DISPLAY_NAME").agg(
                Jobs=("JOBS", "sum"),
                Orgs=("CONSUMER_ORGANIZATION", "nunique"),
            ).reset_index().rename(columns={"LISTING_DISPLAY_NAME": "Listing"})
            by_listing = by_listing.sort_values("Jobs", ascending=False)
            st.bar_chart(by_listing, x="Listing", y="Jobs")
            st.caption("Org count per listing:")
            st.dataframe(by_listing[["Listing", "Orgs"]], hide_index=True, use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Query Volume (Access History)")
        if not ah.empty:
            daily_q = ah.groupby("QUERY_DATE").size().reset_index(name="Queries")
            daily_q = daily_q.rename(columns={"QUERY_DATE": "Date"})
            st.area_chart(daily_q, x="Date", y="Queries")
        else:
            st.info("No access history data available.")

    with col2:
        st.subheader("Queries by Region")
        if not ah.empty:
            by_region = ah.groupby("SNOWFLAKE_REGION").size().reset_index(name="Queries")
            by_region = by_region.rename(columns={"SNOWFLAKE_REGION": "Region"})
            by_region = by_region.sort_values("Queries", ascending=False)
            st.bar_chart(by_region, x="Region", y="Queries")
        else:
            st.info("No access history data available.")

    st.divider()
    st.subheader("Consumption Heatmap (Jobs by Day of Week)")
    if not cd.empty:
        heat = cd.copy()
        heat["DOW"] = pd.to_datetime(heat["EVENT_DATE"]).dt.day_name()
        hm = heat.groupby(["LISTING_DISPLAY_NAME", "DOW"])["JOBS"].sum().reset_index()
        hm_pivot = hm.pivot(index="LISTING_DISPLAY_NAME", columns="DOW", values="JOBS").fillna(0)
        dow_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        hm_pivot = hm_pivot.reindex(columns=[d for d in dow_order if d in hm_pivot.columns])
        styled = hm_pivot.style.background_gradient(cmap="Blues", axis=None).format("{:.0f}")
        st.dataframe(styled, use_container_width=True)
    else:
        st.info("No consumption data available.")


# --- TAB 3: CONSUMERS ---
with tab3:
    st.header("Consumer Breakdown")

    if not cd.empty:
        top = cd.groupby("CONSUMER_ORGANIZATION").agg(
            TOTAL_JOBS=("JOBS", "sum"),
            TOTAL_USERS=("UNIQUE_USERS_1D", "sum"),
            LISTINGS_USED=("LISTING_DISPLAY_NAME", "nunique"),
            DAYS_ACTIVE=("EVENT_DATE", "nunique"),
        ).reset_index().sort_values("TOTAL_JOBS", ascending=False)

        c1, c2, c3 = st.columns(3)
        c1.metric("Total Orgs", f"{len(top):,}")
        c2.metric("Avg Jobs/Org", f"{top['TOTAL_JOBS'].mean():,.0f}")
        c3.metric("Avg Listings/Org", f"{top['LISTINGS_USED'].mean():.1f}")

        st.subheader("Top Organizations by Usage")
        st.bar_chart(
            top.head(15).rename(columns={"CONSUMER_ORGANIZATION": "Organization", "TOTAL_JOBS": "Jobs"}),
            x="Organization", y="Jobs"
        )

        st.subheader("All Organizations")
        st.dataframe(
            top,
            hide_index=True, use_container_width=True,
            column_config={
                "CONSUMER_ORGANIZATION": "Organization",
                "TOTAL_JOBS": st.column_config.NumberColumn("Jobs", format="%d"),
                "TOTAL_USERS": st.column_config.NumberColumn("Users", format="%d"),
                "LISTINGS_USED": st.column_config.NumberColumn("Listings", format="%d"),
                "DAYS_ACTIVE": st.column_config.NumberColumn("Days Active", format="%d"),
            },
        )

        st.divider()
        st.subheader("Usage by Region")
        by_region = cd.groupby("SNOWFLAKE_REGION").agg(
            Jobs=("JOBS", "sum"),
            Orgs=("CONSUMER_ORGANIZATION", "nunique"),
        ).reset_index().rename(columns={"SNOWFLAKE_REGION": "Region"})
        by_region = by_region.sort_values("Jobs", ascending=False)
        st.bar_chart(by_region, x="Region", y="Jobs")
        st.dataframe(by_region, hide_index=True, use_container_width=True)
    else:
        st.info("No consumption data available for the selected period.")


# --- TAB 4: EVENTS & FUNNEL ---
with tab4:
    st.header("Events & Funnel")

    if not events.empty:
        event_counts = events.groupby("EVENT_TYPE").size().reset_index(name="COUNT").sort_values("COUNT", ascending=False)

        cols = st.columns(len(event_counts))
        for i, (_, row) in enumerate(event_counts.iterrows()):
            cols[i].metric(row["EVENT_TYPE"], f"{row['COUNT']:,}")

        st.subheader("Events Over Time")
        daily_events = events.groupby(["EVENT_DATE", "EVENT_TYPE"]).size().reset_index(name="COUNT")
        pivot_events = daily_events.pivot(index="EVENT_DATE", columns="EVENT_TYPE", values="COUNT").fillna(0)
        pivot_events.index.name = "Date"
        st.bar_chart(pivot_events)

        funnel_order = ["GET", "REQUEST", "TRIAL", "PURCHASE"]
        funnel_data = events["EVENT_TYPE"].value_counts()
        funnel_vals = [(e, int(funnel_data.get(e, 0))) for e in funnel_order if funnel_data.get(e, 0) > 0]

        if len(funnel_vals) > 1:
            st.subheader("Conversion Funnel")
            first_val = funnel_vals[0][1]
            funnel_df = pd.DataFrame(funnel_vals, columns=["Stage", "Count"])
            funnel_df["% of First Stage"] = (funnel_df["Count"] / first_val * 100).round(1)
            st.dataframe(funnel_df, hide_index=True, use_container_width=True)
            st.bar_chart(funnel_df, x="Stage", y="Count")

        st.divider()
        st.subheader("Recent Events")
        st.dataframe(
            events.sort_values("EVENT_DATE", ascending=False).head(50),
            hide_index=True, use_container_width=True,
            column_config={
                "EVENT_DATE": st.column_config.DateColumn("Date"),
                "EVENT_TYPE": "Event",
                "LISTING_NAME": "Listing",
                "CONSUMER_ACCOUNT_NAME": "Account",
                "CONSUMER_ORGANIZATION": "Organization",
                "CONSUMER_EMAIL": "Email",
                "CONSUMER_MCD_STATUS": "MCD Status",
                "CONSUMER_MCD_OPT_IN_DATE": st.column_config.DatetimeColumn("MCD Opt-in"),
            },
        )
    else:
        st.info("No listing events found for the selected period.")


# --- TAB 5: LEADS ---
with tab5:
    st.header("Leads — Trial & Active Consumers")
    st.caption(
        "Consumers who have started a trial or are actively querying your listings. "
        "Use this list to proactively reach out and convert to paid."
    )

    if not events.empty:
        trials = events[events["EVENT_TYPE"] == "TRIAL"].copy()

        if not trials.empty:
            # Find which trial orgs have since purchased
            purchased_orgs = set(
                events[events["EVENT_TYPE"] == "PURCHASE"]["CONSUMER_ORGANIZATION"].dropna()
            )
            trials["Status"] = trials["CONSUMER_ORGANIZATION"].apply(
                lambda o: "Converted" if o in purchased_orgs else "Active Trial"
            )

            leads = trials.sort_values("EVENT_DATE", ascending=False).drop_duplicates(
                subset=["CONSUMER_ORGANIZATION", "LISTING_NAME"]
            )

            active = leads[leads["Status"] == "Active Trial"]
            converted = leads[leads["Status"] == "Converted"]

            c1, c2 = st.columns(2)
            c1.metric("Active Trials", f"{len(active):,}")
            c2.metric("Converted", f"{len(converted):,}")

            if len(active) > 0:
                conv_rate = len(converted) / (len(active) + len(converted)) * 100
                st.info(f"**Trial → Purchase conversion rate: {conv_rate:.1f}%**")

            st.subheader("Active Trials")
            if not active.empty:
                st.dataframe(
                    active[["EVENT_DATE", "CONSUMER_ORGANIZATION", "LISTING_NAME",
                             "CONSUMER_EMAIL", "CONSUMER_MCD_STATUS", "CONSUMER_MCD_OPT_IN_DATE"]],
                    hide_index=True, use_container_width=True,
                    column_config={
                        "EVENT_DATE": st.column_config.DateColumn("Trial Started"),
                        "CONSUMER_ORGANIZATION": "Organization",
                        "LISTING_NAME": "Listing",
                        "CONSUMER_EMAIL": "Contact Email",
                        "CONSUMER_MCD_STATUS": "MCD Status",
                        "CONSUMER_MCD_OPT_IN_DATE": st.column_config.DatetimeColumn("MCD Opt-in Date"),
                    },
                )
            else:
                st.info("No active trials in this period.")

            st.subheader("Converted Trials")
            if not converted.empty:
                st.dataframe(
                    converted[["EVENT_DATE", "CONSUMER_ORGANIZATION", "LISTING_NAME",
                                "CONSUMER_EMAIL", "CONSUMER_MCD_STATUS"]],
                    hide_index=True, use_container_width=True,
                    column_config={
                        "EVENT_DATE": st.column_config.DateColumn("Trial Started"),
                        "CONSUMER_ORGANIZATION": "Organization",
                        "LISTING_NAME": "Listing",
                        "CONSUMER_EMAIL": "Contact Email",
                        "CONSUMER_MCD_STATUS": "MCD Status",
                    },
                )
            else:
                st.info("No converted trials in this period.")
        else:
            st.info("No trial events found for the selected period.")

    # Active consumers who haven't trialed — also worth outreach
    st.divider()
    st.subheader("Active Consumers (No Trial)")
    st.caption("Organizations actively querying your listing who have not started a formal trial.")
    if not cd.empty and not events.empty:
        trial_orgs = set(events[events["EVENT_TYPE"] == "TRIAL"]["CONSUMER_ORGANIZATION"].dropna())
        active_orgs = cd.groupby("CONSUMER_ORGANIZATION").agg(
            TOTAL_JOBS=("JOBS", "sum"),
            LAST_ACTIVE=("EVENT_DATE", "max"),
            LISTINGS_USED=("LISTING_DISPLAY_NAME", "nunique"),
        ).reset_index()
        non_trial = active_orgs[~active_orgs["CONSUMER_ORGANIZATION"].isin(trial_orgs)]
        non_trial = non_trial.sort_values("TOTAL_JOBS", ascending=False)
        if not non_trial.empty:
            st.dataframe(
                non_trial,
                hide_index=True, use_container_width=True,
                column_config={
                    "CONSUMER_ORGANIZATION": "Organization",
                    "TOTAL_JOBS": st.column_config.NumberColumn("Total Jobs", format="%d"),
                    "LAST_ACTIVE": st.column_config.DateColumn("Last Active"),
                    "LISTINGS_USED": st.column_config.NumberColumn("Listings Used", format="%d"),
                },
            )
        else:
            st.info("No non-trial active consumers found.")
    elif cd.empty:
        st.info("No consumption data available for the selected period.")


with st.expander("SQL queries powering this dashboard"):
    st.code("""-- Consumption by org & listing (org shown as friendly name, ID as fallback)
SELECT EVENT_DATE, CONSUMER_ACCOUNT_NAME,
       COALESCE(CONSUMER_NAME, CONSUMER_ORGANIZATION) AS CONSUMER_ORGANIZATION,
       LISTING_DISPLAY_NAME, SNOWFLAKE_REGION,
       SUM(JOBS) AS JOBS, SUM(UNIQUE_USERS_1D) AS USERS
FROM SNOWFLAKE.DATA_SHARING_USAGE.LISTING_CONSUMPTION_DAILY
WHERE EVENT_DATE >= DATEADD('day', -90, CURRENT_DATE())
GROUP BY ALL;

-- Consumer events (GET, REQUEST, TRIAL, PURCHASE) with MCD info
SELECT EVENT_DATE, EVENT_TYPE, LISTING_NAME, CONSUMER_ACCOUNT_NAME,
       COALESCE(CONSUMER_NAME, CONSUMER_ORGANIZATION) AS CONSUMER_ORGANIZATION,
       CONSUMER_EMAIL, CONSUMER_MCD_STATUS, CONSUMER_MCD_OPT_IN_DATE
FROM SNOWFLAKE.DATA_SHARING_USAGE.LISTING_EVENTS_DAILY
WHERE EVENT_DATE >= DATEADD('day', -90, CURRENT_DATE());

-- Aggregate views & clicks
SELECT EVENT_DATE, LISTING_NAME, EVENT_TYPE, SUM(EVENT_COUNT) AS EVENT_COUNT
FROM SNOWFLAKE.DATA_SHARING_USAGE.LISTING_TELEMETRY_DAILY
WHERE EVENT_DATE >= DATEADD('day', -90, CURRENT_DATE())
GROUP BY EVENT_DATE, LISTING_NAME, EVENT_TYPE;

-- Query-level access history
SELECT QUERY_DATE, QUERY_TOKEN, CONSUMER_ACCOUNT_NAME,
       SNOWFLAKE_REGION, LISTING_GLOBAL_NAME
FROM SNOWFLAKE.DATA_SHARING_USAGE.LISTING_ACCESS_HISTORY
WHERE QUERY_DATE >= DATEADD('day', -90, CURRENT_DATE());""", language="sql")
