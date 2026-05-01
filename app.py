import streamlit as st
import pandas as pd
import requests
from pathlib import Path

DATA_FILE = Path("lego_inventory.csv")

BRICKSET_API_KEY = st.secrets["BRICKSET_API_KEY"]
BRICKSET_USER_HASH = st.secrets["BRICKSET_USER_HASH"]

BRICKSET_URL = "https://brickset.com/api/v3.asmx/getSets"

st.set_page_config(page_title="LEGO Inventory Tracker", layout="wide")

st.title("🧱 LEGO Inventory Tracker")


# -----------------------------
# Load or create inventory file
# -----------------------------
columns = [
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
    "Image URL",
    "Brickset URL",
    "Notes"
]

if DATA_FILE.exists():
    df = pd.read_csv(DATA_FILE)
else:
    df = pd.DataFrame(columns=columns)


# -----------------------------
# Brickset lookup function
# -----------------------------
def lookup_brickset_set(set_number):
    """
    Looks up a LEGO set from Brickset by set number.
    Example set_number: 10305 or 10305-1
    """

    if "-" not in set_number:
        set_number = f"{set_number}-1"

    params = {
        "apiKey": BRICKSET_API_KEY,
        "userHash": BRICKSET_USER_HASH,
        "params": f'{{"setNumber":"{set_number}"}}'
    }

    response = requests.get(BRICKSET_URL, params=params)

    if response.status_code != 200:
        st.error("Brickset API request failed.")
        return None

    data = response.json()

    if data.get("status") != "success":
        st.error(f"Brickset error: {data.get('message', 'Unknown error')}")
        return None

    sets = data.get("sets", [])

    if not sets:
        st.warning("No set found for that set number.")
        return None

    return sets[0]


# -----------------------------
# Sidebar: Add set
# -----------------------------
st.sidebar.header("Add LEGO Set")

lookup_number = st.sidebar.text_input("Enter LEGO Set Number", placeholder="Example: 10305")

if st.sidebar.button("Look Up Set"):
    result = lookup_brickset_set(lookup_number)

    if result:
        st.session_state["brickset_result"] = result
        st.sidebar.success("Set found!")


brickset_result = st.session_state.get("brickset_result", {})

with st.sidebar.form("add_set_form"):
    set_number = st.text_input(
        "Set Number",
        value=brickset_result.get("number", "")
    )

    set_name = st.text_input(
        "Set Name",
        value=brickset_result.get("name", "")
    )

    theme = st.text_input(
        "Theme",
        value=brickset_result.get("theme", "")
    )

    subtheme = st.text_input(
        "Subtheme",
        value=brickset_result.get("subtheme", "")
    )

    year = st.number_input(
        "Year",
        min_value=1950,
        max_value=2100,
        step=1,
        value=int(brickset_result.get("year", 2024) or 2024)
    )

    pieces = st.number_input(
        "Pieces",
        min_value=0,
        step=1,
        value=int(brickset_result.get("pieces", 0) or 0)
    )

    minifigs = st.number_input(
        "Minifigs",
        min_value=0,
        step=1,
        value=int(brickset_result.get("minifigs", 0) or 0)
    )

    quantity = st.number_input("Quantity", min_value=1, step=1, value=1)

    condition = st.selectbox(
        "Condition",
        ["New Sealed", "New Open Box", "Used Complete", "Used Incomplete", "Built", "Parts Only"]
    )

    status = st.selectbox(
        "Status",
        ["Owned", "Wishlist", "Sold", "Ordered", "Missing Pieces"]
    )

    purchase_price = st.number_input("Purchase Price", min_value=0.00, step=1.00)

    retail_price = st.number_input(
        "Retail Price",
        min_value=0.00,
        step=1.00,
        value=float(
            brickset_result.get("LEGOCom", {})
            .get("US", {})
            .get("retailPrice", 0) or 0
        )
    )

    image_url = st.text_input(
        "Image URL",
        value=brickset_result.get("image", {}).get("imageURL", "")
    )

    brickset_url = st.text_input(
        "Brickset URL",
        value=brickset_result.get("bricksetURL", "")
    )

    notes = st.text_area("Notes")

    submitted = st.form_submit_button("Add Set to Inventory")


if submitted:
    new_row = {
        "Set Number": set_number,
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

    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df.to_csv(DATA_FILE, index=False)

    st.success(f"Added {set_number} - {set_name} to your inventory!")

    if "brickset_result" in st.session_state:
        del st.session_state["brickset_result"]


# -----------------------------
# Dashboard
# -----------------------------
st.subheader("Collection Overview")

total_sets = int(df["Quantity"].fillna(0).sum()) if not df.empty else 0
unique_sets = len(df)
total_pieces = int((df["Pieces"].fillna(0) * df["Quantity"].fillna(0)).sum()) if not df.empty else 0
total_spend = df["Purchase Price"].fillna(0).sum() if not df.empty else 0

col1, col2, col3, col4 = st.columns(4)

col1.metric("Unique Sets", unique_sets)
col2.metric("Total Sets Owned", total_sets)
col3.metric("Total Pieces", f"{total_pieces:,}")
col4.metric("Total Spend", f"${total_spend:,.2f}")


# -----------------------------
# Search/filter inventory
# -----------------------------
st.subheader("Inventory")

search = st.text_input("Search by set number, name, theme, year, or status")

filtered_df = df.copy()

if search:
    filtered_df = df[
        df.astype(str).apply(
            lambda row: row.str.contains(search, case=False, na=False).any(),
            axis=1
        )
    ]

st.dataframe(filtered_df, use_container_width=True)


# -----------------------------
# Show images/cards
# -----------------------------
st.subheader("Set Gallery")

for _, row in filtered_df.iterrows():
    with st.expander(f"{row['Set Number']} - {row['Set Name']}"):
        col_img, col_info = st.columns([1, 3])

        with col_img:
            if pd.notna(row.get("Image URL")) and row.get("Image URL"):
                st.image(row["Image URL"], use_container_width=True)

        with col_info:
            st.write(f"**Theme:** {row['Theme']}")
            st.write(f"**Subtheme:** {row['Subtheme']}")
            st.write(f"**Year:** {row['Year']}")
            st.write(f"**Pieces:** {row['Pieces']}")
            st.write(f"**Minifigs:** {row['Minifigs']}")
            st.write(f"**Quantity:** {row['Quantity']}")
            st.write(f"**Condition:** {row['Condition']}")
            st.write(f"**Status:** {row['Status']}")
            st.write(f"**Purchase Price:** ${row['Purchase Price']}")
            st.write(f"**Retail Price:** ${row['Retail Price']}")

            if pd.notna(row.get("Brickset URL")) and row.get("Brickset URL"):
                st.link_button("Open on Brickset", row["Brickset URL"])


# -----------------------------
# Download inventory
# -----------------------------
st.download_button(
    label="Download Inventory as CSV",
    data=df.to_csv(index=False),
    file_name="lego_inventory.csv",
    mime="text/csv"
)
