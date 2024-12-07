# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.16.6
#   kernelspec:
#     display_name: Python 3 (ipykernel)
#     language: python
#     name: python3
# ---

# %% [markdown]
# # Food insecurity

# %%
import datetime

import altair as alt
import pandas as pd

# %% [markdown]
# ## Data

# %% [markdown]
# ### IPC assessments

# %%
# from https://www.ipcinfo.org/ipc-country-analysis/en/
df_ipc = pd.read_csv('../data/food_insecurity/ipc_assessments.csv')

# %%
df_ipc

# %%
# drop cols
df_ipc = df_ipc.drop(columns=['type', 'url'])

# %%
# convert date cols to datetime
df_ipc['start_date'] = pd.to_datetime(df_ipc['start_date'])
df_ipc['end_date'] = pd.to_datetime(df_ipc['end_date'])


# %%
def create_linear_timeline(df_ipc: pd.DataFrame) -> pd.DataFrame:
    """
    Determine linear timeline across assessments.

    Parameters:
    df_ipc (pd.DataFrame): DataFrame with `start_date` and `end_date` columns.

    Returns:
    pd.DataFrame: Linear timeline DataFrame.
    """

    df_ipc['start_date'] = pd.to_datetime(df_ipc['start_date'])
    df_ipc['end_date'] = pd.to_datetime(df_ipc['end_date'])

    df_ipc = df_ipc.sort_values('start_date')

    linear_timeline_rows = []

    for _, row in df_ipc.iterrows():
        # check if linear_timeline_rows is empty or no overlap with linear_timeline_row
        if (
            not linear_timeline_rows
            or row['start_date'] > linear_timeline_rows[-1]['end_date']
        ):
            linear_timeline_rows.append(row)

        else:
            # set end_date of last linear row to before start_date of new row
            linear_timeline_rows[-1]['end_date'] = min(
                linear_timeline_rows[-1]['end_date'],
                row['start_date'] - pd.Timedelta(days=1),
            )

            linear_timeline_rows.append(row)

    df_linear = pd.DataFrame(linear_timeline_rows)

    df_linear = df_linear.sort_values('start_date').reset_index(drop=True)

    return df_linear


# %%
# create df with linear timeline
df_ipc = create_linear_timeline(df_ipc)


# %%
def find_assessment_gaps(df_ipc: pd.DataFrame, interpolate: bool = True) -> pd.DataFrame:
    """
    Find gaps in assessments with rows containing None values.
    """

    df_ipc = df_ipc.sort_values('start_date').reset_index(drop=True)

    gap_rows = {'start_date': [], 'end_date': []}

    for i in range(1, len(df_ipc)):
        # previous row end_date
        previous_end_date = df_ipc.loc[i - 1, 'end_date']
        # current row start_date
        current_start_date = df_ipc.loc[i, 'start_date']

        # if diff between previous end_date and current start_date > 1, create new row filling the gap interval
        if (current_start_date - previous_end_date).days > 1:
            gap_start_date = previous_end_date + pd.Timedelta(days=1)
            gap_rows['start_date'].append(gap_start_date)

            gap_end_date = current_start_date - pd.Timedelta(days=1)
            gap_rows['end_date'].append(gap_end_date)

    df_gaps = pd.DataFrame(gap_rows)
    df_ipc = pd.concat([df_ipc, df_gaps], ignore_index=True)

    df_ipc = df_ipc.sort_values('start_date').reset_index(drop=True)

    # fill NA values with average of surrounding assessments
    if interpolate is True:
        df_ipc = df_ipc.interpolate(method='linear', limit_direction='both')

    return df_ipc


# %%
df_ipc = find_assessment_gaps(df_ipc, interpolate=True)

df_ipc

# %% [markdown]
# ### IPC CDR reference table

# %%
# figure 25 from https://www.ipcinfo.org/fileadmin/user_upload/ipcinfo/manual/IPC_Technical_Manual_3_Final.pdf
ipc_cdr = {
    'Crisis': {
        'lower_bound': 0.5 / 10000,
        'upper_bound': 0.99 / 10000,
    },
    'Emergency': {
        'lower_bound': 1 / 10000,
        'upper_bound': 1.99 / 10000,
    },
    'Catastrophe': {
        'lower_bound': 2 / 10000,
        'upper_bound': None,
    },
}

# %% [markdown]
# ### Gaza population

