import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import datetime
import os
import psutil
import time
from google.cloud import bigquery
from google.oauth2 import service_account
import concurrent.futures

# 1. Page Configuration
st.set_page_config(
    page_title="Olist Fulfillment & Retention Dashboard",
    page_icon="🚚",
    layout="wide"
)

# ---- CENTRALIZED BLUE THEME CONFIGURATION ----
COLOR_PRIMARY_BLUE = "#4169E1"    
COLOR_DARK_BLUE = "#1E3A8A"       
COLOR_LIGHT_BLUE = "#AEC7E8"      
COLOR_MUTED_SLATE = "#64748B"     
COLOR_BACKGROUND_GRAY = "#E2E8F0" 
COLOR_ALERT_CRIMSON = "#DC2626"   

PALETTE_COHORTS = {'Returning Customer': COLOR_DARK_BLUE, 'One-Time Customer': COLOR_LIGHT_BLUE}
PALETTE_CATEGORIES = [COLOR_PRIMARY_BLUE, "#3B82F6", "#60A5FA", "#93C5FD", "#BFDBFE"]
# ----------------------------------------------

# Helper function to get the BigQuery client safely
def get_bigquery_client():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        credentials = service_account.Credentials.from_service_account_info(creds_dict)
        return bigquery.Client(credentials=credentials, project=creds_dict["project_id"])
    except KeyError:
        st.error("GCP secrets dictionary not found in st.secrets.")
        st.stop()

# Helper function to get initial filter lists efficiently
@st.cache_data(ttl=86400, show_spinner=False)
def load_filter_options(use_mock_data=True):
    if use_mock_data:
        return (
            ['alimentos_bebidas', 'automotivo', 'bebes', 'beleza_saude', 'brinquedos'],
            ['SP', 'RJ', 'MG'],
            ['2016-09', '2016-10', '2016-11', '2016-12', 
             '2017-01', '2017-02', '2017-03', '2017-04', '2017-05', '2017-06', 
             '2017-07', '2017-08', '2017-09', '2017-10', '2017-11', '2017-12',
             '2018-01', '2018-02', '2018-03', '2018-04', '2018-05', '2018-06', '2018-07', '2018-08', '2018-09']
        )
    
    client = get_bigquery_client()
    cat_query = "SELECT DISTINCT product_category_name FROM `dsai-project-51420.olist_all.dim_product` WHERE product_category_name IS NOT NULL ORDER BY 1"
    state_query = "SELECT DISTINCT state FROM `dsai-project-51420.olist_all.dim_customer` WHERE state IS NOT NULL ORDER BY 1"
    
    date_query = """
        SELECT DISTINCT FORMAT_DATE('%Y-%m', date) as year_month 
        FROM `dsai-project-51420.olist_all.dim_date` 
        WHERE date IS NOT NULL 
        ORDER BY 1
    """
    
    cats = client.query(cat_query).to_dataframe()['product_category_name'].tolist()
    states = client.query(state_query).to_dataframe()['state'].tolist()
    months = client.query(date_query).to_dataframe()['year_month'].tolist()
    
    return cats, states, months


