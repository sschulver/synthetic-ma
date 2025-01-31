import streamlit as st
import geopandas as gpd
import folium
from streamlit_folium import st_folium

import pydeck as pdk
import altair as alt
import plotly.express as px
import geodesic
from geodesic import cql
import pandas as pd


### Main Page formating
st.set_page_config(
    page_title="Syntheic Data Patient",
    layout="wide",
    initial_sidebar_state="expanded",
)

alt.themes.enable("dark")
st.title("Exploring Synthetic Patient Data and EPA TRI Sites")

# Defining Default Values
ma_bbox = [-73.749890, 41.103738, -69.415784, 42.955983]
ma_center = [42.039094, -71.586914]


if "map_center" not in st.session_state:
    st.session_state["map_center"] = [ma_center[0], ma_center[1]]
if "zoom_level" not in st.session_state:
    st.session_state["zoom_level"] = 8


m = folium.Map(location=st.session_state["map_center"], zoom_start=st.session_state["zoom_level"])
geodesic.set_active_project("ehr")

sites_ds = geodesic.get_dataset("epa-tri-facilities-ma")
sites_buffered_ds = geodesic.get_dataset("epa-tri-facilities-ma-buffered")
claims_ds = geodesic.get_dataset("synthea-claims")
patient_ds = geodesic.get_dataset("synthea-patient")
conditions_ds = geodesic.get_dataset("synthea-condition")

chem_release_epa_ds = geodesic.get_dataset("epa-combined-chemical-release-ma")


sites_df = sites_ds.search(limit=None)


sites_df["name-id"] = sites_df["FACILITY_NAME"] + " - " + sites_df["TRI_FACILITY_ID"]
# Remove duplicates from the DataFrame
sites_df = sites_df.drop_duplicates(subset=["FACILITY_NAME", "TRI_FACILITY_ID"])
# Get a list of all sites and sort alphabetically

sites_list_sorted = sorted(sites_df["name-id"].tolist())

# Add " " to the start of the list
blank = [" "]
ref_list = blank + sites_list_sorted

# Store the selected value in the session_state variable
epa_site_selected = st.sidebar.selectbox("Choose EPA Site", ref_list)


st.session_state["selectbox_selection"] = epa_site_selected


if epa_site_selected != " ":
    tri_site_id = epa_site_selected.split(" - ")[1]

    selected_site_df = sites_df[sites_df["TRI_FACILITY_ID"] == tri_site_id]

    sites_buffered_df = sites_buffered_ds.search(
        filter=cql.CQLFilter.eq("TRI_FACILITY_ID", tri_site_id), limit=None
    )

    patients_in_buffered_area = patient_ds.search(
        intersects=sites_buffered_df["geometry"].values[0], limit=None
    )

    patients_in_buffered_area["FIRST"] = patients_in_buffered_area["FIRST"].str.replace(
        r"\d+", "", regex=True
    )
    patients_in_buffered_area["LAST"] = patients_in_buffered_area["LAST"].str.replace(
        r"\d+", "", regex=True
    )

    patients_in_buffered_area["first_last"] = (
        patients_in_buffered_area["FIRST"] + " " + patients_in_buffered_area["LAST"]
    )

    patient_id_lst = patients_in_buffered_area["Id"].tolist()

    patient_conditions = conditions_ds.search(
        filter=cql.CQLFilter.isin("PATIENT", patient_id_lst), limit=None
    )

    merged_patient_conditions = pd.merge(
        patient_conditions, patients_in_buffered_area, left_on="PATIENT", right_on="Id"
    )

    st.session_state["map_center"] = [
        selected_site_df["LATITUDE"],
        selected_site_df["LONGITUDE"],
    ]
    st.session_state["zoom_level"] = 12

    # Create a folium layer for the buffered geometry
    buffered_layer = folium.GeoJson(
        sites_buffered_df,
        name="Buffered Geometry",
        style_function=lambda x: {
            "fillColor": "orange",
            "color": "orange",
            "weight": 2,
            "fillOpacity": 0.3,
        },
    )
    # Create a folium layer for the selected site point
    point_layer = folium.Marker(
        location=[selected_site_df["LATITUDE"].values[0], selected_site_df["LONGITUDE"].values[0]],
        popup=selected_site_df["FACILITY_NAME"].values[0],
        tooltip=selected_site_df["FACILITY_NAME"].values[0],
        icon=folium.Icon(icon="fa-industry", prefix="fa", color="gray"),
    )

    # create a folium layer for the patients in the buffered area
    patients_in_buffered_area_layer = folium.GeoJson(
        patients_in_buffered_area,
        name="Patients in Buffered Area",
        marker=folium.Marker(icon=folium.Icon(icon="fa-user", prefix="fa", color="blue")),
        tooltip=folium.GeoJsonTooltip(fields=["FIRST", "LAST", "ADDRESS", "CITY", "STATE"]),
        popup=folium.GeoJsonTooltip(fields=["FIRST", "LAST", "ADDRESS", "CITY", "STATE"]),
    )

    patient_list = patients_in_buffered_area["first_last"].tolist()
    tabs = st.tabs(["Map"] + patient_list)

    with tabs[0]:
        st.title("Patient Map")
        buffered_layer.add_to(m)
        point_layer.add_to(m)
        patients_in_buffered_area_layer.add_to(m)

        folium.TileLayer("cartodbdark_matter", overlay=True, name="View in Dark Mode").add_to(m)

        st_folium(m, use_container_width=True)

    for i, patient_name in enumerate(patient_list, start=1):
        with tabs[i]:
            st.title(f"{patient_name}")

            patient_conditions_subset = merged_patient_conditions[
                merged_patient_conditions["first_last"] == patient_name
            ]

            st.write(
                f"Address: {patient_conditions_subset['ADDRESS'].values[0]}, {patient_conditions_subset['CITY'].values[0]}, {patient_conditions_subset['STATE'].values[0]}"
            )

            patient_conditions_subset = patient_conditions_subset[["DESCRIPTION", "START"]]

            if len(patient_conditions_subset) > 0:
                st.write("Conditions:")
                st.write(patient_conditions_subset)
            else:
                st.write("No conditions found for this patient")

else:
    st.session_state["map_center"] = [ma_center[0], ma_center[1]]
    st.session_state["zoom_level"] = 8

    layer = folium.GeoJson(
        sites_df,
        name="EPA TRI Sites",
        marker=folium.Marker(icon=folium.Icon(icon="fa-industry", prefix="fa", color="gray")),
        tooltip=folium.GeoJsonTooltip(fields=["FACILITY_NAME", "FAC_CLOSED_IND", "STREET_ADDRESS"]),
        popup=folium.GeoJsonPopup(fields=["FACILITY_NAME", "FAC_CLOSED_IND", "STREET_ADDRESS"]),
        highlight_function=lambda x: {"fillOpacity": 0.8},
        zoom_on_click=True,
    )
    layer.add_to(m)
    folium.TileLayer("cartodbdark_matter", overlay=True, name="View in Dark Mode").add_to(m)

    st_folium(m, use_container_width=True)
# Create a folium map


# if "layer" in locals() and layer is not None:
#     layer.add_to(m)

# if "buffered_layer" in locals() and buffered_layer is not None:
#     buffered_layer.add_to(m)
#     point_layer.add_to(m)
#     patients_in_buffered_area_layer.add_to(m)
