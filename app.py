import os
from datetime import datetime
import requests
import pandas as pd
import streamlit as st
import plotly.express as px
from notion_client import Client


# -------------------------------------------------
# Page setup
# -------------------------------------------------
st.set_page_config(
    page_title="Kathryn's LEGO Inventory",
    page_icon="🧱",
    layout="wide"
)

st.title("🧱 Kathryn's LEGO Inventory")


# -------------------------------------------------
# Secrets
# -------------------------------------------------
BRICKSET_API_KEY = st.secrets["BRICKSET_API_KEY"]
BRICKSET_USER_HASH = st.secrets["BRICKSET_USER_HASH"]

NOTION_TOKEN = st.secrets["NOTION_TOKEN"]
NOTION_DATABASE_ID = st.secrets["NOTION_DATABASE_ID"]

notion = Client(auth=NOTION_TOKEN)

BRICKSET_URL = "https://brickset.com/api/v3.asmx/getSets"


# -------------------------------------------------
# Helpers
# -------------------------------------------------
def normalize_set_number(set_number: str) -> str:
    set_number = str(set_number).strip()
    if "-" not in set_number:
        set_number = f"{set_number}-1"
    return set_number


def safe_number(value, default=0):
    try:
        if value in [None, "", "None"]:
            return default
        return int(float(value))
    except Exception:
        return default


def safe_float(value, default=0.0):
    try:
        if value in [None, "", "None"]:
            return default
        return float(value)
    except Exception:
        return default


def get_text(prop):
    try:
        return prop["rich_text"][0]["plain_text"]
    except Exception:
        return ""


def get_title(prop):
    try:
        return prop["title"][0]["plain_text"]
    except Exception:
        return ""


def get_select(prop):
    try:
        return prop["select"]["name"]
    except Exception:
        return ""


def get_number(prop):
    try:
        return prop["number"] or 0
    except Exception:
        return 0


def get_url(prop):
    try:
        return prop["url"] or ""
    except Exception:
        return ""


# -------------------------------------------------
# Brickset lookup
# -------------------------------------------------
@st.cache_data(show_spinner=False)
def lookup_brickset_set(set_number):
    set_number = normalize_set_number(set_number)

    params = {
        "apiKey": BRICKSET_API_KEY,
        "userHash": BRICKSET_USER_HASH,
        "params": f'{{"setNumber":"{set_number}"}}'
    }

    response = requests.get(BRICKSET_URL, params=params, timeout=20)

    if response.status_code != 200:
        return None, f"Brickset request failed with status code {response.status_code}."

    data = response.json()

    if data.get("status") != "success":
        return None, data.get("message", "Unknown Brickset error.")

    sets = data.get("sets", [])

    if not sets:
        return None, "No set found."

    result = sets[0]

    clean = {
        "Set Number": result.get("number", set_number),
        "Set Name": result.get("name", ""),
        "Theme": result.get("theme", ""),
        "Subtheme": result.get("subtheme", ""),
        "Year": safe_number(result.get("year")),
        "Pieces": safe_number(result.get("pieces")),
        "Minifigs": safe_number(result.get("minifigs")),
        "Retail Price": safe_float(
            result.get("LEGOCom", {})
            .get("US", {})
            .get("retailPrice", 0)
        ),
        "Image URL": result.get("image", {}).get("imageURL", ""),
        "Brickset URL": result.get("bricksetURL", "")
    }

    return clean, None


# -------------------------------------------------
# Notion functions
# -------------------------------------------------
def notion_page_to_record(page):
    props = page["properties"]

    return {
        "Page ID": page["id"],
        "Set Name": get_title(props.get("Set Name", {})),
        "Set Number": get_text(props.get("Set Number", {})),
        "Theme": get_select(props.get("Theme", {})),
        "Subtheme": get_select(props.get("Subtheme", {})),
        "Year": get_number(props.get("Year", {})),
        "Pieces": get_number(props.get("Pieces", {})),
        "Minifigs": get_number(props.get("Minifigs", {})),
        "Quantity": get_number(props.get("Quantity", {})),
        "Condition": get_select(props.get("Condition", {})),
        "Status": get_select(props.get("Status", {})),
        "Purchase Price": get_number(props.get("Purchase Price", {})),
        "Retail Price": get_number(props.get("Retail Price", {})),
        "Image URL": get_url(props.get("Image URL", {})),
        "Brickset URL": get_url(props.get("Brickset URL", {})),
        "Notes": get_text(props.get("Notes", {})),
    }


