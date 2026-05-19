from __future__ import annotations

import streamlit as st

from src.strategies import STRATEGY_SPECS, get_strategy_parameter_table, get_strategy_source, list_strategy_catalog

st.set_page_config(page_title="策略管理", page_icon="📋", layout="wide")

st.title("📋 策略管理")

# ────────────────────────────── 策略目录 ──────────────────────────────
st.subheader("📚 策略目录")
catalog_df = list_strategy_catalog()
st.dataframe(catalog_df, use_container_width=True, hide_index=True)

st.markdown("---")

# ────────────────────────────── 策略详情 ──────────────────────────────
st.subheader("🔍 策略详情")

strategy_key = st.selectbox(
    "选择策略查看详情",
    options=list(STRATEGY_SPECS.keys()),
    format_func=lambda k: f"{STRATEGY_SPECS[k].display_name} ({k})",
    index=0,
)
spec = STRATEGY_SPECS[strategy_key]

col1, col2 = st.columns([1, 2])

with col1:
    st.markdown(f"**策略键：** `{spec.key}`")
    st.markdown(f"**显示名称：** {spec.display_name}")
    st.markdown(f"**分类：** {spec.category}")
    st.markdown(f"**引擎类型：** {spec.engine_type}")
    st.markdown(f"**支持周期：** {spec.supports_frequency}")
    st.markdown(f"**描述：** {spec.description}")

    if spec.source_file:
        st.markdown(f"**源码文件：** `{spec.source_file}`")

with col2:
    st.subheader("📐 参数定义")
    param_df = get_strategy_parameter_table(strategy_key)
    st.dataframe(param_df, use_container_width=True, hide_index=True)

st.markdown("---")

# ────────────────────────────── 源码预览 ──────────────────────────────
st.subheader("📝 源码预览")
source_file, source_code = get_strategy_source(strategy_key)
if source_code:
    st.code(source_code, language="python")
else:
    st.info("该策略暂无源码预览")
