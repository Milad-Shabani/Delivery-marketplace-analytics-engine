import os, json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
with open(f"{ROOT}/dashboard/data/novafood_data.js") as f:
    js = f.read()
payload = json.loads(js[len("window.NOVAFOOD_DATA = "):-2])

NAVY, TEAL, AMBER, RED, GREEN, MUTED = "#1f2a44", "#0f7c82", "#e08a2b", "#c94b4b", "#1f8b5b", "#9aa3b2"
PALETTE = [TEAL, NAVY, AMBER, GREEN, RED, "#7c6fd6", "#3f8fd6", "#c98bd6", "#999"]
plt.rcParams.update({"font.family": "DejaVu Sans", "axes.edgecolor": "#e6e8ee", "axes.linewidth": 1})

OUT_DIR = os.path.join(ROOT, "docs", "screenshots")
os.makedirs(OUT_DIR, exist_ok=True)


def new_fig(title, subtitle, w=13, h=6.2):
    fig = plt.figure(figsize=(w, h), facecolor="white")
    fig.text(0.045, 0.965, title, fontsize=15, fontweight="bold", color=NAVY)
    fig.text(0.045, 0.935, subtitle, fontsize=9.5, color="#6b7280")
    return fig


def kpi_band(fig, kpis, top=0.90, bottom=0.78):
    ax = fig.add_axes([0.045, bottom, 0.91, top - bottom])
    ax.axis("off")
    n = len(kpis)
    for i, (label, val) in enumerate(kpis):
        x = i / n
        ax.add_patch(plt.Rectangle((x + 0.006, 0.05), 1/n - 0.02, 0.9, transform=ax.transAxes,
                                    facecolor="white", edgecolor="#e6e8ee", linewidth=1))
        ax.text(x + 0.022, 0.62, label.upper(), transform=ax.transAxes, fontsize=8, color="#6b7280", fontweight="bold")
        ax.text(x + 0.022, 0.18, val, transform=ax.transAxes, fontsize=15.5, color=NAVY, fontweight="bold")


def style_ax(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(labelsize=7.5)


# ---------------------------------------------------------------------------
# 1. Executive Overview
# ---------------------------------------------------------------------------
k = payload["kpis"]
fin = payload["financial"]
cities = payload["cities"]
fig = new_fig("NOVAFOOD Dashboard — Executive Overview", "Business Analytics · Financial Planning · Demand Forecasting · Optimization (preview render)")
kpi_band(fig, [
    ("GMV (trailing mo.)", f"${k['gmv']:,.0f}"),
    ("Delivered Orders", f"{k['orders']:,}"),
    ("Contribution Margin", f"{k['contribution_margin_pct']}%"),
    ("Active Customers", f"{k['active_customers']:,}"),
    ("On-Time Rate", f"{k['on_time_rate']}%"),
])
ax1 = fig.add_axes([0.06, 0.10, 0.42, 0.60])
ax1.bar(fin["months"], fin["gmv"], color=TEAL, alpha=0.85)
ax1.set_title("GMV by Month", fontsize=10, color=NAVY, loc="left")
ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x/1000:.0f}k"))
ax1.tick_params(axis="x", rotation=90)
style_ax(ax1)

ax2 = fig.add_axes([0.56, 0.10, 0.40, 0.60])
colors = [GREEN if v >= 0 else RED for v in cities["contribution_profit"]]
ax2.barh(cities["names"], cities["contribution_profit"], color=colors)
ax2.set_title("Contribution Profit by City ($, period total)", fontsize=10, color=NAVY, loc="left")
ax2.axvline(0, color="#ccc", linewidth=1)
style_ax(ax2)
fig.savefig(f"{OUT_DIR}/section_1_overview.png", dpi=160)
plt.close(fig)

