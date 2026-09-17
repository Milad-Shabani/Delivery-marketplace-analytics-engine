import os, json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
with open(f"{ROOT}/dashboard/data/novafood_data.js") as f:
    js = f.read()
payload = json.loads(js[len("window.NOVAFOOD_DATA = "):-2])

NAVY, TEAL, AMBER, RED, GREEN = "#1f2a44", "#0f7c82", "#e08a2b", "#c94b4b", "#1f8b5b"
plt.rcParams.update({"font.family": "DejaVu Sans", "axes.edgecolor": "#e6e8ee", "axes.linewidth": 1})

fig = plt.figure(figsize=(13, 9), facecolor="white")
gs = fig.add_gridspec(3, 2, height_ratios=[0.5, 1, 1], hspace=0.55, wspace=0.28, left=0.06, right=0.97, top=0.93, bottom=0.06)

# KPI band
ax_kpi = fig.add_subplot(gs[0, :])
ax_kpi.axis("off")
k = payload["kpis"]
kpis = [
    ("GMV (trailing mo.)", f"${k['gmv']:,.0f}"),
    ("Delivered Orders", f"{k['orders']:,}"),
    ("Contribution Margin", f"{k['contribution_margin_pct']}%"),
    ("Active Customers", f"{k['active_customers']:,}"),
    ("On-Time Rate", f"{k['on_time_rate']}%"),
]
n = len(kpis)
for i, (label, val) in enumerate(kpis):
    x = i / n
    ax_kpi.add_patch(plt.Rectangle((x + 0.005, 0.05), 1/n - 0.02, 0.9, transform=ax_kpi.transAxes,
                                    facecolor="white", edgecolor="#e6e8ee", linewidth=1))
    ax_kpi.text(x + 0.02, 0.7, label.upper(), transform=ax_kpi.transAxes, fontsize=8.5, color="#6b7280", fontweight="bold")
    ax_kpi.text(x + 0.02, 0.25, val, transform=ax_kpi.transAxes, fontsize=17, color=NAVY, fontweight="bold")
fig.text(0.06, 0.965, "NOVAFOOD — Business Intelligence Dashboard (preview render)", fontsize=15, fontweight="bold", color=NAVY)
fig.text(0.06, 0.945, "Business Analytics · Financial Planning · Demand Forecasting · Optimization", fontsize=9.5, color="#6b7280")

# GMV & orders trend
ax1 = fig.add_subplot(gs[1, 0])
fin = payload["financial"]
ax1.bar(fin["months"], fin["gmv"], color=TEAL, alpha=0.85)
ax1.set_title("GMV by Month", fontsize=10, color=NAVY, loc="left")
ax1.tick_params(axis="x", rotation=90, labelsize=6.5)
ax1.tick_params(axis="y", labelsize=7)
ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x/1000:.0f}k"))
ax1.spines[["top", "right"]].set_visible(False)

# Contribution margin trend
ax2 = fig.add_subplot(gs[1, 1])
ax2.plot(fin["months"], fin["contribution_margin_pct"], color=TEAL, linewidth=2.5, marker="o", markersize=3)
ax2.fill_between(range(len(fin["months"])), fin["contribution_margin_pct"], color=TEAL, alpha=0.08)
ax2.set_title("Contribution Margin % by Month", fontsize=10, color=NAVY, loc="left")
ax2.tick_params(axis="x", rotation=90, labelsize=6.5)
ax2.tick_params(axis="y", labelsize=7)
ax2.spines[["top", "right"]].set_visible(False)

# Segment donut
ax3 = fig.add_subplot(gs[2, 0])
seg = payload["segments"]
colors = [TEAL, NAVY, AMBER, GREEN, RED, "#7c6fd6", "#3f8fd6", "#c98bd6", "#999"]
ax3.pie(seg["customer_counts"], labels=seg["names"], colors=colors[:len(seg["names"])],
        wedgeprops=dict(width=0.45), textprops={"fontsize": 7}, startangle=90)
ax3.set_title("Customers by Segment", fontsize=10, color=NAVY, loc="left")

# Forecast
ax4 = fig.add_subplot(gs[2, 1])
fo = payload["forecast"]["metrics"]["delivered_orders"]
hist = payload["forecast"]["history_orders"]
ax4.plot(hist["months"], hist["values"], color=NAVY, linewidth=2, label="Actuals")
fut_x = list(range(len(hist["months"]), len(hist["months"]) + len(fo["months"])))
ax4.plot(fut_x, fo["point_forecast"], color=TEAL, linewidth=2, linestyle="--", label="Forecast")
ax4.fill_between(fut_x, fo["lower_80"], fo["upper_80"], color=TEAL, alpha=0.15)
ax4.set_title("Delivered Orders — History & 12-Month Forecast", fontsize=10, color=NAVY, loc="left")
ax4.set_xticks([])
ax4.legend(fontsize=7, frameon=False)
ax4.spines[["top", "right"]].set_visible(False)

out_dir = os.path.join(ROOT, "docs", "screenshots")
os.makedirs(out_dir, exist_ok=True)
out_path = os.path.join(out_dir, "dashboard_preview.png")
fig.savefig(out_path, dpi=160)
print("Saved", out_path)
