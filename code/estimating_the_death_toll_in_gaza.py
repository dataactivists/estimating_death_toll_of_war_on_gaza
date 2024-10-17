# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.16.4
#   kernelspec:
#     display_name: Python 3 (ipykernel)
#     language: python
#     name: python3
# ---

# %% [markdown]
# # Estimating the death toll in Gaza

# %%
import altair as alt
import pandas as pd

# %% [markdown]
# ## Official counts

# %%
# from https://data.techforpalestine.org/
df_official = pd.read_csv('../data/casualties_daily.csv')

# %% editable=true slideshow={"slide_type": ""}
df_official

# %%
# drop unnecessary columns
df_official = df_official[['report_date', 'killed_cum']]

# %%
df_official.info()

# %%
# convert to the right dtypes
df_official = df_official.convert_dtypes()
df_official['report_date'] = pd.to_datetime(df_official['report_date'])

df_official.info()

# %% [markdown]
# ## Estimates

# %%
# from data.techforpalestine.org
feb_6_official = 27958

# from https://aoav.org.uk/wp-content/uploads/2024/02/gaza_projections_report.pdf
aoav_base_projection = 58260
# inclusion of epidemic scenario based on https://www.gazahealthcareletters.org/usa-letter-oct-2-2024
aoav_base_epidemic_projection = 66720

aoav_base_estimate = feb_6_official + aoav_base_projection
aoav_high_estimate = feb_6_official + aoav_base_epidemic_projection

# %%
# independent estimates from different sources
estimates = [
    {
        'date': '2024/06/19',
        'estimate': 186980,
        'url': 'https://www.thelancet.com/action/showPdf?pii=S0140-6736%2824%2901169-3',
        'title': 'Counting the dead in Gaza: difficult but essential',
    },
    {
        'date': '2024/12/31',
        'estimate': 335500,
        'url': 'https://www.theguardian.com/commentisfree/article/2024/sep/05/scientists-death-disease-gaza-polio-vaccinations-israel',
        'title': 'Scientists are closing in on the true, horrifying scale of death and disease in Gaza',
    },
    {
        'date': '2024/08/06',
        'estimate': aoav_base_estimate,
        'url': 'https://aoav.org.uk/wp-content/uploads/2024/02/gaza_projections_report.pdf',
        'title': 'Crisis in Gaza: Scenario-based Health Impact Projections, Report One: 7 February to 6 August 2024',
    },
    {
        'date': '2024/08/06',
        'estimate': aoav_high_estimate,
        'url': 'https://aoav.org.uk/wp-content/uploads/2024/02/gaza_projections_report.pdf',
        'title': 'Crisis in Gaza: Scenario-based Health Impact Projections, Report One: 7 February to 6 August 2024',
    },
    {
        'date': '2024/10/02',
        'estimate': 118908,
        'url': 'https://www.gazahealthcareletters.org/usa-letter-oct-2-2024',
        'title': 'USA Letter | October 2 — Gaza Healthcare Letters',
    },
]

# %%
df_estimates = pd.DataFrame.from_records(estimates)
df_estimates = df_estimates.sort_values('date')

# %%
df_estimates.info()

# %%
# convert to the right dtypes
df_estimates = df_estimates.convert_dtypes()
df_estimates['date'] = pd.to_datetime(df_estimates['date'])

df_estimates.info()

# %%
df_estimates

# %%
# add first 30 days of official data to anchor trendline at 0
df_estimates_weighted = df_estimates.merge(
    df_official.loc[
        :30, ['report_date', 'killed_cum']
    ].rename(
        columns={'report_date': 'date', 'killed_cum': 'estimate'}
    ),
    how='outer',
)

df_estimates_weighted

# %% [markdown]
# ## Charts

# %%
# chart with official counts
chart_official = (
    alt.Chart(df_official[['report_date', 'killed_cum']])
    .mark_line(color='black', size=3)
    .encode(
        alt.X('report_date:T').title(None),
        alt.Y('killed_cum:Q').title('Total casualties'),
    )
    .properties(
        title='Official numbers'
    )
)

chart_official

# %%
# chart with estimates as scatter plot
chart_estimates = (
    alt.Chart(df_estimates_weighted)
    .mark_circle()
    .encode(
        alt.X('date:T'),
        alt.Y('estimate:Q'),
        alt.Size('estimate:Q').legend(None),
        alt.Tooltip(['date', 'estimate', 'title', 'url']),
        alt.Href('url:N'),
    )
)

# trendline for scatter plot
chart_trendline = (
    alt.Chart(df_estimates_weighted)
    .mark_line(color='red', strokeDash=[5, 5])
    .transform_regression(
        on='date',
        regression='estimate',
        method='log',
        # order=3,
    )
    .encode(
        alt.X('date:T').title(None),
        alt.Y('estimate:Q').title('Total casualties').scale(domain=[0, 400000]),
    )
)

# combine scatter plot and trendline
chart_estimates_trend = (
    alt.layer(chart_estimates, chart_trendline)
    .properties(
        title='Estimates'
    )
)

chart_estimates_trend

# %%
# combine charts for official counts and estimates
chart_combined = (
    alt.layer(chart_official, chart_estimates_trend)
    .properties(
        title=[
            'Official casuaty numbers',
            'vs independent estimates'
        ],
        width=600,
        height=400,
    )
)

chart_combined

# %%
# make legend chart
chart_legend = (
    alt.Chart({
        'values': [
            {'category': 'Official', 'color': 'black'},
            {'category': 'Estimate', 'color': 'red'}
        ]
    })
    .mark_point(filled=True, size=100)
    .encode(
        alt.Y('category:N').axis(orient='right').title(None).sort(None),
        alt.Color('color:N', scale=None)
    )
)

# combine the main chart with the legend
chart = alt.hconcat(chart_combined, chart_legend).resolve_scale(color='independent')

chart.save('../charts/official_vs_estimates.png')
chart.save('../charts/official_vs_estimates.html')

chart