# ---------------------------------------------------------------------------
# 2. Financial Performance
# ---------------------------------------------------------------------------
drivers = payload["drivers"]
fig = new_fig("NOVAFOOD Dashboard — Financial Performance", "Marketplace P&L, cost structure, and an approximate margin-driver decomposition (preview render)")
ax1 = fig.add_axes([0.06, 0.10, 0.27, 0.72])
ax1.plot(fin["months"], fin["contribution_margin_pct"], color=TEAL, linewidth=2.5, marker="o", markersize=3)
ax1.fill_between(range(len(fin["months"])), fin["contribution_margin_pct"], color=TEAL, alpha=0.08)
ax1.set_title("Contribution Margin %", fontsize=10, color=NAVY, loc="left")
ax1.tick_params(axis="x", rotation=90)
style_ax(ax1)

ax2 = fig.add_axes([0.40, 0.10, 0.24, 0.72])
last3 = {
    "Commission": sum(fin["commission_revenue"][-3:]),
    "Delivery Fee": sum(fin["delivery_fee_collected"][-3:]),
    "Service Fee": sum(fin["service_fee_revenue"][-3:]),
}
ax2.pie(last3.values(), labels=last3.keys(), colors=[NAVY, TEAL, AMBER],
        wedgeprops=dict(width=0.45), textprops={"fontsize": 7.5}, startangle=90)
ax2.set_title("Revenue Mix (Trailing 3 Mo.)", fontsize=10, color=NAVY, loc="left")

ax3 = fig.add_axes([0.71, 0.10, 0.25, 0.72])
d = drivers
colors3 = [GREEN if v >= 0 else RED for v in d["values"]]
labels_short = [l.split(" (")[0] for l in d["labels"]]
ax3.barh(labels_short, d["values"], color=colors3)
ax3.axvline(0, color="#ccc", linewidth=1)
ax3.set_title("Margin Driver Impact (pp)", fontsize=10, color=NAVY, loc="left")
style_ax(ax3)
fig.savefig(f"{OUT_DIR}/section_2_financial.png", dpi=160)
plt.close(fig)

# ---------------------------------------------------------------------------
# 3. Customers & Retention
# ---------------------------------------------------------------------------
seg = payload["segments"]
chan = payload["channels"]
coh = payload["cohorts"]
fig = new_fig("NOVAFOOD Dashboard — Customers & Retention", "Segmentation, channel LTV:CAC, and monthly cohort retention (preview render)")
ax1 = fig.add_axes([0.05, 0.10, 0.27, 0.72])
ax1.pie(seg["customer_counts"], labels=seg["names"], colors=PALETTE[:len(seg["names"])],
        wedgeprops=dict(width=0.5), textprops={"fontsize": 6.8}, startangle=140,
        labeldistance=1.08)
ax1.set_title("Customers by Segment", fontsize=10, color=NAVY, loc="left")

ax2 = fig.add_axes([0.38, 0.10, 0.24, 0.72])
colors2 = [GREEN if v >= 3 else (AMBER if v >= 1.5 else RED) for v in chan["ltv_to_cac"]]
ax2.bar(chan["names"], chan["ltv_to_cac"], color=colors2)
ax2.set_title("LTV : CAC by Channel", fontsize=10, color=NAVY, loc="left")
ax2.tick_params(axis="x", rotation=35)
style_ax(ax2)

ax3 = fig.add_axes([0.68, 0.10, 0.28, 0.72])
mat = np.array([[np.nan if v is None else v for v in row] for row in coh["matrix"]])
im = ax3.imshow(mat, aspect="auto", cmap="RdYlGn", vmin=0, vmax=max(1, np.nanmax(mat)) if mat.size else 1)
ax3.set_xticks(range(len(coh["month_numbers"])))
ax3.set_xticklabels([f"M{m}" for m in coh["month_numbers"]], fontsize=6.5)
ax3.set_yticks(range(len(coh["cohort_labels"])))
ax3.set_yticklabels(coh["cohort_labels"], fontsize=6)
ax3.set_title("Cohort Retention % Heatmap", fontsize=10, color=NAVY, loc="left")
fig.savefig(f"{OUT_DIR}/section_3_customers.png", dpi=160)
plt.close(fig)

