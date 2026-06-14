import numpy as np
from datetime import datetime, timedelta
from collections import defaultdict
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import os

def get_monthly_totals(expenses):
    """Group expenses by month and return monthly totals."""
    monthly = defaultdict(float)
    for exp in expenses:
        try:
            date_str = str(exp[4])
            date = datetime.strptime(date_str, "%Y-%m-%d")
            key = f"{date.year}-{date.month:02d}"
            monthly[key] += float(exp[2])
        except:
            continue
    return dict(sorted(monthly.items()))

def get_category_totals(expenses):
    """Group expenses by category."""
    categories = defaultdict(float)
    for exp in expenses:
        try:
            cat = str(exp[3])
            categories[cat] += float(exp[2])
        except:
            continue
    return dict(sorted(categories.items(), key=lambda x: x[1], reverse=True))

def forecast_next_month(expenses):
    """
    Predict next month spending using linear regression on monthly totals.
    Returns a dict with forecast data.
    """
    if not expenses:
        return {
            "predicted_amount": 0,
            "trend": "stable",
            "trend_pct": 0,
            "confidence": "low",
            "monthly_history": {},
            "category_forecast": {},
            "next_month_label": get_next_month_label(),
            "insight": "No expense data available yet. Add expenses to unlock forecasting.",
            "chart_path": None
        }

    monthly = get_monthly_totals(expenses)
    categories = get_category_totals(expenses)
    next_month = get_next_month_label()

    if len(monthly) < 2:
        # Only one month of data — use it as flat forecast
        amount = list(monthly.values())[0]
        return {
            "predicted_amount": round(amount, 2),
            "trend": "stable",
            "trend_pct": 0,
            "confidence": "low",
            "monthly_history": monthly,
            "category_forecast": categories,
            "next_month_label": next_month,
            "insight": "More data needed for accurate forecasting. Keep adding expenses.",
            "chart_path": generate_forecast_chart(monthly, amount, next_month)
        }

    # Linear regression on monthly totals
    months_list = list(monthly.keys())
    amounts_list = list(monthly.values())

    x = np.arange(len(amounts_list))
    y = np.array(amounts_list)

    # Fit linear trend
    coeffs = np.polyfit(x, y, 1)
    slope = coeffs[0]
    intercept = coeffs[1]

    # Predict next month
    next_x = len(amounts_list)
    predicted = slope * next_x + intercept
    predicted = max(0, round(predicted, 2))

    # Trend analysis
    last_amount = amounts_list[-1]
    if last_amount > 0:
        trend_pct = round(((predicted - last_amount) / last_amount) * 100, 1)
    else:
        trend_pct = 0

    if trend_pct > 5:
        trend = "increasing"
    elif trend_pct < -5:
        trend = "decreasing"
    else:
        trend = "stable"

    # Confidence based on data points
    if len(amounts_list) >= 6:
        confidence = "high"
    elif len(amounts_list) >= 3:
        confidence = "medium"
    else:
        confidence = "low"

    # Category forecast — proportional to predicted amount
    total_hist = sum(amounts_list)
    category_forecast = {}
    if total_hist > 0:
        for cat, amt in categories.items():
            pct = amt / total_hist
            category_forecast[cat] = round(predicted * pct, 2)

    # Generate insight
    insight = generate_insight(trend, trend_pct, predicted, confidence)

    # Generate chart
    chart_path = generate_forecast_chart(monthly, predicted, next_month)

    return {
        "predicted_amount": predicted,
        "trend": trend,
        "trend_pct": abs(trend_pct),
        "confidence": confidence,
        "monthly_history": monthly,
        "category_forecast": category_forecast,
        "next_month_label": next_month,
        "insight": insight,
        "chart_path": chart_path
    }

def generate_insight(trend, trend_pct, predicted, confidence):
    """Generate a human-readable insight."""
    if trend == "increasing":
        return f"⚠ Spending is trending upward by {abs(trend_pct)}%. Consider reviewing your budget allocations to prevent overspend next month."
    elif trend == "decreasing":
        return f"✅ Spending is trending downward by {abs(trend_pct)}%. Good financial discipline detected. Keep monitoring to maintain this trajectory."
    else:
        return f"📊 Spending is stable. Predicted expenditure of £{predicted:,.2f} next month aligns with your recent financial patterns."

def get_next_month_label():
    """Return next month as a readable label."""
    now = datetime.now()
    if now.month == 12:
        next_month = datetime(now.year + 1, 1, 1)
    else:
        next_month = datetime(now.year, now.month + 1, 1)
    return next_month.strftime("%B %Y")

def generate_forecast_chart(monthly_history, predicted_amount, next_month_label):
    """Generate a professional forecast chart."""
    try:
        os.makedirs("static", exist_ok=True)

        months = list(monthly_history.keys())
        amounts = list(monthly_history.values())

        # Add forecast point
        months_display = [m.replace("-", "/") for m in months]
        months_display.append(f"{next_month_label[:3]} (Forecast)")
        amounts_with_forecast = amounts + [predicted_amount]

        fig, ax = plt.subplots(figsize=(10, 5))
        fig.patch.set_facecolor('#ffffff')
        ax.set_facecolor('#f5f8ff')

        # Historical bars
        x = np.arange(len(months_display))
        colors = ['#1565C0'] * len(months) + ['#4CAF50']
        bars = ax.bar(x, amounts_with_forecast, color=colors, width=0.6, zorder=3)

        # Add value labels on bars
        for bar, val in zip(bars, amounts_with_forecast):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + max(amounts_with_forecast) * 0.01,
                f'£{val:,.0f}',
                ha='center', va='bottom',
                fontsize=8, fontweight='bold', color='#0A1628'
            )

        # Trend line through historical data
        if len(months) >= 2:
            x_hist = np.arange(len(months))
            y_hist = np.array(amounts)
            coeffs = np.polyfit(x_hist, y_hist, 1)
            trend_y = np.polyval(coeffs, np.arange(len(months_display)))
            ax.plot(x, trend_y, color='#FF6B35', linewidth=2,
                   linestyle='--', label='Trend Line', zorder=4)

        # Forecast indicator line
        ax.axvline(x=len(months) - 0.5, color='#666666',
                  linestyle=':', linewidth=1.5, alpha=0.7)
        ax.text(len(months) - 0.4, max(amounts_with_forecast) * 0.95,
               'Forecast →', fontsize=8, color='#666666', style='italic')

        ax.set_xticks(x)
        ax.set_xticklabels(months_display, rotation=30, ha='right', fontsize=8)
        ax.set_ylabel('Amount (£)', fontsize=10, color='#0A1628')
        ax.set_title('Financial Forecasting — Monthly Spend & Prediction',
                    fontsize=12, fontweight='bold', color='#0A1628', pad=15)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'£{x:,.0f}'))
        ax.grid(axis='y', alpha=0.3, zorder=0)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)

        if len(months) >= 2:
            ax.legend(fontsize=9)

        plt.tight_layout()
        chart_path = "static/forecast_chart.png"
        plt.savefig(chart_path, dpi=150, bbox_inches='tight',
                   facecolor='white', edgecolor='none')
        plt.close()
        return chart_path
    except Exception as e:
        print("Forecast chart error:", e)
        return None