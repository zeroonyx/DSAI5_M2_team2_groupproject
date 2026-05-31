# DSAI Chohort 5 Module 2 Group Project

## Data Engineering and EDA
This project applies core Data Engineering principles alongside Exploratory Data Analysis (EDA) to solve real-world e-commerce challenges using the Olist dataset. 

The pipeline follows a structured data lifecycle, transitioning raw data through a Medallion Architecture into clean Kimball-style Dimensional Models (Facts and Dimensions) optimized for business intelligence and deep analytical exploration.

## Team Members:
*in alphabetical order by last name*

* Li Zhongyi (Ethan)
* Lin Minghui (Reeve)
* Mao Jianwen (Tony)
* Nainar Mohideen (Nainar)
* Wang Her Suen (Tom)
* Yang Shicong (Shicong)

## Problem Statements

Olist’s market competitiveness and customer retention are currently threatened by recurring delivery delays across its unified logistics network in Brazil. 

The core operational challenge lies in the team's inability to isolate whether these bottlenecks occur during initial seller processing hours or during carrier transit. 

To protect customer loyalty and maintain operational continuity, Olist needs to analyze transit days variance, seller processing lag, and regional late severity scores. 

Pinpointing these exact failure points will allow the operations team to establish a concrete governance framework, enforce strict carrier service level agreements, and hold low performing sellers accountable without disrupting daily supply chain flows.


| Project Topic | Context | Problem Statement | Analysis | Business Outcome |
| :--- | :--- | :--- | :--- | :--- |
| **Delivery Performance Optimization** | Olist connects small businesses across Brazil through a unified logistics network, managing multiple shipping carriers and thousands of independent sellers. | Delivery delays hurt customer retention, but the operations team cannot isolate whether delays happen during seller fulfillment or carrier transit. | • Transit days variance<br>• Seller processing lag (hours)<br>• Late severity score per region | **Market Competitiveness & Operational Continuity:** Secures Olist’s market positioning by protecting customer retention. Establishes a concrete governance framework to hold low-performing carriers accountable via SLAs and penalize bottleneck sellers without disrupting daily supply chain flows. |

---

## Solution Overview

```mermaid
%%{init: { 
  'theme': 'base', 
  'themeVariables': { 
    'background': '#ffffff', 
    'primaryColor': '#ffffff', 
    'lineColor': '#4a5568', 
    'tertiaryColor': '#ffffff'
  } 
}}%%
graph TD
    %% Distinct sub level (subgraph) styling
    style Src fill:#eff6ff,stroke:#3b82f6,stroke-width:1.5px;
    style Ingest fill:#fef3c7,stroke:#d97706,stroke-width:1.5px;
    style Warehouse fill:#ecfdf5,stroke:#059669,stroke-width:1.5px;
    style Serving fill:#faf5ff,stroke:#7c3aed,stroke-width:1.5px;

    %% Consistent node styling
    classDef default fill:#ffffff,stroke:#4a5568,stroke-width:1px;

    %% 1. Source Systems
    subgraph Src [OLTP Data Sources]
        A[(Operational Database)]
    end

    %% 2. Ingestion Pipeline
    subgraph Ingest [Data Extraction & Loading]
        B[Meltano Pipeline]
    end

    %% 3. Simplified Unified Warehouse
    subgraph Warehouse [Analytical Storage Engine: GCP]
    direction LR
        C[(LandingZone)]
        C -->|<font color='#059669'>dbt SQL </font>| D[(Staging Layer)]
        D -->|<font color='#059669'>Kimball Dimension</font>| E[(Data Marts)]
    end

    %% 4. Access
    subgraph Serving [Analytical Serving Layer]
        F[Exploratory Data Analysis<br>BI Dashboards]
    end

    %% Cross Subgraph Connections pointing directly to the subgraphs
    Src -->|<font color='#3b82f6'>Protocol: REST API<br>Format: JSON</font>| Ingest
    Ingest -->|<font color='#d97706'>Protocol: Database API<br>Format: Parquet</font>| Warehouse
    Warehouse -->|<font color='#059669'>Protocol: Database Driver <br>Format: Columnar</font>| Serving

    %% Output
    Serving -->|<font color='#7c3aed'>Visualization</font>| L([Project Stakeholders])

    %% Colored link assignments for clear connection levels
    %% Internal Warehouse link (C to D)
    linkStyle 0 stroke:#059669,stroke-width:1.5px; 
    %% Internal Warehouse link (D to E)
    linkStyle 1 stroke:#059669,stroke-width:1.5px; 
    %% Connection from Src subgraph to Ingest subgraph
    linkStyle 2 stroke:#3b82f6,stroke-width:2px; 
    %% Connection from Ingest subgraph to Warehouse subgraph
    linkStyle 3 stroke:#d97706,stroke-width:2px; 
    %% Connection from Warehouse subgraph to Serving subgraph
    linkStyle 4 stroke:#059669,stroke-width:2px; 
    %% Connection from Serving subgraph to Stakeholders
    linkStyle 5 stroke:#7c3aed,stroke-width:2px;
```
---

