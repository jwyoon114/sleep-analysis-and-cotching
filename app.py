"""Wearable sleep analysis entry point, independent of EEG training packages."""
import streamlit as st
from apple_watch_ui import render

st.set_page_config(page_title="나의 수면 리포트", page_icon="🌙", layout="wide")
render()
