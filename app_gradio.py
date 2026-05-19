from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="Quant Beginner",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.sidebar.title("📈 Quant Beginner")
st.sidebar.markdown("按 vn.py 风格重建的量化回测平台")
st.sidebar.markdown("---")

st.title("🚀 Quant Beginner")
st.markdown(
    """
    欢迎使用 Quant Beginner —— 一个面向新手的量化回测平台。

    **核心功能：**
    - 📊 **单标回测** — 在单个标的上运行 CTA 策略
    - 🏗️ **组合回测** — 多标的并行运行，资金等权/自定义权重分配
    - ⚙️ **参数优化** — 多进程并行网格扫描，寻找最优参数
    - 📋 **策略管理** — 查看所有内置策略的源码与参数
    - 📚 **历史记录** — 回测结果自动保存，支持多组对比

    从左侧导航栏选择功能开始。
    """
)

st.markdown("---")
st.caption("基于 vn.py 设计哲学 | 数据来自 akshare")