## 🛠️ Data Engineering (The Pipeline)
* **[Data Ingestion & Storage](2.1-meltano.ipynb):** Establishing the landing zone for raw operational data into the **Bronze** warehouse layer.
* **[Data Warehouse Design](2.2-dimension-model.md):** Enforcing the Kimball framework by designing dedicated Fact and Dimension tables, and arrive at star schema.
* **[ELT Pipeline (dbt)](2.4-dbt-doc.md):** Processing, cleaning, and normalizing data into **Silver** models before building the final **Gold** layer.

## 📊 Exploratory Data Analysis (The Insights)
* **[Data Quality Validation](2.3-dbt.ipynb):** Writing profiling scripts to ensure data types match, null boundaries are respected, and data engineering logic functions correctly under real-world scenarios.
* **[Data Analysis](3.1-olist-fulfillment-eda.ipynb):** Investigating distributions, correlation metrics (e.g., delivery delay impact on review scores), and behavior variance across distinct regions.
* **[Business Insights](3.2-business-insights.md):** Converting modeled tables into structured visualizations, dashboards, and reports that directly inform the strategies of the Accountable (A) project stakeholders.

---

## Project Work Breakdown Structure (WBS) & Progress Tracker

| WBS Code | Phase / Work Package | Task Description | Technical Deliverable | Status |
| :--- | :--- | :--- | :--- | :--- |
| **1.0** | **Project Initiation** | **Foundation and environment configuration** | **Infrastructure Baseline** | - |
| 1.1 | Environment Setup | Initialize GitHub repository, configure local dbt profiles, and establish active data warehouse connections. | Shared Git repository and active warehouse connection | [X] |
| 1.2 | Source Data Preparation | Prepare raw operational data tables in Supabase. | [Source Data in Supabase](1.2-supabase-setup.md) | [X] |
| 1.3 | Topic Selection | Choose and finalize the specific business problem statement from the four proposed Olist tracks. | Delivery Delay Analysis | [X] |
| **2.0** | **Data Pipeline** | **Building the Bronze, Silver, and Gold data layers** | **Data Engineering Track** | - |
| 2.1 | Data Ingestion (Meltano) | Configure Meltano pipelines to extract from Supabase and Load into GCP. | [Meltano EL notebook](2.1-meltano.ipynb) | [X] |
| 2.2 | Data Warehouse (Star Schema) | Organize data into facts and dimension tables, adopt SCD Type 1 and Type 2 | [Dimension Model](2.2-dimension-model.md)| [X] |
| 2.3 | Data Mart (dbt) |  Transform raw data into organized tables using dbt, remove deduplicate records, clean null values, and standardize basic data types. | [dbt](2.3-dbt.ipynb) | [X] |
| 2.4 | Data Quality Testing | Deploy dbt tests for uniqueness, non null values, and referential integrity while auto generating the data catalog. Execute analytical data profiling scripts to stress test dimensional boundaries and validate engineering logic | [lineage diagram](2.4-dbt-doc.md) | [X] |
| **3.0** | **Exploratory Data Analysis (EDA)** | **Validating quality and extracting analytical trends** | **Analytics Track** | - |
| 3.1 | Data Analysis | Investigate data distributions, calculate target metric correlations, and analyze regional behavior variances. | [Jupyter Notebooks](3.1-olist-fulfillment-eda.ipynb) | [X] |
| 3.2 | Deep Dive Business Insights | Extract actionable intelligence that explicitly answers the core metrics of the chosen problem statement. | [Documented analytical insights](3.2-business-insights.md) | [X] |
| **4.0** | **Documentation and Presentation** | **Translating data models into stakeholder value** | **Presentation & Interface** | - |
| 4.1 | Project Documentation | Finalize the comprehensive GitHub README outlining the system architecture, dbt models, and analytical outcomes. | [Project Document](README.md) | [X] |
| 4.3 | Stakeholder Presentation | Present architecture and recommendations to executives. | Final presentation deck | [ ] |


## Next Step

### Pipeline Orchestration

it's not included in this project yet.  Next step is to use an automation tool to manage the steps of your pipeline from start to finish.

Set up a schedule so your data updates and quality checks run automatically.
Options for scheduling include (not limited to):
* Orchestration tools (Dagster, Airflow, etc.) 
* Managed service (e.g., Google Cloud Composer) 
* Cron jobs
* CICD via GitHub Actions