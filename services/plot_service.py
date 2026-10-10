# -*- coding: utf-8 -*-
"""绘图服务：matplotlib pcolormesh 生成温度 / 降水色斑图，缓存到 static/weather_img/"""
import os
import hashlib

import matplotlib
matplotlib.use("Agg")  # 无界面后端
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap

from config import WEATHER_IMG_DIR

# 中文字体（Windows 常见黑体）
for _f in ["Microsoft YaHei", "SimHei", "Arial Unicode MS"]:
    try:
        matplotlib.rcParams["font.sans-serif"] = [_f]
        matplotlib.rcParams["axes.unicode_minus"] = False
        break
    except Exception:
        pass


def _cache_key(city, var, data):
    h = hashlib.md5(np.ascontiguousarray(np.nan_to_num(data)).tobytes()).hexdigest()[:10]
    return f"{city}_{var}_{h}.png"


def _plot_field(field2d, lats, lons, title, cbar_label, cmap, fname):
    """绘制单个 2D 场色斑图【修复版】"""
    path = os.path.join(WEATHER_IMG_DIR, fname)
    try:
        # 调整画布比例，适配窄经度区域
        fig, ax = plt.subplots(figsize=(7, 5), dpi=120)
        
        mesh = ax.pcolormesh(lons, lats, field2d, cmap=cmap, shading="flat")
        
        # ========== 关键修复1：固定色标范围，拉开色彩差距 ==========
        if "温度" in title:
            mesh.set_clim(vmin=27, vmax=31)   # 强制温度区间27~31℃
        elif "降水" in title:
            mesh.set_clim(vmin=2, vmax=4)    # 强制降水区间2~4mm
        
        # ========== 关键修复2：删除等比例拉伸，不再强制1:1 ==========
        # ax.set_aspect("equal", adjustable="box")
        
        # ========== 关键修复3：添加黑色网格线，分割格子 ==========
        ax.grid(True, color="black", linewidth=0.5, alpha=0.7)
        
        # ========== 关键修复4：每个格子标注数值 ==========
        lat_step = np.diff(lats)[0] / 2
        lon_step = np.diff(lons)[0] / 2
        for i, lat in enumerate(lats):
            for j, lon in enumerate(lons):
                val = field2d[i, j]
                ax.text(lon, lat, f"{val:.2f}", fontsize=7, ha="center", va="center", color="black")
        
        ax.set_title(title, fontsize=13)
        ax.set_xlabel("经度")
        ax.set_ylabel("纬度")
        
        cb = fig.colorbar(mesh, ax=ax, shrink=0.85)
        cb.set_label(cbar_label)
        fig.tight_layout()
        fig.savefig(path, bbox_inches="tight")
        plt.close(fig)
        return f"/static/weather_img/{fname}"
    except Exception as e:
        print(f"绘图异常：{e}")
        plt.close("all")
        return None
        
    """绘制单个 2D 场色斑图"""
    path = os.path.join(WEATHER_IMG_DIR, fname)
    try:
        fig, ax = plt.subplots(figsize=(6, 4.5), dpi=110)
        mesh = ax.pcolormesh(lons, lats, field2d, cmap=cmap, shading="auto")
        ax.set_title(title, fontsize=13)
        ax.set_xlabel("经度")
        ax.set_ylabel("纬度")
        ax.set_aspect("equal", adjustable="box")
        cb = fig.colorbar(mesh, ax=ax, shrink=0.85)
        cb.set_label(cbar_label)
        fig.tight_layout()
        fig.savefig(path, bbox_inches="tight")
        plt.close(fig)
        return f"/static/weather_img/{fname}"
    except Exception as e:
        plt.close("all")
        return None


def plot_weather(city, grid, lats, lons, avg_tmp=None):
    """
    生成温度 / 降水两张色斑图（取时间平均场）。
    返回 (tmp_url, pre_url)，失败项为 None。
    """
    tmp_url = pre_url = None
    tmp_arr = grid.get("TMP")
    pre_arr = grid.get("PRE")

    if tmp_arr is not None:
        field = np.nanmean(tmp_arr, axis=0) if tmp_arr.ndim == 3 else tmp_arr
        tmp_url = _plot_field(
            field, lats, lons,
            title=f"{city} · 温度分布(℃)",
            cbar_label="温度 (℃)",
            cmap="RdYlBu_r",
            fname=_cache_key(city, "TMP", field),
        )

    if pre_arr is not None:
        field = np.nansum(pre_arr, axis=0) if pre_arr.ndim == 3 else pre_arr
        pre_url = _plot_field(
            field, lats, lons,
            title=f"{city} · 累计降水(mm)",
            cbar_label="降水 (mm)",
            cmap=LinearSegmentedColormap.from_list("pre", ["#ffffff", "#a6cee3", "#1f78b4", "#08306b"]),
            fname=_cache_key(city, "PRE", field),
        )

    return tmp_url, pre_url