# 2. Optimized Aggregated BigQuery Data Loading Functions
@st.cache_data(ttl=3600, show_spinner=False)
def load_fulfillment_summary(selected_cats, selected_sts, start_month, end_month, use_mock_data=True):
    client = get_bigquery_client()
    start_date_str = f"{start_month}-01"
    end_date_str = f"{end_month}-01" 
    
    if use_mock_data:
        return pd.DataFrame([
            {'order_date': '2017-01-15', 'product_category_name': 'alimentos_bebidas', 'customer_state': 'SP', 'total_orders': 150, 'avg_delivery_delay': -2.0, 'late_orders_count': 12, 'avg_freight_value': 9.99, 'avg_item_price_value': 50.00, 'avg_geo_distance': 120.5, 'avg_pickup_delay': 1.0, 'avg_order_rating': 4.5, 'p10_delay': -5.0, 'p25_delay': -3.0, 'p50_delay': -2.0, 'p75_delay': 0.0, 'p90_delay': 2.0},
            {'order_date': '2017-01-20', 'product_category_name': 'automotivo', 'customer_state': 'SP', 'total_orders': 90, 'avg_delivery_delay': 1.2, 'late_orders_count': 35, 'avg_freight_value': 4.50, 'avg_item_price_value': 25.00, 'avg_geo_distance': 45.2, 'avg_pickup_delay': 0.0, 'avg_order_rating': 4.0, 'p10_delay': -2.0, 'p25_delay': 0.0, 'p50_delay': 1.0, 'p75_delay': 3.0, 'p90_delay': 6.0},
            {'order_date': '2017-02-10', 'product_category_name': 'bebes', 'customer_state': 'RJ', 'total_orders': 210, 'avg_delivery_delay': -4.1, 'late_orders_count': 15, 'avg_freight_value': 15.00, 'avg_item_price_value': 300.00, 'avg_geo_distance': 450.0, 'avg_pickup_delay': 2.0, 'avg_order_rating': 4.8, 'p10_delay': -8.0, 'p25_delay': -6.0, 'p50_delay': -4.0, 'p75_delay': -1.0, 'p90_delay': 1.0},
            {'order_date': '2017-02-18', 'product_category_name': 'beleza_saude', 'customer_state': 'MG', 'total_orders': 80, 'avg_delivery_delay': 3.5, 'late_orders_count': 40, 'avg_freight_value': 5.00, 'avg_item_price_value': 12.90, 'avg_geo_distance': 89.1, 'avg_pickup_delay': 1.0, 'avg_order_rating': 3.2, 'p10_delay': -1.0, 'p25_delay': 1.0, 'p50_delay': 3.0, 'p75_delay': 5.0, 'p90_delay': 9.0},
            {'order_date': '2017-03-05', 'product_category_name': 'brinquedos', 'customer_state': 'SP', 'total_orders': 300, 'avg_delivery_delay': 0.0, 'late_orders_count': 45, 'avg_freight_value': 12.30, 'avg_item_price_value': 89.90, 'avg_geo_distance': 210.0, 'avg_pickup_delay': 0.0, 'avg_order_rating': 4.1, 'p10_delay': -4.0, 'p25_delay': -2.0, 'p50_delay': 0.0, 'p75_delay': 2.0, 'p90_delay': 5.0}
        ])
    
    sql_query = """
    SELECT 
        d_order.date AS order_date,
        p.product_category_name,
        c.state AS customer_state,
        COUNT(DISTINCT f.order_id) as total_orders,
        AVG(f.delivery_delay_days) as avg_delivery_delay,
        COUNT(CASE WHEN f.delivery_delay_days > 0 THEN 1 END) as late_orders_count,
        AVG(f.freight_value) as avg_freight_value,
        AVG(f.item_price_value) as avg_item_price_value,
        AVG(f.geo_distance_km) as avg_geo_distance,
        AVG(f.pickup_delay_days) as avg_pickup_delay,
        AVG(f.order_rating) as avg_order_rating,
        APPROX_QUANTILES(f.delivery_delay_days, 100)[OFFSET(10)] AS p10_delay,
        APPROX_QUANTILES(f.delivery_delay_days, 100)[OFFSET(25)] AS p25_delay,
        APPROX_QUANTILES(f.delivery_delay_days, 100)[OFFSET(50)] AS p50_delay,
        APPROX_QUANTILES(f.delivery_delay_days, 100)[OFFSET(75)] AS p75_delay,
        APPROX_QUANTILES(f.delivery_delay_days, 100)[OFFSET(90)] AS p90_delay
    FROM `dsai-project-51420.olist_all.fact_order_fulfillment` AS f
    INNER JOIN `dsai-project-51420.olist_all.dim_product` AS p ON f.product_key = p.product_key
    INNER JOIN `dsai-project-51420.olist_all.dim_customer` AS c ON f.customer_key = c.customer_key
    LEFT JOIN `dsai-project-51420.olist_all.dim_date` AS d_order ON f.order_date_key = d_order.date_key
    WHERE f.order_status = 'delivered'
      AND p.product_category_name IN UNNEST(@categories)
      AND d_order.date BETWEEN CAST(@start_d AS DATE) AND LAST_DAY(CAST(@end_d AS DATE))
    """
    if "All States" not in selected_sts and selected_sts:
        sql_query += " AND c.state IN UNNEST(@states)"
        
    sql_query += " GROUP BY 1, 2, 3"
    
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ArrayQueryParameter("categories", "STRING", selected_cats),
            bigquery.ArrayQueryParameter("states", "STRING", selected_sts),
            bigquery.ScalarQueryParameter("start_d", "STRING", start_date_str),
            bigquery.ScalarQueryParameter("end_d", "STRING", end_date_str)
        ]
    )
    df = client.query(sql_query, job_config=job_config).to_dataframe()
    if 'order_date' in df.columns:
        df['order_date'] = pd.to_datetime(df['order_date'], errors='coerce')
    return df

