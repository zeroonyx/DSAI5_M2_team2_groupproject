import streamlit as st
import pandas as pd
import plotly.express as px
import datetime
import os
import psutil
from google.cloud import bigquery
from google.oauth2 import service_account

# 1. Page Configuration
st.set_page_config(
    page_title="Olist Fulfillment Dashboard",
    page_icon="🚚",
    layout="wide"
)

# 2. Cached BigQuery Data Loading Function
@st.cache_data(ttl=3600)  # Caches results for 1 hour to optimize BigQuery usage cost
def load_bigquery_data():
    # Initialize the client wrapper
    # Note: Ensure your local environment has GOOGLE_APPLICATION_CREDENTIALS set 
    # Authenticate safely using Streamlit Secrets
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        credentials = service_account.Credentials.from_service_account_info(creds_dict)
        client = bigquery.Client(credentials=credentials, project=creds_dict["project_id"])
    except KeyError:
        # Fallback mechanism if secrets are missing (e.g., local development via environment variables)
        st.error("GCP secrets dictionary not found in st.secrets.")
        st.stop()

    sql_query = """
    SELECT 
        f.order_id,
        f.order_item_id, 
        f.customer_key, 
        f.seller_key, 
        f.product_key, 
        f.item_price_value, 
        f.freight_value, 
        f.order_rating,
        f.delivery_delay_days, 
        f.pickup_delay_days,
        f.total_fulfillment_duration_days,
        f.geo_distance_km,
        
        -- Pulling true calendar dates via surrogate key relationships
        d_order.date AS order_date,
        d_pay.date AS payment_date,
        
        -- Temporal metadata for seasonality tracking
        d_order.year AS order_year,
        d_order.month AS order_month,
        d_order.day_of_week AS order_day_name,
        d_order.is_weekend AS order_is_weekend,
        
        -- Product details
        p.product_category_name,
        p.product_type,
        
        -- Geographic corridor analysis
        c.state AS customer_state,
        s.state AS seller_state
        
    FROM `dsai-project-51420.olist_all.fact_order_fulfillment` AS f

    -- Join to product dimension on product_key
    LEFT JOIN `dsai-project-51420.olist_all.dim_product` AS p
        ON f.product_key = p.product_key
        
    -- Join to customer and seller dimensions
    LEFT JOIN `dsai-project-51420.olist_all.dim_customer` AS c
        ON f.customer_key = c.customer_key
    LEFT JOIN `dsai-project-51420.olist_all.dim_seller` AS s
        ON f.seller_key = s.seller_key
        
    -- Joins to resolve date keys (INTEGER) to dim_date (INTEGER)
    LEFT JOIN `dsai-project-51420.olist_all.dim_date` AS d_order
        ON f.order_date_key = d_order.date_key
    LEFT JOIN `dsai-project-51420.olist_all.dim_date` AS d_pay
        ON f.payment_date_key = d_pay.date_key
        
    WHERE f.order_status = 'delivered'
    """
    
    sql_query_sample = """
    SELECT * FROM `dsai-project-51420.olist_all.sample_order_fulfillment`
    """

    # Executing query and downloading dataframe
    # df = client.query(sql_query).to_dataframe()
    df = client.query(sql_query_sample).to_dataframe()
    
    # Enforce clear date types
    df['order_date'] = pd.to_datetime(df['order_date'])
    df['payment_date'] = pd.to_datetime(df['payment_date'])
    
    return df

# Initialize data pull
with st.spinner("Fetching data from BigQuery star schema..."):
    df_clean = load_bigquery_data()

# 3. Sidebar Filters
st.sidebar.header("Filter Options")

# Category Filter (Handling potential missing/null values safely)
categories = df_clean['product_category_name'].dropna().unique().tolist()
categories.sort()

selected_categories = st.sidebar.multiselect(
    "Select Product Categories",
    options=categories,
    default=categories[:5] if len(categories) >= 5 else categories
)

# Filter dataframe dynamically based on sidebar selections
filtered_df = df_clean[df_clean['product_category_name'].isin(selected_categories)]


def track_memory_timeline():
    # 1. Initialize the session state list if it doesn't exist
    if "memory_history" not in st.session_state:
        st.session_state.memory_history = []

    # 2. Get current system process memory consumption
    process = psutil.Process(os.getpid())
    current_mem_mb = process.memory_info().rss / (1024 * 1024)
    # current_time = datetime.datetime.now()
    current_time = datetime.datetime.now().strftime("%H:%M:%S")

    # 3. Append the newest data point
    st.session_state.memory_history.append({
        "Timestamp": current_time,
        "RAM Usage (MB)": current_mem_mb
    })

    # 4. Optional: Cap history at the last 100 script reruns to save memory
    if len(st.session_state.memory_history) > 100:
        st.session_state.memory_history.pop(0)

    # 5. Convert to a Pandas DataFrame for charting
    return pd.DataFrame(st.session_state.memory_history)