def load_inventory_from_notion():
    records = []
    start_cursor = None

    while True:
        response = notion.databases.query(
            database_id=NOTION_DATABASE_ID,
            start_cursor=start_cursor
        )

        for page in response["results"]:
            records.append(notion_page_to_record(page))

        if not response.get("has_more"):
            break

        start_cursor = response.get("next_cursor")

    return pd.DataFrame(records)


def find_existing_set_page(set_number):
    set_number = normalize_set_number(set_number)

    response = notion.databases.query(
        database_id=NOTION_DATABASE_ID,
        filter={
            "property": "Set Number",
            "rich_text": {
                "equals": set_number
            }
        }
    )

    results = response.get("results", [])

    if results:
        return results[0]["id"]

    return None


def build_notion_properties(record):
    return {
        "Set Name": {
            "title": [
                {
                    "text": {
                        "content": record.get("Set Name", "")
                    }
                }
            ]
        },
        "Set Number": {
            "rich_text": [
                {
                    "text": {
                        "content": normalize_set_number(record.get("Set Number", ""))
                    }
                }
            ]
        },
        "Theme": {
            "select": {
                "name": record.get("Theme", "Unknown") or "Unknown"
            }
        },
        "Subtheme": {
            "select": {
                "name": record.get("Subtheme", "None") or "None"
            }
        },
        "Year": {
            "number": safe_number(record.get("Year"))
        },
        "Pieces": {
            "number": safe_number(record.get("Pieces"))
        },
        "Minifigs": {
            "number": safe_number(record.get("Minifigs"))
        },
        "Quantity": {
            "number": safe_number(record.get("Quantity"), 1)
        },
        "Condition": {
            "select": {
                "name": record.get("Condition", "Owned") or "Owned"
            }
        },
        "Status": {
            "select": {
                "name": record.get("Status", "Owned") or "Owned"
            }
        },
        "Purchase Price": {
            "number": safe_float(record.get("Purchase Price"))
        },
        "Retail Price": {
            "number": safe_float(record.get("Retail Price"))
        },
        "Image URL": {
            "url": record.get("Image URL", "") or None
        },
        "Brickset URL": {
            "url": record.get("Brickset URL", "") or None
        },
        "Notes": {
            "rich_text": [
                {
                    "text": {
                        "content": record.get("Notes", "") or ""
                    }
                }
            ]
        },
        "Last Synced": {
            "date": {
                "start": datetime.now().isoformat()
            }
        }
    }


def save_set_to_notion(record):
    set_number = normalize_set_number(record["Set Number"])
    existing_page_id = find_existing_set_page(set_number)

    properties = build_notion_properties(record)

    if existing_page_id:
        notion.pages.update(
            page_id=existing_page_id,
            properties=properties
        )
        return "updated"

    notion.pages.create(
        parent={"database_id": NOTION_DATABASE_ID},
        properties=properties
    )

    return "created"


def sync_inventory_with_brickset(df):
    updated_count = 0

    for _, row in df.iterrows():
        set_number = row.get("Set Number", "")

        if not set_number:
            continue

        brickset_data, error = lookup_brickset_set(set_number)

        if error or not brickset_data:
            continue

        updated_record = row.to_dict()

        for key in [
            "Set Name",
            "Theme",
            "Subtheme",
            "Year",
            "Pieces",
            "Minifigs",
            "Retail Price",
            "Image URL",
            "Brickset URL"
        ]:
            updated_record[key] = brickset_data.get(key, updated_record.get(key, ""))

        save_set_to_notion(updated_record)
        updated_count += 1

    return updated_count


# -------------------------------------------------
# Sidebar: Add new set
# -------------------------------------------------
st.sidebar.header("Add New LEGO Set")

lookup_number = st.sidebar.text_input("Set Number", placeholder="Example: 10305")

if st.sidebar.button("Look Up from Brickset"):
    if lookup_number.strip():
        result, error = lookup_brickset_set(lookup_number)

        if error:
            st.sidebar.error(error)
        else:
            st.session_state["brickset_result"] = result
            st.sidebar.success("Set found!")
    else:
        st.sidebar.warning("Enter a set number first.")


brickset_result = st.session_state.get("brickset_result", {})

