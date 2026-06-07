import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
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
@st.cache_data(ttl=86400)
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


# 2. Cached BigQuery Data Loading Functions
@st.cache_data(ttl=3600)
def load_fulfillment_data(selected_cats, selected_sts, start_month, end_month, use_mock_data=True):
    client = get_bigquery_client()
    
    start_date_str = f"{start_month}-01"
    end_date_str = f"{end_month}-01" 
    
    if use_mock_data:
        sql_query = """
        SELECT * FROM UNNEST([
            STRUCT('ord_A' AS order_id, 1 AS order_item_id, 101 AS customer_key, 201 AS seller_key, 301 AS product_key, 50.00 AS item_price_value, 9.99 AS freight_value, 5 AS order_rating, -2 AS delivery_delay_days, 1 AS pickup_delay_days, 5 AS total_fulfillment_duration_days, 120.5 AS geo_distance_km, 'alimentos_bebidas' AS product_category_name, 'SP' AS customer_state, CAST('2017-01-15' AS DATE) AS order_date),
            STRUCT('ord_B', 1, 101, 201, 302, 25.00, 4.50, 4, 1, 0, 7, 45.2, 'automotivo', 'SP', CAST('2017-01-20' AS DATE)),
            STRUCT('ord_C', 1, 102, 202, 303, 300.00, 15.00, 5, -5, 2, 10, 450.0, 'bebes', 'RJ', CAST('2017-02-10' AS DATE)),
            STRUCT('ord_D', 1, 103, 203, 304, 12.90, 5.00, 3, 4, 1, 14, 89.1, 'beleza_saude', 'MG', CAST('2017-02-18' AS DATE)),
            STRUCT('ord_E', 1, 104, 204, 305, 89.90, 12.30, 2, 0, 0, 6, 210.0, 'brinquedos', 'SP', CAST('2017-03-05' AS DATE))
        ])
        WHERE product_category_name IN UNNEST(@categories)
          AND order_date BETWEEN CAST(@start_d AS DATE) AND LAST_DAY(CAST(@end_d AS DATE))
        """
        if "All States" not in selected_sts and selected_sts:
            sql_query += " AND customer_state IN UNNEST(@states)"
            
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ArrayQueryParameter("categories", "STRING", selected_cats),
                bigquery.ArrayQueryParameter("states", "STRING", selected_sts),
                bigquery.ScalarQueryParameter("start_d", "STRING", start_date_str),
                bigquery.ScalarQueryParameter("end_d", "STRING", end_date_str)
            ]
        )
    else:
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
            d_order.date AS order_date,
            d_pay.date AS payment_date,
            d_order.year AS order_year,
            d_order.month AS order_month,
            d_order.day_of_week AS order_day_name,
            d_order.is_weekend AS order_is_weekend,
            p.product_category_name,
            p.product_type,
            c.state AS customer_state,
            s.state AS seller_state
        FROM `dsai-project-51420.olist_all.fact_order_fulfillment` AS f
        INNER JOIN `dsai-project-51420.olist_all.dim_product` AS p
            ON f.product_key = p.product_key
        INNER JOIN `dsai-project-51420.olist_all.dim_customer` AS c
            ON f.customer_key = c.customer_key
        LEFT JOIN `dsai-project-51420.olist_all.dim_seller` AS s
            ON f.seller_key = s.seller_key
        LEFT JOIN `dsai-project-51420.olist_all.dim_date` AS d_order
            ON f.order_date_key = d_order.date_key
        LEFT JOIN `dsai-project-51420.olist_all.dim_date` AS d_pay
            ON f.payment_date_key = d_pay.date_key
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
        
    df = client.query(sql_query, job_config=job_config).to_dataframe()
    
    date_columns = ['order_date', 'payment_date']
    for col in date_columns:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')
    return df