@st.cache_data(ttl=3600, show_spinner=False)
def load_delay_histogram_data(selected_cats, selected_sts, start_month, end_month, use_mock_data=True):
    if use_mock_data:
        return pd.DataFrame({
            'delay_bucket': range(-20, 20, 2), 
            'order_count': [0, 1, 3, 5, 10, 25, 80, 150, 200, 90, 40, 20, 10, 5, 2, 1, 0, 0, 0, 0]
        })
    client = get_bigquery_client()
    start_date_str = f"{start_month}-01"
    end_date_str = f"{end_month}-01"
    
    sql_query = """
    SELECT 
        CAST(FLOOR(f.delivery_delay_days) AS INT64) as delay_bucket,
        COUNT(DISTINCT f.order_id) as order_count
    FROM `dsai-project-51420.olist_all.fact_order_fulfillment` AS f
    INNER JOIN `dsai-project-51420.olist_all.dim_product` AS p ON f.product_key = p.product_key
    INNER JOIN `dsai-project-51420.olist_all.dim_customer` AS c ON f.customer_key = c.customer_key
    LEFT JOIN `dsai-project-51420.olist_all.dim_date` AS d_order ON f.order_date_key = d_order.date_key
    WHERE f.order_status = 'delivered'
      AND f.delivery_delay_days BETWEEN -60 AND 60
      AND p.product_category_name IN UNNEST(@categories)
      AND d_order.date BETWEEN CAST(@start_d AS DATE) AND LAST_DAY(CAST(@end_d AS DATE))
    """
    if "All States" not in selected_sts and selected_sts:
        sql_query += " AND c.state IN UNNEST(@states)"
    sql_query += " GROUP BY 1 ORDER BY 1"
    
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ArrayQueryParameter("categories", "STRING", selected_cats),
            bigquery.ArrayQueryParameter("states", "STRING", selected_sts),
            bigquery.ScalarQueryParameter("start_d", "STRING", start_date_str),
            bigquery.ScalarQueryParameter("end_d", "STRING", end_date_str)
        ]
    )
    return client.query(sql_query, job_config=job_config).to_dataframe()

