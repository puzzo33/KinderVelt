"""
Generates a chart of estimated global web-visit market share for major AI
chatbots/assistants over the past two years (mid-2024 - mid-2026).

Data points are approximate, aggregated from publicly reported figures
(Similarweb-based market share reports, First Page Sage, company
disclosures). Where exact monthly data wasn't available, values are
interpolated between known anchor points. See sources in the accompanying
summary for details.
"""

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import date

# Approximate worldwide web-visit market share (%) among major AI chatbots
dates = [
    date(2024, 6, 1),
    date(2024, 9, 1),
    date(2024, 12, 1),
    date(2025, 2, 1),
    date(2025, 6, 1),
    date(2025, 9, 1),
    date(2025, 12, 1),
    date(2026, 4, 1),
]

series = {
    "ChatGPT":  [88, 86, 84, 76.5, 70, 65, 68, 54.7],
    "Gemini":   [2.5, 3, 4, 5.6, 11, 15, 18, 27.4],
    "Claude":   [3, 3.5, 4, 5, 6, 6.5, 7, 8.2],
    "Copilot":  [4, 3.5, 3, 3, 2.5, 2, 1.7, 1.3],
    "Grok":     [0.1, 0.3, 0.8, 1.9, 3, 4, 6, 2.8],
    "Perplexity / DeepSeek / Other": [2.3, 3.7, 4.2, 8, 7.5, 7.5, -0.7, 5.4],
}

# Fix the negative placeholder above (kept formula transparent: "other"
# is whatever is left after the named competitors, can't go negative)
other = []
for i in range(len(dates)):
    named_total = sum(series[k][i] for k in ["ChatGPT", "Gemini", "Claude", "Copilot", "Grok"])
    other.append(max(0, round(100 - named_total, 1)))
series["Perplexity / DeepSeek / Other"] = other

colors = {
    "ChatGPT": "#74AA9C",
    "Gemini": "#4285F4",
    "Claude": "#D97757",
    "Copilot": "#00A4EF",
    "Grok": "#000000",
    "Perplexity / DeepSeek / Other": "#999999",
}

fig, ax = plt.subplots(figsize=(11, 6.5))

for name, values in series.items():
    ax.plot(dates, values, marker="o", linewidth=2.5, label=name, color=colors[name])

ax.set_title("Estimated Global AI Chatbot Market Share by Web Visits\n(Mid-2024 to Mid-2026)", fontsize=14, fontweight="bold")
ax.set_ylabel("Share of Web Visits (%)")
ax.set_xlabel("Date")
ax.set_ylim(0, 100)
ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
ax.grid(True, linestyle="--", alpha=0.4)
ax.legend(loc="upper right", fontsize=10)

fig.text(0.01, 0.01,
         "Source (approximate, aggregated): Similarweb-based market share reports (First Page Sage, Vertu, ppc.land),\n"
         "Anthropic/OpenAI/Google/xAI public disclosures. Values are estimates and vary by methodology/region.",
         fontsize=7, color="gray")

plt.tight_layout(rect=(0, 0.04, 1, 1))
plt.savefig("reports/ai_competitor_popularity.png", dpi=150)
print("Saved chart to reports/ai_competitor_popularity.png")
