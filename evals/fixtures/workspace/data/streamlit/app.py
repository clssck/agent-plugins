import plotly.express as px
import streamlit as st
from snowflake.snowpark.context import get_active_session

session = get_active_session()
df = session.table("ORDERS").to_pandas()
st.plotly_chart(px.bar(df, x="DAY", y="AMOUNT"))