@st.cache_data(ttl=3600, show_spinner=False)
def load_correlation_matrix(selected_cats, selected_sts, start_month, end_month, use_mock_data=True):
    if use_mock_data:
        columns = ['delivery_delay_days', 'pickup_delay_days', 'item_price_value', 'freight_value', 'order_rating']
        return pd.DataFrame([[1.0, 0.4, 0.1, 0.2, -0.5], [0.4, 1.0, 0.0, 0.1, -0.3], [0.1, 0.0, 1.0, 0.6, 0.0], [0.2, 0.1, 0.6, 1.0, -0.1], [-0.5, -0.3, 0.0, -0.1, 1.0]], index=columns, columns=columns)
        
    client = get_bigquery_client()
    start_date_str = f"{start_month}-01"
    end_date_str = f"{end_month}-01"
    
    sql_query = """
    SELECT 
        CORR(f.delivery_delay_days, f.pickup_delay_days) as corr_delay_pickup,
        CORR(f.delivery_delay_days, f.item_price_value) as corr_delay_price,
        CORR(f.delivery_delay_days, f.freight_value) as corr_delay_freight,
        CORR(f.delivery_delay_days, f.order_rating) as corr_delay_rating,
        CORR(f.pickup_delay_days, f.item_price_value) as corr_pickup_price,
        CORR(f.pickup_delay_days, f.freight_value) as corr_pickup_freight,
        CORR(f.pickup_delay_days, f.order_rating) as corr_pickup_rating,
        CORR(f.item_price_value, f.freight_value) as corr_price_freight,
        CORR(f.item_price_value, f.order_rating) as corr_price_rating,
        CORR(f.freight_value, f.order_rating) as corr_freight_rating
    FROM `dsai-project-51420.olist_all.fact_order_fulfillment` AS f
    INNER JOIN `dsai-project-51420.olist_all.dim_product` AS p ON f.product_key = p.product_key
    INNER JOIN `dsai-project-51420.olist_all.dim_customer` AS c ON f.customer_key = c.customer_key
    LEFT JOIN `dsai-project-51420.olist_all.dim_date` AS d_order ON f.order_date_key = d_order.date_key
    WHERE f.order_status = 'delivered'
      AND p.product_category_name IN UNNEST(@categories)
      AND d_order.date BETWEEN CAST(@start_d AS DATE) AND LAST_DAY(CAST(@end_d AS DATE))
    """
    if "All States" not in selected_sts and selected_sts:
        sql_query += " AND c.state IN UNNEST(@states)"
        
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ArrayQueryParameter("categories", "STRING", selected_cats),
            bigquery.ArrayQueryParameter("states", "STRING", selected_sts),
            bigquery.ScalarQueryParameter("start_d", "STRING", start_date_str),
            bigquery.ScalarQueryParameter("end_d", "STRING", end_date_str)
        ]
    )
    res = client.query(sql_query, job_config=job_config).to_dataframe().iloc[0]
    
    columns = ['delivery_delay_days', 'pickup_delay_days', 'item_price_value', 'freight_value', 'order_rating']
    matrix = pd.DataFrame(1.0, index=columns, columns=columns)
    
    matrix.loc['delivery_delay_days', 'pickup_delay_days'] = matrix.loc['pickup_delay_days', 'delivery_delay_days'] = res['corr_delay_pickup']
    matrix.loc['delivery_delay_days', 'item_price_value'] = matrix.loc['item_price_value', 'delivery_delay_days'] = res['corr_delay_price']
    matrix.loc['delivery_delay_days', 'freight_value'] = matrix.loc['freight_value', 'delivery_delay_days'] = res['corr_delay_freight']
    matrix.loc['delivery_delay_days', 'order_rating'] = matrix.loc['order_rating', 'delivery_delay_days'] = res['corr_delay_rating']
    matrix.loc['pickup_delay_days', 'item_price_value'] = matrix.loc['item_price_value', 'pickup_delay_days'] = res['corr_pickup_price']
    matrix.loc['pickup_delay_days', 'freight_value'] = matrix.loc['freight_value', 'pickup_delay_days'] = res['corr_pickup_freight']
    matrix.loc['pickup_delay_days', 'order_rating'] = matrix.loc['order_rating', 'pickup_delay_days'] = res['corr_pickup_rating']
    matrix.loc['item_price_value', 'freight_value'] = matrix.loc['freight_value', 'item_price_value'] = res['corr_price_freight']
    matrix.loc['item_price_value', 'order_rating'] = matrix.loc['order_rating', 'item_price_value'] = res['corr_price_rating']
    matrix.loc['freight_value', 'order_rating'] = matrix.loc['order_rating', 'freight_value'] = res['corr_freight_rating']
    return matrix