# ---------------------------------------------------------------------------
# 4. Restaurant Performance
# ---------------------------------------------------------------------------
rest = payload["restaurants"]
quad_color = {
    "Star: High Revenue / High Margin": GREEN,
    "Volume Trap: High Revenue / Low Margin": AMBER,
    "Niche Profit: Low Revenue / High Margin": TEAL,
    "Review: Low Revenue / Low Margin": RED,
}
fig = new_fig("NOVAFOOD Dashboard — Restaurant Performance", "Revenue-vs-margin quadrant classification, one dot per restaurant (preview render)")
ax1 = fig.add_axes([0.06, 0.10, 0.55, 0.72])
sc = rest["scatter"]
for qlabel, color in quad_color.items():
    xs = [sc["gmv"][i] for i in range(len(sc["gmv"])) if sc["quadrant"][i] == qlabel]
    ys = [sc["margin_pct"][i] for i in range(len(sc["gmv"])) if sc["quadrant"][i] == qlabel]
    ax1.scatter(xs, ys, s=16, color=color, alpha=0.75, label=qlabel.split(":")[0])
ax1.set_xlabel("Monthly GMV ($)", fontsize=8)
ax1.set_ylabel("Margin %", fontsize=8)
ax1.set_title("Revenue vs. Contribution Margin", fontsize=10, color=NAVY, loc="left")
ax1.legend(fontsize=7, frameon=False, loc="upper right")
style_ax(ax1)

ax2 = fig.add_axes([0.68, 0.10, 0.28, 0.72])
labels_short = [l.split(":")[0] for l in rest["quadrant_labels"]]
colors4 = [quad_color.get(l, MUTED) for l in rest["quadrant_labels"]]
ax2.barh(labels_short, rest["quadrant_counts"], color=colors4)
ax2.set_title("Restaurant Count by Quadrant", fontsize=10, color=NAVY, loc="left")
style_ax(ax2)
fig.savefig(f"{OUT_DIR}/section_4_restaurants.png", dpi=160)
plt.close(fig)

# ---------------------------------------------------------------------------
# 5. Operations
# ---------------------------------------------------------------------------
fig = new_fig("NOVAFOOD Dashboard — Delivery Operations", "Service levels behind the financial numbers (preview render)")
ax1 = fig.add_axes([0.07, 0.12, 0.40, 0.68])
ax1.plot(fin["months"], fin["on_time_rate"], color=GREEN, linewidth=2.5, marker="o", markersize=3)
ax1.set_title("On-Time Delivery Rate (%)", fontsize=10, color=NAVY, loc="left")
ax1.tick_params(axis="x", rotation=90)
style_ax(ax1)

ax2 = fig.add_axes([0.56, 0.12, 0.40, 0.68])
ax2.plot(fin["months"], fin["cancellation_rate"], color=RED, linewidth=2.5, marker="o", markersize=3)
ax2.set_title("Cancellation Rate (%)", fontsize=10, color=NAVY, loc="left")
ax2.tick_params(axis="x", rotation=90)
style_ax(ax2)
fig.savefig(f"{OUT_DIR}/section_5_operations.png", dpi=160)
plt.close(fig)

