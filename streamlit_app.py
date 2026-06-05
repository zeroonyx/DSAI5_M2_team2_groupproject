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
    page_title="Olist Fulfillment & Retention Dashboard",
    page_icon="🚚",
    layout="wide"
)

# Helper function to get the BigQuery client safely
def get_bigquery_client():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        credentials = service_account.Credentials.from_service_account_info(creds_dict)
        return bigquery.Client(credentials=credentials, project=creds_dict["project_id"])
    except KeyError:
        st.error("GCP secrets dictionary not found in st.secrets.")
        st.stop()

# 2. Cached BigQuery Data Loading Functions
@st.cache_data(ttl=3600)
def load_fulfillment_data(use_mock_data=True):
    client = get_bigquery_client()
    
    if use_mock_data:
        # Standalone mock dataset for fulfillment to bypass missing physical table gaps
        sql_query = """
        SELECT * FROM UNNEST([
            STRUCT('ord_A' AS order_id, 1 AS order_item_id, 101 AS customer_key, 201 AS seller_key, 301 AS product_key, 50.00 AS item_price_value, 9.99 AS freight_value, 5 AS order_rating, -2 AS delivery_delay_days, 1 AS pickup_delay_days, 5 AS total_fulfillment_duration_days, 120.5 AS geo_distance_km, 'alimentos_bebidas' AS product_category_name, 'SP' AS customer_state),
            STRUCT('ord_B', 1, 101, 201, 302, 25.00, 4.50, 4, 1, 0, 7, 45.2, 'automotivo', 'SP'),
            STRUCT('ord_C', 1, 102, 202, 303, 300.00, 15.00, 5, -5, 2, 10, 450.0, 'bebes', 'RJ'),
            STRUCT('ord_D', 1, 103, 203, 304, 12.90, 5.00, 3, 4, 1, 14, 89.1, 'beleza_saude', 'MG'),
            STRUCT('ord_E', 1, 104, 204, 305, 89.90, 12.30, 2, 0, 0, 6, 210.0, 'brinquedos', 'SP')
        ])
        """
    else:
        # Production fulfillment warehousing query
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
        
    df = client.query(sql_query).to_dataframe()
    
    date_columns = ['order_date', 'payment_date']
    for col in date_columns:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')
    return df

@st.cache_data(ttl=3600)
def load_retention_data(use_mock_data=True):
    client = get_bigquery_client()
    
    if use_mock_data:
        sql_query = """
            WITH dim_customer_mock AS (
            SELECT * FROM UNNEST([
                STRUCT('cust_1' AS customer_unique_id, 101 AS customer_key, 'SP' AS state, TRUE AS is_current),
                STRUCT('cust_1', 101, 'SP', FALSE),
                STRUCT('cust_2', 102, 'RJ', TRUE),
                STRUCT('cust_3', 103, 'MG', TRUE)
            ])
            ),

            fact_order_summary_mock AS (
            SELECT * FROM UNNEST([
                STRUCT('ord_A' AS order_id, 101 AS customer_key, 150.00 AS total_order_value, 5.0 AS order_rating),
                STRUCT('ord_B', 101, 50.00, 4.0),
                STRUCT('ord_C', 102, 300.00, 4.5),
                STRUCT('ord_D', 103, 50.00, 3.0)
            ])
            ),

            latest_customer_profile AS (
            SELECT 
                customer_unique_id,
                customer_key,
                state AS customer_state
            FROM 
                dim_customer_mock
            WHERE 
                is_current = TRUE
            ),

            customer_metrics AS (
            SELECT 
                c.customer_unique_id,
                COUNT(DISTINCT f.order_id) AS total_orders,
                SUM(f.total_order_value) AS lifetime_order_value,
                AVG(f.order_rating) AS avg_rating
            FROM 
                fact_order_summary_mock AS f
            JOIN 
                dim_customer_mock AS c
                ON f.customer_key = c.customer_key
            GROUP BY 
                c.customer_unique_id
            )

            SELECT 
            m.customer_unique_id,
            p.customer_state,
            m.total_orders,
            ROUND(m.lifetime_order_value, 2) AS lifetime_order_value,
            ROUND(m.avg_rating, 2) AS avg_order_rating,
            CASE 
                WHEN m.total_orders > 1 THEN 'Returning Customer'
                ELSE 'One-Time Customer'
            END AS customer_segment
            FROM 
            customer_metrics AS m
            LEFT JOIN 
            latest_customer_profile AS p
            ON m.customer_unique_id = p.customer_unique_id
            ORDER BY 
            m.lifetime_order_value DESC;
        """
    else:
        # Production cohort analysis query
        sql_query = """
        WITH latest_customer_profile AS (
          SELECT 
            customer_unique_id,
            customer_key,
            state AS customer_state
          FROM 
            `dsai-project-51420.olist_all.dim_customer`
          WHERE 
            is_current = TRUE
        ),

        customer_metrics AS (
          SELECT 
            c.customer_unique_id,
            COUNT(DISTINCT f.order_id) AS total_orders,
            SUM(f.total_order_value) AS lifetime_order_value,
            AVG(f.order_rating) AS avg_rating
          FROM 
            `dsai-project-51420.olist_all.fact_order_summary` AS f
          JOIN 
            `dsai-project-51420.olist_all.dim_customer` AS c
            ON f.customer_key = c.customer_key
          GROUP BY 
            c.customer_unique_id
        )

        SELECT 
          m.customer_unique_id,
          p.customer_state,
          m.total_orders,
          ROUND(m.lifetime_order_value, 2) AS lifetime_order_value,
          ROUND(m.avg_rating, 2) AS avg_order_rating,
          CASE 
            WHEN m.total_orders > 1 THEN 'Returning Customer'
            ELSE 'One-Time Customer'
          END AS customer_segment
        FROM 
          customer_metrics AS m
        LEFT JOIN 
          latest_customer_profile AS p
          ON m.customer_unique_id = p.customer_unique_id
        ORDER BY 
          m.lifetime_order_value DESC;
        """
        
    return client.query(sql_query).to_dataframe()