@st.cache_data(ttl=3600, show_spinner=False)
def load_retention_data(selected_sts, start_month, end_month, use_mock_data=True):
    client = get_bigquery_client()
    start_date_str = f"{start_month}-01"
    end_date_str = f"{end_month}-01"
    
    if use_mock_data:
        return pd.DataFrame([
            {'customer_state': 'SP', 'customer_segment': 'Returning Customer', 'customer_count': 1200, 'total_revenue': 180000.00},
            {'customer_state': 'SP', 'customer_segment': 'One-Time Customer', 'customer_count': 8500, 'total_revenue': 425000.00},
            {'customer_state': 'RJ', 'customer_segment': 'One-Time Customer', 'customer_count': 4100, 'total_revenue': 205000.00},
            {'customer_state': 'MG', 'customer_segment': 'Returning Customer', 'customer_count': 600, 'total_revenue': 90000.00}
        ])

    sql_query = """
    WITH latest_customer_profile AS (
      SELECT customer_unique_id, customer_key, state AS customer_state
      FROM `dsai-project-51420.olist_all.dim_customer`
      WHERE is_current = TRUE
    """
    if "All States" not in selected_sts and selected_sts:
        sql_query += " AND state IN UNNEST(@states)"
        
    sql_query += """
    ),
    customer_metrics AS (
      SELECT 
        c.customer_unique_id,
        c.customer_state,
        COUNT(DISTINCT f.order_id) AS total_orders,
        SUM(f.total_order_value) AS lifetime_order_value
      FROM `dsai-project-51420.olist_all.fact_order_summary` AS f
      INNER JOIN latest_customer_profile AS c ON f.customer_key = c.customer_key
      INNER JOIN `dsai-project-51420.olist_all.dim_date` AS d ON f.order_date_key = d.date_key
      WHERE d.date BETWEEN CAST(@start_d AS DATE) AND LAST_DAY(CAST(@end_d AS DATE))
      GROUP BY c.customer_unique_id, c.customer_state
    ),
    segmented_customers AS (
      SELECT 
        customer_state,
        CASE WHEN total_orders > 1 THEN 'Returning Customer' ELSE 'One-Time Customer' END AS customer_segment,
        lifetime_order_value
      FROM customer_metrics
    )
    SELECT 
      customer_state,
      customer_segment,
      COUNT(*) AS customer_count,
      ROUND(SUM(lifetime_order_value), 2) AS total_revenue
    FROM segmented_customers
    GROUP BY customer_state, customer_segment;
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ArrayQueryParameter("states", "STRING", selected_sts),
            bigquery.ScalarQueryParameter("start_d", "STRING", start_date_str),
            bigquery.ScalarQueryParameter("end_d", "STRING", end_date_str)
        ]
    )
    return client.query(sql_query, job_config=job_config).to_dataframe()

# 3. Sidebar Setup
st.sidebar.header("Data Environment Switch")
data_mode = st.sidebar.toggle(
    "Use Live BigQuery Tables", 
    value=False, 
    help="Toggle between sandbox mock generation and live production cloud analytics tables."
)

st.sidebar.divider()

# ---- #4 BATCH FORM WRAPPER HOOK ----
with st.sidebar.form("dashboard_filter_form"):
    st.header("Filter Options")

    categories, states, available_months = load_filter_options(use_mock_data=not data_mode)

    # Default boundaries assigned dynamically to match full available scope bounds
    default_start_month = available_months[0]
    default_end_month = available_months[-1]

    start_month, end_month = st.select_slider(
        "Select Order Month Range",
        options=available_months,
        value=(default_start_month, default_end_month)
    )

    selected_categories = st.multiselect(
        "Select Product Categories",
        options=categories,
        default=categories[:5] if len(categories) >= 5 else categories
    )

    selected_states = st.multiselect(
        "Select Customer States",
        options=["All States"] + states,
        default="All States"
    )
    
    # Form submission anchor to suppress instant re-runs during user multi-selection
    submit_button = st.form_submit_button("Apply Filters & Run Queries", type='primary', use_container_width=True)

if not selected_categories:
    st.warning("Please choose at least one item from Product Categories.")
    st.stop()

# ---- REAL-TIME PARALLEL TERMINAL LOGGING PIPELINE ----
with st.sidebar.status("Executing concurrent bq tasks...", expanded=True) as status:
    terminal_output = "$ Initializing parallel thread workers...\n"
    console = st.code(terminal_output, language="bash")
    
    t_start = time.time()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        terminal_output += "$ dispatching 4 bq queries simultaneously...\n"
        console.code(terminal_output, language="bash")
        
        # 1. Submit tasks and map futures to task identifiers
        future_to_name = {
            executor.submit(load_fulfillment_summary, selected_categories, selected_states, start_month, end_month, not data_mode): "load_fulfillment_summary",
            executor.submit(load_delay_histogram_data, selected_categories, selected_states, start_month, end_month, not data_mode): "load_delay_histogram_data",
            executor.submit(load_correlation_matrix, selected_categories, selected_states, start_month, end_month, not data_mode): "load_correlation_matrix",
            executor.submit(load_retention_data, selected_states, start_month, end_month, not data_mode): "load_retention_data"
        }
        
        # 2. Process futures dynamically in real-time as they finish
        results = {}
        for future in concurrent.futures.as_completed(future_to_name):
            task_name = future_to_name[future]
            try:
                data = future.result()
                results[task_name] = data  # Save dataframe to a temporary storage dictionary
                
                # Compute elapsed time up to this point
                elapsed = time.time() - t_start
                terminal_output += f"> {task_name} complete [{elapsed:.2f}s elapsed]\n"
                console.code(terminal_output, language="bash")
                
            except Exception as exc:
                terminal_output += f"!! {task_name} generated an exception: {exc}\n"
                console.code(terminal_output, language="bash")
        
        # 3. Safely map dataframes out of our temporary dictionary back to individual variables
        summary_df = results["load_fulfillment_summary"]
        hist_df = results["load_delay_histogram_data"]
        corr_matrix = results["load_correlation_matrix"]
        filtered_retention = results["load_retention_data"]

    total_duration = time.time() - t_start
    terminal_output += f"\n--- SUCCESS: All bq queries finished in {total_duration:.2f}s ---"
    console.code(terminal_output, language="bash")
    
    status.update(
        label=f"bq executed concurrently ({total_duration:.1f}s)", 
        state="complete", 
        expanded=True
    )

# 4. Memory Profiling Status Indicator
def track_memory_timeline():
    if "memory_history" not in st.session_state:
        st.session_state.memory_history = []
    process = psutil.Process(os.getpid())
    current_mem_mb = process.memory_info().rss / (1024 * 1024)
    current_time = datetime.datetime.now().strftime("%H:%M:%S")
    st.session_state.memory_history.append({"Timestamp": current_time, "RAM Usage (MB)": current_mem_mb})
    if len(st.session_state.memory_history) > 100:
        st.session_state.memory_history.pop(0)
    return pd.DataFrame(st.session_state.memory_history)

mem_df = track_memory_timeline()

with st.sidebar.expander("App Memory Usage", expanded=False):
    latest_ram = mem_df["RAM Usage (MB)"].iloc[-1]
    st.markdown("#### Streamlit Free Tier has 1GB Memory limit")
    if latest_ram > 800:
        st.error(f"Current RAM: {latest_ram:.1f} MB (Critical)")
    elif latest_ram > 500:
        st.warning(f"Current RAM: {latest_ram:.1f} MB (High)")
    else:
        st.success(f"Current RAM: {latest_ram:.1f} MB (Stable)")
    st.line_chart(data=mem_df, x="Timestamp", y="RAM Usage (MB)", use_container_width=True)
    if st.button("Force Clear Python RAM"):
        import gc
        st.cache_data.clear() 
        gc.collect()          
        st.rerun()

# 5. UI Elements Header
st.title("🚚 Olist Order Fulfillment & Customer Cohorts")
st.markdown("This dashboard leverages cloud database pre-aggregations to run sub-second analytics pipelines safely below the free-tier infrastructure memory targets.")
st.divider()

st.subheader("Key Performance Indicators")

if not summary_df.empty:
    total_orders = int(summary_df['total_orders'].sum())
    avg_delay = (summary_df['avg_delivery_delay'] * summary_df['total_orders']).sum() / total_orders if total_orders > 0 else 0
    delayed_orders_pct = (summary_df['late_orders_count'].sum() / total_orders * 100) if total_orders > 0 else 0
    avg_freight = (summary_df['avg_freight_value'] * summary_df['total_orders']).sum() / total_orders if total_orders > 0 else 0
    avg_order_value = (summary_df['avg_item_price_value'] * summary_df['total_orders']).sum() / total_orders if total_orders > 0 else 0
    avg_distance = (summary_df['avg_geo_distance'] * summary_df['total_orders']).sum() / total_orders if total_orders > 0 else 0

    row1_col1, row1_col2, row1_col3 = st.columns(3)
    with row1_col1:
        with st.container(border=True):
            st.metric(label="Sampled Orders", value=f"{total_orders:,}")
    with row1_col2:
        with st.container(border=True):
            st.metric(label="Avg Delivery Delay", value=f"{avg_delay:.1f} Days")
    with row1_col3:
        with st.container(border=True):
            st.metric(label="Delayed Orders Rate", value=f"{delayed_orders_pct:.1f}%")

    row2_col1, row2_col2, row2_col3 = st.columns(3)
    with row2_col1:
        with st.container(border=True):
            st.metric(label="Avg Freight Value", value=f"R$ {avg_freight:.2f}")
    with row2_col2:
        with st.container(border=True):
            st.metric(label="Avg Order Value", value=f"R$ {avg_order_value:.2f}")
    with row2_col3:
        with st.container(border=True):
            st.metric(label="Avg Order Distance", value=f"{avg_distance:.1f} km")

    st.divider()

    # 6. Customer Retention Layout Section
    st.subheader("👤 Customer Retention & Lifetime Value Analysis")
    if not filtered_retention.empty:
        cust_col1, cust_col2 = st.columns(2)
    
        segment_counts = filtered_retention.groupby('customer_segment').agg(
            customer_count=('customer_count', 'sum'),
            total_revenue=('total_revenue', 'sum')
        ).reset_index()

        with cust_col1:
            st.markdown("#### Proportion of Customer Base")
            fig_pie = px.pie(
                segment_counts, names='customer_segment', values='customer_count', hole=0.4,
                color='customer_segment', color_discrete_map=PALETTE_COHORTS,
                template='plotly_white'
            )
            st.plotly_chart(fig_pie, use_container_width=True)

        with cust_col2:
            st.markdown("#### Total Revenue Contributed (R$)")
            fig_revenue = px.bar(
                segment_counts, x='customer_segment', y='total_revenue', text_auto='.2s',
                color='customer_segment', color_discrete_map=PALETTE_COHORTS,
                template='plotly_white'
            )
            fig_revenue.update_layout(showlegend=False)
            st.plotly_chart(fig_revenue, use_container_width=True)

        st.markdown("#### Geographic Loyalty Spread (Top States)")
        if 'customer_state' in filtered_retention.columns:
            top_states = filtered_retention.groupby('customer_state')['customer_count'].sum().nlargest(10).index
            filtered_states = filtered_retention[filtered_retention['customer_state'].isin(top_states)]

            fig_state = px.bar(
                filtered_states, x='customer_state', y='customer_count', color='customer_segment',
                title="Top States Buyer Counts broken down by Loyalty",
                color_discrete_map=PALETTE_COHORTS,
                labels={'customer_count': 'Number of Customers', 'customer_state': 'State Code'},
                barmode='stack', template='plotly_white'
            )
            st.plotly_chart(fig_state, use_container_width=True)

    st.divider()
    
    # 7. Fulfillment Distributions Section
    st.subheader("Fulfillment Distributions")
    col_chart1, col_chart2 = st.columns(2)
    
    with col_chart1:
        st.markdown("#### Delivery Delay Box Plot Distribution vs SLA Target")
        cat_groups = summary_df.groupby('product_category_name').agg(
            p10=('p10_delay', 'mean'), p25=('p25_delay', 'mean'), p50=('p50_delay', 'mean'), p75=('p75_delay', 'mean'), p90=('p90_delay', 'mean')
        ).reset_index()
        
        fig_box = go.Figure()
        for _, row in cat_groups.iterrows():
            fig_box.add_trace(go.Box(
                name=row['product_category_name'],
                q1=[row['p25']], median=[row['p50']], q3=[row['p75']],
                lowerfence=[row['p10']], upperfence=[row['p90']],
                fillcolor=COLOR_PRIMARY_BLUE, line=dict(color=COLOR_DARK_BLUE)
            ))
        fig_box.add_hline(y=0, line_dash="dash", line_color=COLOR_ALERT_CRIMSON, annotation_text="SLA Target")
        fig_box.update_layout(showlegend=False, xaxis_tickangle=-30, template='plotly_white')
        st.plotly_chart(fig_box, use_container_width=True)
        
    with col_chart2:
        st.markdown("#### Total Fulfillment Duration vs Corridor Distance (Bubble Volume Summary)")
        cat_summary = summary_df.groupby('product_category_name').agg(
            avg_distance=('avg_geo_distance', 'mean'),
            avg_delay=('avg_delivery_delay', 'mean'),
            volume=('total_orders', 'sum')
        ).reset_index()
        
        fig_scatter = px.scatter(
            cat_summary, x='avg_distance', y='avg_delay', size='volume', color='product_category_name',
            labels={'avg_distance': 'Avg Distance (km)', 'avg_delay': 'Avg Delay (Days)'},
            template='plotly_white', opacity=0.8
        )
        st.plotly_chart(fig_scatter, use_container_width=True)

    st.divider()

    # 8. Delivery Delay Timeline Analysis Section
    st.subheader("📊 Delivery Delay Timeline Analysis")
    
    fig_hist = px.bar(
        hist_df, x='delay_bucket', y='order_count',
        title='Chart 1: Distribution of Order Delivery Delay (Pre-Calculated Warehouse Bins)',
        labels={'delay_bucket': 'Delivery Delay (Days) -> Positive means Late', 'order_count': 'Count of Orders'},
        color_discrete_sequence=[COLOR_PRIMARY_BLUE], template='plotly_white'
    )
    fig_hist.add_vline(x=0, line_dash="dash", line_color=COLOR_ALERT_CRIMSON, annotation_text="Promised Delivery Date")
    st.plotly_chart(fig_hist, use_container_width=True)
    
    st.info(f"💡 **Fulfillment Insight:** Percentage of evaluated orders delivered late: **{delayed_orders_pct:.2f}%**")

    st.divider()

    # 9. Correlation Analysis Section
    st.subheader("🔗 Operational Variables Correlation Matrix")
    fig_heat = px.imshow(
        corr_matrix, text_auto='.2f', color_continuous_scale='Blues', zmin=-1.0, zmax=1.0,
        title='Chart 8: Correlation Matrix: Pre-Calculated Database Variable Pairings',
        template='plotly_white'
    )
    st.plotly_chart(fig_heat, use_container_width=True)

    st.divider()

    # 10. Monthly Order Volume vs. Delivery Delay Percentiles
    st.subheader("📈 Monthly Performance Tendencies & Percentiles")
        
    summary_df['order_date_clean'] = pd.to_datetime(summary_df['order_date'], errors='coerce')
    summary_df['order_month_ts'] = summary_df['order_date_clean'].dt.to_period('M').dt.to_timestamp()

    monthly_stats = summary_df.groupby('order_month_ts').agg(
        p90=('p90_delay', 'mean'), p75=('p75_delay', 'mean'), p50=('p50_delay', 'mean'), p25=('p25_delay', 'mean'), p10=('p10_delay', 'mean'),
        order_count=('total_orders', 'sum')
    ).reset_index().sort_values('order_month_ts')
    
    fig_dual = go.Figure()
    fig_dual.add_trace(go.Bar(x=monthly_stats['order_month_ts'], y=monthly_stats['order_count'], name='Order Volume', marker_color=COLOR_BACKGROUND_GRAY, yaxis='y1'))
    fig_dual.add_trace(go.Scatter(x=monthly_stats['order_month_ts'], y=monthly_stats['p90'], name='90th Pctl', line=dict(color=COLOR_ALERT_CRIMSON, width=2), yaxis='y2'))
    fig_dual.add_trace(go.Scatter(x=monthly_stats['order_month_ts'], y=monthly_stats['p75'], name='75th Pctl', line=dict(color=COLOR_MUTED_SLATE, width=1.5, dash='dash'), yaxis='y2'))
    fig_dual.add_trace(go.Scatter(x=monthly_stats['order_month_ts'], y=monthly_stats['p50'], name='50th Pctl (Median)', line=dict(color=COLOR_PRIMARY_BLUE, width=2.5), yaxis='y2'))
    fig_dual.add_trace(go.Scatter(x=monthly_stats['order_month_ts'], y=monthly_stats['p25'], name='25th Pctl', line=dict(color=COLOR_MUTED_SLATE, width=1.5, dash='dash'), yaxis='y2'))
    fig_dual.add_trace(go.Scatter(x=monthly_stats['order_month_ts'], y=monthly_stats['p10'], name='10th Pctl', line=dict(color=COLOR_DARK_BLUE, width=2), yaxis='y2'))
    
    fig_dual.update_layout(
        title='Chart 11: Monthly Order Volume vs. Delivery Delay Percentiles (Cloud Aggregations)',
        template='plotly_white',
        xaxis=dict(type='date', tickformat='%Y-%m', tickangle=-90, tickmode='linear', dtick='M1'),
        yaxis=dict(title=dict(text='Order Volume', font=dict(color=COLOR_MUTED_SLATE)), tickfont=dict(color=COLOR_MUTED_SLATE)),
        yaxis2=dict(title=dict(text='Delivery Delay (Days)', font=dict(color='black')), tickfont=dict(color='black'), overlaying='y', side='right'),
        legend=dict(x=0.01, y=0.99, bgcolor='rgba(255,255,255,0.8)'), height=600
    )
    st.plotly_chart(fig_dual, use_container_width=True)

else:
    st.warning("No records found matching the selected month range and criteria.")