# ---------------------------------------------------------------------------
# 6. Forecast & Strategic Planning
# ---------------------------------------------------------------------------
fo = payload["forecast"]["metrics"]["delivered_orders"]
hist = payload["forecast"]["history_orders"]
plan = payload["plan"]
fig = new_fig("NOVAFOOD Dashboard — Forecast & Strategic Planning", "12-month demand forecast (rolling-origin validated) and the +25% orders / +2pp margin plan (preview render)")
ax1 = fig.add_axes([0.06, 0.10, 0.55, 0.72])
ax1.plot(hist["months"], hist["values"], color=NAVY, linewidth=2, label="Actuals")
fut_x = list(range(len(hist["months"]), len(hist["months"]) + len(fo["months"])))
ax1.plot(fut_x, fo["point_forecast"], color=TEAL, linewidth=2, linestyle="--", label="Forecast (Base)")
ax1.fill_between(fut_x, fo["lower_80"], fo["upper_80"], color=TEAL, alpha=0.15, label="80% Interval")
ax1.set_xticks([])
ax1.set_title("Delivered Orders — History & 12-Month Forecast", fontsize=10, color=NAVY, loc="left")
ax1.legend(fontsize=7.5, frameon=False)
style_ax(ax1)

ax2 = fig.add_axes([0.68, 0.10, 0.28, 0.72])
ax2.axis("off")
rows = [
    ("Current annualized orders", f"{plan['current_orders_annualized']:,.0f}"),
    ("Target (+25%)", f"{plan['required_orders_annualized']:,.0f}"),
    ("Current margin", f"{plan['current_margin_pct']}%"),
    ("Target (+2pp)", f"{plan['required_margin_pct']}%"),
]
ax2.set_title("Strategic Plan Targets", fontsize=10, color=NAVY, loc="left", x=0)
for i, (label, val) in enumerate(rows):
    y = 0.75 - i * 0.2
    ax2.text(0, y, label, fontsize=8.5, color="#6b7280", transform=ax2.transAxes)
    ax2.text(0.62, y, val, fontsize=9.5, color=NAVY, fontweight="bold", transform=ax2.transAxes)
fig.savefig(f"{OUT_DIR}/section_6_forecast.png", dpi=160)
plt.close(fig)

# ---------------------------------------------------------------------------
# 7. Scenario & Optimization
# ---------------------------------------------------------------------------
scn = payload["forecast"]["metrics"]["contribution_profit"]
opt = payload["optimization"]
fig = new_fig("NOVAFOOD Dashboard — Scenario & Optimization", "Base/Upside/Downside contribution-profit scenarios and promo-budget reallocation (preview render)")
ax1 = fig.add_axes([0.06, 0.12, 0.42, 0.68])
ax1.plot(scn["months"], scn["downside_case"], color=RED, linewidth=2, linestyle=":", label="Downside")
ax1.plot(scn["months"], scn["base_case"], color=NAVY, linewidth=2.5, label="Base")
ax1.plot(scn["months"], scn["upside_case"], color=GREEN, linewidth=2, linestyle=":", label="Upside")
ax1.set_xticks([])
ax1.set_title("Contribution Profit Scenarios", fontsize=10, color=NAVY, loc="left")
ax1.legend(fontsize=7.5, frameon=False)
style_ax(ax1)

ax2 = fig.add_axes([0.56, 0.12, 0.40, 0.68])
cells = opt["cells"]
top_n = 8
idx = np.argsort(cells["optimized_profit"])[::-1][:top_n]
labels5 = [cells["labels"][i].split(" / ")[0][:4] + "/" + cells["labels"][i].split(" / ")[1] for i in idx]
base_v = [cells["baseline_spend"][i] for i in idx]
opt_v = [cells["optimized_spend"][i] for i in idx]
x = np.arange(len(labels5))
ax2.bar(x - 0.2, base_v, width=0.4, color=MUTED, label="Baseline")
ax2.bar(x + 0.2, opt_v, width=0.4, color=TEAL, label="Optimized")
ax2.set_xticks(x)
ax2.set_xticklabels(labels5, rotation=30, ha="right", fontsize=6.8)
ax2.set_title("Promo Spend — Baseline vs. Optimized (Top Cells)", fontsize=10, color=NAVY, loc="left")
ax2.legend(fontsize=7.5, frameon=False)
style_ax(ax2)
fig.savefig(f"{OUT_DIR}/section_7_optimization.png", dpi=160)
plt.close(fig)

print("Saved 7 section previews to", OUT_DIR)