with st.sidebar.form("add_set_form"):
    set_number = st.text_input(
        "Set Number",
        value=brickset_result.get("Set Number", "")
    )

    set_name = st.text_input(
        "Set Name",
        value=brickset_result.get("Set Name", "")
    )

    theme = st.text_input(
        "Theme",
        value=brickset_result.get("Theme", "")
    )

    subtheme = st.text_input(
        "Subtheme",
        value=brickset_result.get("Subtheme", "")
    )

    year = st.number_input(
        "Year",
        min_value=1950,
        max_value=2100,
        value=safe_number(brickset_result.get("Year"), 2024),
        step=1
    )

    pieces = st.number_input(
        "Pieces",
        min_value=0,
        value=safe_number(brickset_result.get("Pieces")),
        step=1
    )

    minifigs = st.number_input(
        "Minifigs",
        min_value=0,
        value=safe_number(brickset_result.get("Minifigs")),
        step=1
    )

    quantity = st.number_input("Quantity", min_value=1, value=1, step=1)

    condition = st.selectbox(
        "Condition",
        [
            "New Sealed",
            "New Open Box",
            "Used Complete",
            "Used Incomplete",
            "Built",
            "Parts Only"
        ]
    )

    status = st.selectbox(
        "Status",
        [
            "Owned",
            "Wishlist",
            "Ordered",
            "Built",
            "Sold",
            "Missing Pieces"
        ]
    )

    purchase_price = st.number_input(
        "Purchase Price",
        min_value=0.00,
        value=0.00,
        step=1.00
    )

    retail_price = st.number_input(
        "Retail Price",
        min_value=0.00,
        value=safe_float(brickset_result.get("Retail Price")),
        step=1.00
    )

    image_url = st.text_input(
        "Image URL",
        value=brickset_result.get("Image URL", "")
    )

    brickset_url = st.text_input(
        "Brickset URL",
        value=brickset_result.get("Brickset URL", "")
    )

    notes = st.text_area("Notes")

    submitted = st.form_submit_button("Save to Notion")


if submitted:
    record = {
        "Set Number": normalize_set_number(set_number),
        "Set Name": set_name,
        "Theme": theme,
        "Subtheme": subtheme,
        "Year": year,
        "Pieces": pieces,
        "Minifigs": minifigs,
        "Quantity": quantity,
        "Condition": condition,
        "Status": status,
        "Purchase Price": purchase_price,
        "Retail Price": retail_price,
        "Image URL": image_url,
        "Brickset URL": brickset_url,
        "Notes": notes
    }

    action = save_set_to_notion(record)

    if action == "created":
        st.success(f"Added {record['Set Number']} - {record['Set Name']} to Notion.")
    else:
        st.success(f"Updated {record['Set Number']} - {record['Set Name']} in Notion.")

    st.cache_data.clear()

    if "brickset_result" in st.session_state:
        del st.session_state["brickset_result"]


# -------------------------------------------------
# Load data
# -------------------------------------------------
try:
    df = load_inventory_from_notion()
except Exception as e:
    st.error("Could not load your Notion database.")
    st.exception(e)
    st.stop()


if df.empty:
    st.info("Your inventory is empty. Add your first set from the sidebar.")
    st.stop()


# -------------------------------------------------
# Auto-sync button
# -------------------------------------------------
sync_col1, sync_col2 = st.columns([1, 4])

with sync_col1:
    if st.button("🔄 Sync with Brickset"):
        count = sync_inventory_with_brickset(df)
        st.success(f"Synced {count} sets with Brickset.")
        st.cache_data.clear()
        st.rerun()

with sync_col2:
    st.caption("Sync updates set name, theme, subtheme, year, pieces, minifigs, retail price, image URL, and Brickset URL.")


# -------------------------------------------------
# Dashboard metrics
# -------------------------------------------------
st.subheader("Collection Dashboard")

df["Quantity"] = pd.to_numeric(df["Quantity"], errors="coerce").fillna(0)
df["Pieces"] = pd.to_numeric(df["Pieces"], errors="coerce").fillna(0)
df["Purchase Price"] = pd.to_numeric(df["Purchase Price"], errors="coerce").fillna(0)
df["Retail Price"] = pd.to_numeric(df["Retail Price"], errors="coerce").fillna(0)
df["Year"] = pd.to_numeric(df["Year"], errors="coerce").fillna(0)

df["Total Pieces"] = df["Pieces"] * df["Quantity"]
df["Total Purchase Value"] = df["Purchase Price"] * df["Quantity"]
df["Total Retail Value"] = df["Retail Price"] * df["Quantity"]

unique_sets = len(df)
total_sets = int(df["Quantity"].sum())
total_pieces = int(df["Total Pieces"].sum())
total_spend = df["Total Purchase Value"].sum()
total_retail = df["Total Retail Value"].sum()

col1, col2, col3, col4, col5 = st.columns(5)

col1.metric("Unique Sets", f"{unique_sets:,}")
col2.metric("Total Sets", f"{total_sets:,}")
col3.metric("Total Pieces", f"{total_pieces:,}")
col4.metric("Total Spend", f"${total_spend:,.2f}")
col5.metric("Retail Value", f"${total_retail:,.2f}")


# -------------------------------------------------
# Filters
# -------------------------------------------------
st.subheader("Search & Filter")