# %%
# average from IPC analyses
gaza_pop_total = 2.2 * 10**6

# %% [markdown]
# ## Assessments over time

# %%
df_melted = df_ipc.melt(
    id_vars=['start_date', 'end_date'],
    var_name='Phase',
    value_name='Percentage',
).melt(
    id_vars=['Phase', 'Percentage'],
    var_name='date_type',
    value_name='date',
)

# %%
chart_assessments = (
    alt.Chart(df_melted)
    .mark_area()
    .encode(
        x=alt.X('date:T').title('Period'),
        y=alt.Y('Percentage:Q').sort(None).stack('normalize'),
        color=alt.Color('Phase:N').sort(None),
    )
    .properties(
        title='Distribution of IPC phases over time',
        width=600,
        height=400,
    )
)

chart_assessments

# %% [markdown]
# ## Deaths based on IPC CDR


# %%
def calculate_expected_dead(row: pd.Series, lower: bool = True):
    """
    Calculate expected dead based on IPC assessment and CDR.

    Parameters:
    row (pd.Series): Series containing 'start_date', 'end_date', 'Emergency', and 'Catastrophe' columns.
    lower (bool): Whether to use the lower or upper bound of the CDR. Defaults to True.

    Returns:
    int: The expected number of dead.
    """

    expected_dead = 0

    # acute food insecurity levels for which mortality is calculated
    levels = ['Emergency', 'Catastrophe']

    for level in levels:
        if pd.isna(row[level]):
            continue

        # affected pop size
        sub_pop = row[level] * gaza_pop_total

        # cdr
        if lower is True:
            cdr = ipc_cdr[level]['lower_bound']
        else:
            cdr = (
                ipc_cdr[level]['upper_bound']
                if ipc_cdr[level]['upper_bound'] is not None
                else ipc_cdr[level]['lower_bound']
            )

        # duration
        duration = (row['end_date'] - row['start_date']).days

        # expected dead for given level, cdr, duration
        value = sub_pop * cdr * duration
        value = int(value)

        expected_dead += value

    return expected_dead


# %%
df_ipc['expected_dead_lower'] = df_ipc.apply(calculate_expected_dead, axis=1)

df_ipc['expected_dead_upper'] = df_ipc.apply(
    lambda x: calculate_expected_dead(x, lower=False), axis=1
)

df_ipc

# %%
# calculate cumulative totals
df_ipc['cumulative_lower'] = df_ipc['expected_dead_lower'].cumsum()
df_ipc['cumulative_upper'] = df_ipc['expected_dead_upper'].cumsum()


# %%
df_ipc

# %%
chart_ipc_cdr = (
    alt.Chart(df_ipc)
    .mark_area(opacity=0.5)
    .encode(
        alt.X('end_date:T').title(None),
        alt.Y('cumulative_lower:Q').title('Cumulative total'),
        alt.Y2('cumulative_upper:Q'),
    )
    .properties(
        title='Deaths expected based on IPC\'s crude death rate (source: IPC)',
        width=600,
        height=400,
    )
)

chart_ipc_cdr.save('../charts/casualties_ipc_cdr.png')

chart_ipc_cdr


# %%
def estimate_dead_for_date(df_ipc, col, date):
    """
    Estimate number of deaths based on IPC CDR for a specific date.
    """

    date = pd.to_datetime(date)

    for i in range(len(df_ipc)):
        if df_ipc.loc[i, 'start_date'] <= date <= df_ipc.loc[i, 'end_date']:
            estimate_base = df_ipc.loc[i - 1, col]
            estimate_range = df_ipc.loc[i, col] - df_ipc.loc[i - 1, col]
            period = (df_ipc.loc[i, 'end_date'] - df_ipc.loc[i - 1, 'end_date']).days
            period_pro_rated = (date - df_ipc.loc[i - 1, 'end_date']).days

            estimate = estimate_base + estimate_range / period * period_pro_rated
            estimate = int(estimate)

            return estimate


# %%
# determine lower and upper bounds
food_insecurity_lower = estimate_dead_for_date(
    df_ipc=df_ipc, col='cumulative_lower', date=datetime.date.today()
)
food_insecurity_upper = estimate_dead_for_date(
    df_ipc=df_ipc, col='cumulative_upper', date=datetime.date.today()
)

# %%
food_insecurity_lower

# %%
food_insecurity_upper