# 3. Sidebar Filters
st.sidebar.header("Data Environment Switch")
data_mode = st.sidebar.toggle(
    "Use Live BigQuery Tables", 
    value=False, 
    help="Toggle between sandbox mock generation and live production cloud analytics tables."
)

# Initialize data pulls with toggled execution environment
with st.spinner("Fetching data from BigQuery star schema..."):
    df_fulfillment = load_fulfillment_data(use_mock_data=not data_mode)
    df_retention = load_retention_data(use_mock_data=not data_mode)

st.sidebar.divider()
st.sidebar.header("Filter Options")

# Category Filter Setup
categories = df_fulfillment['product_category_name'].dropna().unique().tolist()
categories.sort()

selected_categories = st.sidebar.multiselect(
    "Select Product Categories",
    options=categories,
    default=categories[:5] if len(categories) >= 5 else categories
)

# State Filter Setup (Combines clean lookups from dataframes)
available_states = set()
if 'customer_state' in df_retention.columns:
    available_states.update(df_retention['customer_state'].dropna().unique())
if 'customer_state' in df_fulfillment.columns:
    available_states.update(df_fulfillment['customer_state'].dropna().unique())

states = sorted(list(available_states))

selected_states = st.sidebar.multiselect(
    "Select Customer States",
    options=["All States"] + states,
    default="All States"
)

# Filter logistics dataframe dynamically based on sidebar selections
filtered_fulfillment = df_fulfillment[df_fulfillment['product_category_name'].isin(selected_categories)]

# Apply State Filter to Logistics if column matches
if "All States" not in selected_states and selected_states:
    if 'customer_state' in filtered_fulfillment.columns:
        filtered_fulfillment = filtered_fulfillment[filtered_fulfillment['customer_state'].isin(selected_states)]

# Filter retention dataframe dynamically based on sidebar selections
if "All States" in selected_states or not selected_states:
    filtered_retention = df_retention.copy()
else:
    filtered_retention = df_retention[df_retention['customer_state'].isin(selected_states)]


def track_memory_timeline():
    if "memory_history" not in st.session_state:
        st.session_state.memory_history = []

    process = psutil.Process(os.getpid())
    current_mem_mb = process.memory_info().rss / (1024 * 1024)
    current_time = datetime.datetime.now().strftime("%H:%M:%S")

    st.session_state.memory_history.append({
        "Timestamp": current_time,
        "RAM Usage (MB)": current_mem_mb
    })

    if len(st.session_state.memory_history) > 100:
        st.session_state.memory_history.pop(0)

    return pd.DataFrame(st.session_state.memory_history)

mem_df = track_memory_timeline()

with st.sidebar.expander("App Memory Usage", expanded=False):
    latest_ram = mem_df["RAM Usage (MB)"].iloc[-1]
    st.markdown("#### Steamlit Free Tier has 1GB Memory limit")
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

# 4. Dashboard Title layout
st.title("🚚 Olist Order Fulfillment & Customer Cohorts")
st.markdown("""
This interactive dashboard analyzes logistics fulfillment, delivery delay metrics, 
and customer cohort behavior directly connected to the Google BigQuery data warehouse.
""")

st.divider()

# 5. Dynamic Key Metrics KPI Row
st.subheader("Key Performance Indicators")
col1, col2, col3, col4 = st.columns(4)