filter_col1, filter_col2, filter_col3 = st.columns(3)

with filter_col1:
    search = st.text_input("Search")

with filter_col2:
    theme_options = ["All"] + sorted(df["Theme"].dropna().unique().tolist())
    selected_theme = st.selectbox("Theme", theme_options)

with filter_col3:
    status_options = ["All"] + sorted(df["Status"].dropna().unique().tolist())
    selected_status = st.selectbox("Status", status_options)


filtered_df = df.copy()

if search:
    filtered_df = filtered_df[
        filtered_df.astype(str).apply(
            lambda row: row.str.contains(search, case=False, na=False).any(),
            axis=1
        )
    ]

if selected_theme != "All":
    filtered_df = filtered_df[filtered_df["Theme"] == selected_theme]

if selected_status != "All":
    filtered_df = filtered_df[filtered_df["Status"] == selected_status]


# -------------------------------------------------
# Charts
# -------------------------------------------------
st.subheader("Analytics")

chart_col1, chart_col2 = st.columns(2)

with chart_col1:
    theme_counts = (
        filtered_df.groupby("Theme")["Quantity"]
        .sum()
        .reset_index()
        .sort_values("Quantity", ascending=False)
    )

    fig_theme = px.bar(
        theme_counts,
        x="Theme",
        y="Quantity",
        title="Sets by Theme"
    )

    st.plotly_chart(fig_theme, use_container_width=True)

with chart_col2:
    year_counts = (
        filtered_df.groupby("Year")["Quantity"]
        .sum()
        .reset_index()
        .sort_values("Year")
    )

    fig_year = px.line(
        year_counts,
        x="Year",
        y="Quantity",
        markers=True,
        title="Sets by Release Year"
    )

    st.plotly_chart(fig_year, use_container_width=True)


chart_col3, chart_col4 = st.columns(2)

with chart_col3:
    status_counts = (
        filtered_df.groupby("Status")["Quantity"]
        .sum()
        .reset_index()
        .sort_values("Quantity", ascending=False)
    )

    fig_status = px.pie(
        status_counts,
        names="Status",
        values="Quantity",
        title="Inventory by Status"
    )

    st.plotly_chart(fig_status, use_container_width=True)

with chart_col4:
    value_by_theme = (
        filtered_df.groupby("Theme")["Total Retail Value"]
        .sum()
        .reset_index()
        .sort_values("Total Retail Value", ascending=False)
    )

    fig_value = px.bar(
        value_by_theme,
        x="Theme",
        y="Total Retail Value",
        title="Retail Value by Theme"
    )

    st.plotly_chart(fig_value, use_container_width=True)


# -------------------------------------------------
# Inventory table
# -------------------------------------------------
st.subheader("Inventory Table")

display_columns = [
    "Set Number",
    "Set Name",
    "Theme",
    "Subtheme",
    "Year",
    "Pieces",
    "Minifigs",
    "Quantity",
    "Condition",
    "Status",
    "Purchase Price",
    "Retail Price",
    "Brickset URL"
]

st.dataframe(
    filtered_df[display_columns],
    use_container_width=True,
    hide_index=True
)


# -------------------------------------------------
# Gallery
# -------------------------------------------------
st.subheader("Set Gallery")

for _, row in filtered_df.iterrows():
    with st.expander(f"{row['Set Number']} — {row['Set Name']}"):
        img_col, info_col = st.columns([1, 3])

        with img_col:
            if row.get("Image URL"):
                st.image(row["Image URL"], use_container_width=True)

        with info_col:
            st.write(f"**Theme:** {row['Theme']}")
            st.write(f"**Subtheme:** {row['Subtheme']}")
            st.write(f"**Year:** {int(row['Year']) if row['Year'] else ''}")
            st.write(f"**Pieces:** {int(row['Pieces']):,}")
            st.write(f"**Minifigs:** {int(row['Minifigs'])}")
            st.write(f"**Quantity:** {int(row['Quantity'])}")
            st.write(f"**Condition:** {row['Condition']}")
            st.write(f"**Status:** {row['Status']}")
            st.write(f"**Purchase Price:** ${row['Purchase Price']:,.2f}")
            st.write(f"**Retail Price:** ${row['Retail Price']:,.2f}")
            st.write(f"**Notes:** {row['Notes']}")

            if row.get("Brickset URL"):
                st.link_button("Open on Brickset", row["Brickset URL"])


# -------------------------------------------------
# Export
# -------------------------------------------------
st.subheader("Export")

st.download_button(
    label="Download Filtered Inventory as CSV",
    data=filtered_df.to_csv(index=False),
    file_name="lego_inventory_export.csv",
    mime="text/csv"
)