# Execute tracking at the start of every single rerun
mem_df = track_memory_timeline()

with st.sidebar.expander("App Memory Usage", expanded=False):
    latest_ram = mem_df["RAM Usage (MB)"].iloc[-1]
    st.markdown("#### Steamlit Free Tier has 1GB Memory limit")
    # Visual warning color indicator based on community limits
    if latest_ram > 800:
        st.error(f"Current RAM: {latest_ram:.1f} MB (Critical)")
    elif latest_ram > 500:
        st.warning(f"Current RAM: {latest_ram:.1f} MB (High)")
    else:
        st.success(f"Current RAM: {latest_ram:.1f} MB (Stable)")
        
    # Plotting the historical timeline using native Streamlit line charts
    st.line_chart(
        data=mem_df, 
        x="Timestamp", 
        y="RAM Usage (MB)", 
        use_container_width=True
    )
    
    # Manual button to let you trigger garbage collection instantly
    if st.button("Force Clear Python RAM"):
        import gc
        st.cache_data.clear() # Wipes out cached BigQuery frames
        gc.collect()          # Forces Python memory release
        st.rerun()
# ------------------------------------

# 4. Dashboard Title layout
st.title("🚚 Olist Order Fulfillment Analysis")
st.markdown("""
This interactive dashboard analyzes logistics fulfillment, delivery delay metrics, 
and SLA performance directly connected to the Google BigQuery data warehouse.
""")

st.divider()

# 5. Dynamic Key Metrics KPI Row
st.subheader("Key Performance Indicators")
col1, col2, col3, col4 = st.columns(4)

total_orders = len(filtered_df)
avg_delay = filtered_df['delivery_delay_days'].mean() if total_orders > 0 else 0
delayed_orders_pct = ((filtered_df['delivery_delay_days'] > 0).sum() / total_orders * 100) if total_orders > 0 else 0
avg_freight = filtered_df['freight_value'].mean() if total_orders > 0 else 0

with col1:
    st.metric(label="Sampled Orders Evaluated", value=f"{total_orders:,}")

with col2:
    st.metric(
        label="Average Delivery Delay", 
        value=f"{avg_delay:.1f} Days",
        delta="Above SLA Target" if avg_delay > 0 else "Within SLA Target",
        delta_color="inverse"
    )

with col3:
    st.metric(label="Delayed Orders Rate", value=f"{delayed_orders_pct:.1f}%")

with col4:
    st.metric(label="Average Freight Value", value=f"R$ {avg_freight:.2f}")

st.divider()

# 6. Interactive Plotly Visualizations Section
st.subheader("Fulfillment Distributions")

if not filtered_df.empty:
    col_chart1, col_chart2 = st.columns(2)
    
    with col_chart1:
        st.markdown("#### Delivery Delay Distribution vs SLA")
        # Generating interactive boxplot replacing Chart 17
        fig_box = px.box(
            filtered_df,
            x='product_category_name',
            y='delivery_delay_days',
            color='product_category_name',
            labels={
                'product_category_name': 'Product Category',
                'delivery_delay_days': 'Delivery Delay (Days vs SLA)'
            },
            template='plotly_white'
        )
        
        # Adding a visual benchmark for SLA Target at 0
        fig_box.add_hline(
            y=0, 
            line_dash="dash", 
            line_color="crimson", 
            annotation_text="SLA Target Target", 
            annotation_position="top left"
        )
        
        fig_box.update_layout(showlegend=False, xaxis_tickangle=-30)
        st.plotly_chart(fig_box, use_container_width=True)
        
    with col_chart2:
        st.markdown("#### Total Fulfillment Duration vs Corridor Distance")
        # Creating a scatter plot showing distance effect on fulfillment duration
        fig_scatter = px.scatter(
            filtered_df,
            x='geo_distance_km',
            y='total_fulfillment_duration_days',
            color='product_category_name',
            hover_data=['order_id', 'customer_state', 'seller_state'],
            labels={
                'geo_distance_km': 'Geographic Distance (km)',
                'total_fulfillment_duration_days': 'Total Fulfillment Duration (Days)'
            },
            template='plotly_white'
        )
        fig_scatter.update_layout(xaxis_tickangle=0)
        st.plotly_chart(fig_scatter, use_container_width=True)

else:
    st.warning("Please select at least one product category from the filter menu sidebar.")