total_orders = len(filtered_fulfillment)
avg_delay = filtered_fulfillment['delivery_delay_days'].mean() if total_orders > 0 and 'delivery_delay_days' in filtered_fulfillment.columns else 0
delayed_orders_pct = ((filtered_fulfillment['delivery_delay_days'] > 0).sum() / total_orders * 100) if total_orders > 0 and 'delivery_delay_days' in filtered_fulfillment.columns else 0
avg_freight = filtered_fulfillment['freight_value'].mean() if total_orders > 0 and 'freight_value' in filtered_fulfillment.columns else 0

with col1:
    st.metric(label="Sampled Orders Evaluated", value=f"{total_orders:,}")
with col2:
    st.metric(label="Average Delivery Delay", value=f"{avg_delay:.1f} Days", delta="Above SLA Target" if avg_delay > 0 else "Within SLA Target", delta_color="inverse")
with col3:
    st.metric(label="Delayed Orders Rate", value=f"{delayed_orders_pct:.1f}%")
with col4:
    st.metric(label="Average Freight Value", value=f"R$ {avg_freight:.2f}")

st.divider()

# Check to ensure product categories are selected globally before drawing elements
if not filtered_fulfillment.empty:

    # 7. Customer Retention Layout Section
    st.subheader("👤 Customer Retention & Lifetime Value Analysis")

    if not filtered_retention.empty:
        cust_col1, cust_col2 = st.columns(2)

        with cust_col1:
            st.markdown("#### Segment Distribution")
            segment_counts = filtered_retention.groupby('customer_segment').agg(
                customer_count=('customer_unique_id', 'count'),
                total_revenue=('lifetime_order_value', 'sum')
            ).reset_index()

            fig_pie = px.pie(
                segment_counts,
                names='customer_segment',
                values='customer_count',
                hole=0.4,
                title="Proportion of Customer Base",
                color='customer_segment',
                color_discrete_map={'Returning Customer': '#1f77b4', 'One-Time Customer': '#aec7e8'},
                template='plotly_white'
            )
            st.plotly_chart(fig_pie, use_container_width=True)

        with cust_col2:
            st.markdown("#### Revenue Contribution Split")
            fig_revenue = px.bar(
                segment_counts,
                x='customer_segment',
                y='total_revenue',
                text_auto='.2s',
                title="Total Revenue Contributed (R$)",
                color='customer_segment',
                color_discrete_map={'Returning Customer': '#1f77b4', 'One-Time Customer': '#aec7e8'},
                labels={'total_revenue': 'Total Revenue (R$)', 'customer_segment': 'Segment'},
                template='plotly_white'
            )
            fig_revenue.update_layout(showlegend=False)
            st.plotly_chart(fig_revenue, use_container_width=True)

        st.markdown("#### Geographic Loyalty Spread (Top States)")
        if 'customer_state' in filtered_retention.columns:
            state_segmentation = filtered_retention.groupby(['customer_state', 'customer_segment']).size().reset_index(name='customer_count')
            
            top_states = state_segmentation.groupby('customer_state')['customer_count'].sum().nlargest(10).index
            filtered_states = state_segmentation[state_segmentation['customer_state'].isin(top_states)]

            fig_state = px.bar(
                filtered_states,
                x='customer_state',
                y='customer_count',
                color='customer_segment',
                title="Top States Buyer Counts broken down by Loyalty",
                color_discrete_map={'Returning Customer': '#1f77b4', 'One-Time Customer': '#aec7e8'},
                labels={'customer_count': 'Number of Customers', 'customer_state': 'State Code'},
                barmode='stack',
                template='plotly_white'
            )
            st.plotly_chart(fig_state, use_container_width=True)
        else:
            st.info("State profiles column missing from retention structural dataset.")
    else:
        st.warning("No retention data available for the selected states.")

    st.divider()

    # 6. Fulfillment Distributions Section
    st.subheader("Fulfillment Distributions")

    col_chart1, col_chart2 = st.columns(2)
    
    with col_chart1:
        if 'delivery_delay_days' in filtered_fulfillment.columns:
            st.markdown("#### Delivery Delay Distribution vs SLA")
            fig_box = px.box(filtered_fulfillment, x='product_category_name', y='delivery_delay_days', color='product_category_name', template='plotly_white')
            fig_box.add_hline(y=0, line_dash="dash", line_color="crimson", annotation_text="SLA Target", annotation_position="top left")
            fig_box.update_layout(showlegend=False, xaxis_tickangle=-30)
            st.plotly_chart(fig_box, use_container_width=True)
        
    with col_chart2:
        if 'geo_distance_km' in filtered_fulfillment.columns and 'total_fulfillment_duration_days' in filtered_fulfillment.columns:
            st.markdown("#### Total Fulfillment Duration vs Corridor Distance")
            fig_scatter = px.scatter(filtered_fulfillment, x='geo_distance_km', y='total_fulfillment_duration_days', color='product_category_name', template='plotly_white')
            st.plotly_chart(fig_scatter, use_container_width=True)

    st.divider()

else:
    st.warning("Please select at least one product category from the filter menu sidebar.")