@st.cache_data(ttl=3600)
def load_retention_data(selected_sts, start_month, end_month, use_mock_data=True):
    client = get_bigquery_client()
    
    start_date_str = f"{start_month}-01"
    end_date_str = f"{end_month}-01"
    
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
                STRUCT('ord_A' AS order_id, 101 AS customer_key, 150.00 AS total_order_value, 5.0 AS order_rating, CAST('2017-03-15' AS DATE) AS order_date),
                STRUCT('ord_B', 101, 50.00, 4.0, CAST('2017-06-20' AS DATE) AS order_date),
                STRUCT('ord_C', 102, 300.00, 4.5, CAST('2017-08-11' AS DATE) AS order_date),
                STRUCT('ord_D', 103, 50.00, 3.0, CAST('2018-01-05' AS DATE) AS order_date)
            ])
            ),
            latest_customer_profile AS (
            SELECT customer_unique_id, customer_key, state AS customer_state
            FROM dim_customer_mock
            WHERE is_current = TRUE
            ),
            customer_metrics AS (
            SELECT 
                c.customer_unique_id,
                COUNT(DISTINCT f.order_id) AS total_orders,
                SUM(f.total_order_value) AS lifetime_order_value,
                AVG(f.order_rating) AS avg_rating
            FROM fact_order_summary_mock AS f
            JOIN dim_customer_mock AS c ON f.customer_key = c.customer_key
            WHERE f.order_date BETWEEN CAST(@start_d AS DATE) AND LAST_DAY(CAST(@end_d AS DATE))
            GROUP BY c.customer_unique_id
            )
            SELECT 
            m.customer_unique_id,
            p.customer_state,
            m.total_orders,
            ROUND(m.lifetime_order_value, 2) AS lifetime_order_value,
            ROUND(m.avg_rating, 2) AS avg_order_rating,
            CASE WHEN m.total_orders > 1 THEN 'Returning Customer' ELSE 'One-Time Customer' END AS customer_segment
            FROM customer_metrics AS m
            LEFT JOIN latest_customer_profile AS p ON m.customer_unique_id = p.customer_unique_id
            WHERE 1=1
        """
        if "All States" not in selected_sts and selected_sts:
            sql_query += " AND p.customer_state IN UNNEST(@states)"
            
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ArrayQueryParameter("states", "STRING", selected_sts),
                bigquery.ScalarQueryParameter("start_d", "STRING", start_date_str),
                bigquery.ScalarQueryParameter("end_d", "STRING", end_date_str)
            ]
        )
    else:
        sql_query = """
        WITH latest_customer_profile AS (
          SELECT 
            customer_unique_id,
            customer_key,
            state AS customer_state
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
            COUNT(DISTINCT f.order_id) AS total_orders,
            SUM(f.total_order_value) AS lifetime_order_value,
            AVG(f.order_rating) AS avg_rating
          FROM `dsai-project-51420.olist_all.fact_order_summary` AS f
          INNER JOIN latest_customer_profile AS c
            ON f.customer_key = c.customer_key
          INNER JOIN `dsai-project-51420.olist_all.dim_date` AS d
            ON f.order_date_key = d.date_key
          WHERE d.date BETWEEN CAST(@start_d AS DATE) AND LAST_DAY(CAST(@end_d AS DATE))
          GROUP BY c.customer_unique_id
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
        FROM customer_metrics AS m
        LEFT JOIN latest_customer_profile AS p
          ON m.customer_unique_id = p.customer_unique_id
        ORDER BY m.lifetime_order_value DESC;
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
st.sidebar.header("Filter Options")

categories, states, available_months = load_filter_options(use_mock_data=not data_mode)

default_start_month = "2017-01"
default_end_month = "2017-12"

if default_start_month not in available_months:
    default_start_month = available_months[0]
if default_end_month not in available_months:
    default_end_month = available_months[-1]

start_month, end_month = st.sidebar.select_slider(
    "Select Order Month Range",
    options=available_months,
    value=(default_start_month, default_end_month)
)

selected_categories = st.sidebar.multiselect(
    "Select Product Categories",
    options=categories,
    default=categories[:5] if len(categories) >= 5 else categories
)

selected_states = st.sidebar.multiselect(
    "Select Customer States",
    options=["All States"] + states,
    default="All States"
)

if not selected_categories:
    st.warning("Please choose at least one item from Product Categories.")
    st.stop()

with st.spinner("Fetching filtered data down from BigQuery..."):
    filtered_fulfillment = load_fulfillment_data(selected_categories, selected_states, start_month, end_month, use_mock_data=not data_mode)
    filtered_retention = load_retention_data(selected_states, start_month, end_month, use_mock_data=not data_mode)


# 4. App Memory Tracking Expansion
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

# 5. UI Elements Header
st.title("🚚 Olist Order Fulfillment & Customer Cohorts")
st.markdown("""This interactive dashboard analyzes logistics fulfillment, delivery delay metrics, 
and customer cohort behavior directly connected to the Google BigQuery data warehouse.""")
st.divider()

# Clean, Spaced 2x3 KPI Metrics Layout
st.subheader("Key Performance Indicators")

# Pre-calculations
total_orders = len(filtered_fulfillment)
avg_delay = filtered_fulfillment['delivery_delay_days'].mean() if total_orders > 0 and 'delivery_delay_days' in filtered_fulfillment.columns else 0
delayed_orders_pct = ((filtered_fulfillment['delivery_delay_days'] > 0).sum() / total_orders * 100) if total_orders > 0 and 'delivery_delay_days' in filtered_fulfillment.columns else 0
avg_freight = filtered_fulfillment['freight_value'].mean() if total_orders > 0 and 'freight_value' in filtered_fulfillment.columns else 0
avg_order_value = filtered_fulfillment['item_price_value'].mean() if total_orders > 0 and 'item_price_value' in filtered_fulfillment.columns else 0
avg_distance = filtered_fulfillment['geo_distance_km'].mean() if total_orders > 0 and 'geo_distance_km' in filtered_fulfillment.columns else 0

# Row 1: Volume & Delay Metrics
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

# Row 2: Financial & Distance Metrics
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

# Main Filter Validation Conditional Check
if not filtered_fulfillment.empty:
    
    # 6. Customer Retention Layout Section
    st.subheader("👤 Customer Retention & Lifetime Value Analysis")
    if not filtered_retention.empty:
        cust_col1, cust_col2 = st.columns(2)
        with cust_col1:
            st.markdown("#### Proportion of Customer Base")
            segment_counts = filtered_retention.groupby('customer_segment').agg(
                customer_count=('customer_unique_id', 'count'),
                total_revenue=('lifetime_order_value', 'sum')
            ).reset_index()

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
                filtered_states, x='customer_state', y='customer_count', color='customer_segment',
                title="Top States Buyer Counts broken down by Loyalty",
                color_discrete_map=PALETTE_COHORTS,
                labels={'customer_count': 'Number of Customers', 'customer_state': 'State Code'},
                barmode='stack', template='plotly_white'
            )
            st.plotly_chart(fig_state, use_container_width=True)
    else:
        st.warning("No retention data available for the selected states and date filters.")

    st.divider()
    
    # 7. Fulfillment Distributions Section
    st.subheader("Fulfillment Distributions")
    col_chart1, col_chart2 = st.columns(2)
    
    with col_chart1:
        if 'delivery_delay_days' in filtered_fulfillment.columns:
            st.markdown("#### Delivery Delay Distribution vs SLA")
            fig_box = px.box(
                filtered_fulfillment, x='product_category_name', y='delivery_delay_days', 
                color_discrete_sequence=[COLOR_PRIMARY_BLUE], template='plotly_white'
            )
            fig_box.add_hline(y=0, line_dash="dash", line_color=COLOR_ALERT_CRIMSON, annotation_text="SLA Target", annotation_position="top left")
            fig_box.update_layout(showlegend=False, xaxis_tickangle=-30)
            st.plotly_chart(fig_box, use_container_width=True)
        
    with col_chart2:
        if 'geo_distance_km' in filtered_fulfillment.columns and 'total_fulfillment_duration_days' in filtered_fulfillment.columns:
            st.markdown("#### Total Fulfillment Duration vs Corridor Distance")
            fig_scatter = px.scatter(
                filtered_fulfillment, x='geo_distance_km', y='total_fulfillment_duration_days', 
                color_discrete_sequence=[COLOR_PRIMARY_BLUE], template='plotly_white', opacity=0.6
            )
            st.plotly_chart(fig_scatter, use_container_width=True)

    st.divider()

    # 8. Delivery Delay Timeline Analysis Section
    st.subheader("📊 Delivery Delay Timeline Analysis")
    
    if 'delivery_delay_days' in filtered_fulfillment.columns:
        fig_hist = px.histogram(
            filtered_fulfillment,
            x='delivery_delay_days',
            nbins=100,
            title='Chart 1: Distribution of Order Delivery Delay (Days)',
            labels={'delivery_delay_days': 'Delivery Delay (Days) -> Positive means Late', 'count': 'Count of Orders'},
            color_discrete_sequence=[COLOR_PRIMARY_BLUE],
            template='plotly_white'
        )
        
        fig_hist.update_layout(
            xaxis_range=[-60, 60],
            yaxis_title='Count of Orders',
            showlegend=False,
            title_font_size=14
        )
        
        fig_hist.add_vline(
            x=0, 
            line_dash="dash", 
            line_color=COLOR_ALERT_CRIMSON, 
            line_width=1.5,
            annotation_text="Promised Delivery Date",
            annotation_position="top left"
        )
        
        st.plotly_chart(fig_hist, use_container_width=True)
        
        late_orders = filtered_fulfillment[filtered_fulfillment['delivery_delay_days'] > 0]
        pct_late = (len(late_orders) / total_orders) * 100 if total_orders > 0 else 0
        
        st.info(f"💡 **Fulfillment Insight:** Percentage of evaluated orders delivered late: **{pct_late:.2f}%**")
    else:
        st.warning("Unable to generate delay distribution timeline metric constraints.")

    st.divider()

    # 9. Correlation Analysis Section
    st.subheader("🔗 Operational Variables Correlation Matrix")
    
    corr_columns = ['delivery_delay_days', 'pickup_delay_days', 'item_price_value', 'freight_value', 'order_rating']
    available_corr_cols = [col for col in corr_columns if col in filtered_fulfillment.columns]
    
    if len(available_corr_cols) > 1:
        corr_matrix = filtered_fulfillment[available_corr_cols].corr()
        
        fig_heat = px.imshow(
            corr_matrix,
            text_auto='.2f',
            color_continuous_scale='Blues', 
            zmin=-1.0,
            zmax=1.0,
            title='Chart 8: Correlation Matrix: Delays, Logistics Costs, and Ratings',
            labels=dict(color="Correlation Coefficient"),
            template='plotly_white'
        )
        
        fig_heat.update_layout(
            title_font_size=14,
            width=700,
            height=600
        )
        
        st.plotly_chart(fig_heat, use_container_width=True)
    else:
        st.warning("Insufficient numeric features available to generate correlation mappings.")

    st.divider()

    # 10. Monthly Order Volume vs. Delivery Delay Percentiles (Dual Axis Plotly Chart)
    st.subheader("📈 Monthly Performance Tendencies & Percentiles")
    
    if 'order_date' in filtered_fulfillment.columns and 'delivery_delay_days' in filtered_fulfillment.columns:
        timeline_df = filtered_fulfillment.copy()
        timeline_df['date'] = timeline_df['order_date'].dt.to_period('M').dt.to_timestamp()
        
        monthly_stats = timeline_df.groupby('date').agg(
            p90=('delivery_delay_days', lambda x: x.quantile(0.90)),
            p75=('delivery_delay_days', lambda x: x.quantile(0.75)),
            p50=('delivery_delay_days', lambda x: x.quantile(0.50)),
            p25=('delivery_delay_days', lambda x: x.quantile(0.25)),
            p10=('delivery_delay_days', lambda x: x.quantile(0.10)),
            order_count=('order_id', 'count')
        ).reset_index()
        
        monthly_stats = monthly_stats.sort_values('date')
        
        fig_dual = go.Figure()
        
        fig_dual.add_trace(
            go.Bar(
                x=monthly_stats['date'],
                y=monthly_stats['order_count'],
                name='Order Volume',
                marker_color=COLOR_BACKGROUND_GRAY,
                yaxis='y1'
            )
        )
        
        fig_dual.add_trace(go.Scatter(x=monthly_stats['date'], y=monthly_stats['p90'], name='90th Pctl (Late Risk)', line=dict(color=COLOR_ALERT_CRIMSON, width=2), mode='lines+markers', yaxis='y2'))
        fig_dual.add_trace(go.Scatter(x=monthly_stats['date'], y=monthly_stats['p75'], name='75th Pctl', line=dict(color=COLOR_MUTED_SLATE, width=1.5, dash='dash'), mode='lines+markers', yaxis='y2'))
        fig_dual.add_trace(go.Scatter(x=monthly_stats['date'], y=monthly_stats['p50'], name='50th Pctl (Median)', line=dict(color=COLOR_PRIMARY_BLUE, width=2.5), mode='lines+markers', yaxis='y2'))
        fig_dual.add_trace(go.Scatter(x=monthly_stats['date'], y=monthly_stats['p25'], name='25th Pctl', line=dict(color=COLOR_MUTED_SLATE, width=1.5, dash='dash'), mode='lines+markers', yaxis='y2'))
        fig_dual.add_trace(go.Scatter(x=monthly_stats['date'], y=monthly_stats['p10'], name='10th Pctl', line=dict(color=COLOR_DARK_BLUE, width=2), mode='lines+markers', yaxis='y2'))
        
        fig_dual.update_layout(
            title='Chart 11: Monthly Order Volume vs. Delivery Delay Percentiles (2016-2018)',
            title_font_size=16,
            template='plotly_white',
            xaxis=dict(
                title=dict(text='Date'), 
                type='date', 
                tickformat='%Y-%m', 
                tickangle=-90,
                tickmode='linear',
                dtick='M1'
            ),
            yaxis=dict(
                title=dict(text='Order Volume', font=dict(color=COLOR_MUTED_SLATE)), 
                tickfont=dict(color=COLOR_MUTED_SLATE)
            ),
            yaxis2=dict(
                title=dict(text='Delivery Delay (Days)', font=dict(color='black')), 
                tickfont=dict(color='black'), 
                overlaying='y', 
                side='right'
            ),
            legend=dict(x=0.01, y=0.99, bgcolor='rgba(255,255,255,0.8)', bordercolor=COLOR_BACKGROUND_GRAY, borderwidth=1),
            height=600
        )
        
        st.plotly_chart(fig_dual, use_container_width=True)
    else:
        st.warning("Temporal data missing. Unable to map transaction timelines.")

    st.divider()

    # 11. Top Product Categories Delay Distribution (Box Plot)
    st.subheader("📦 Detailed Fulfillment Distribution by Product Category")
    
    if 'product_category_name' in filtered_fulfillment.columns and 'delivery_delay_days' in filtered_fulfillment.columns:
        top_cats = filtered_fulfillment['product_category_name'].value_counts().index[:10]
        boxed_df = filtered_fulfillment[filtered_fulfillment['product_category_name'].isin(top_cats)]
        
        if not boxed_df.empty:
            fig_cat_box = px.box(
                boxed_df,
                x='product_category_name',
                y='delivery_delay_days',
                color='product_category_name',
                category_orders={"product_category_name": top_cats.tolist()},
                color_discrete_sequence=PALETTE_CATEGORIES, 
                title='Chart 17: Delivery Delay Distribution by Top Product Categories',
                labels={
                    'product_category_name': 'Product Category',
                    'delivery_delay_days': 'Delivery Delay (Days vs SLA)'
                },
                template='plotly_white'
            )
            
            fig_cat_box.add_hline(
                y=0, 
                line_dash="dash", 
                line_color=COLOR_ALERT_CRIMSON, 
                line_width=1.5, 
                annotation_text="SLA Target Guideline", 
                annotation_position="top left"
            )
            
            fig_cat_box.update_layout(
                title_font_size=15,
                xaxis=dict(tickangle=-30),
                showlegend=False, 
                height=600
            )
            
            st.plotly_chart(fig_cat_box, use_container_width=True)
        else:
            st.warning("No tracking records matched top category metrics constraints.")
    else:
        st.warning("Required parameters unavailable for category distribution mapping.")

else:
    st.warning("No records found matching the selected month range and criteria.")