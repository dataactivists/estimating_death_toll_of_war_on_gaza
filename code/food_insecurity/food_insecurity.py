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
import sys
from pathlib import Path
from typing import Dict, Optional, Union

import altair as alt
import pandas as pd

# %% [markdown]
# ## Data

# %% [markdown]
# ### IPC assessments

# %%
# from https://www.ipcinfo.org/ipc-country-analysis/en/
ipc_assessments = 'data/food_insecurity/ipc_assessments.csv'

script_dir = Path('__file__').resolve().parent
root_dir = script_dir.parent
data_file_path = root_dir / ipc_assessments
data_file_path = str(data_file_path.resolve())

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
# ### Data cleaning

# %%
def load_and_preprocess_data(
    file_path: Optional[Union[str, Path]] = None
) -> pd.DataFrame:
    """
    Load IPC assessments and clean the data.
    """

    # load ipc_assessments.csv file in data dir
    if file_path is None:
        file_path = data_file_path

    df_ipc = pd.read_csv(file_path)

    # drop cols
    df_ipc = df_ipc.drop(columns=['type', 'url'])

    # convert date cols to datetime
    df_ipc['start_date'] = pd.to_datetime(df_ipc['start_date'])
    df_ipc['end_date'] = pd.to_datetime(df_ipc['end_date'])

    # sort rows
    df_ipc = df_ipc.sort_values('start_date')

    return df_ipc


# %%
df_ipc = load_and_preprocess_data(data_file_path)

df_ipc


# %%
def create_linear_timeline(df_ipc: pd.DataFrame) -> pd.DataFrame:
    """
    Determine linear timeline across assessments.
    """

    linear_timeline_rows = []

    for _, row in df_ipc.iterrows():
        # check if linear_timeline_rows is empty or no overlap with linear_timeline_row
        if (
            not linear_timeline_rows
            or row['start_date'] > linear_timeline_rows[-1]['end_date']
        ):
            linear_timeline_rows.append(row)

        # if overlap, set end_date of last linear row to before start_date of new row
        else:
            linear_timeline_rows[-1]['end_date'] = min(
                linear_timeline_rows[-1]['end_date'],
                row['start_date'] - pd.Timedelta(days=1),
            )

            linear_timeline_rows.append(row)

    df_linear = pd.DataFrame(linear_timeline_rows)

    df_linear = df_linear.sort_values('start_date').reset_index(drop=True)

    return df_linear


# %%
# determine linear timeline across assessments
df_ipc = create_linear_timeline(df_ipc)

df_ipc


# %%
def find_assessment_gaps(df_ipc: pd.DataFrame, interpolate: bool = True) -> pd.DataFrame:
    """
    Find gaps in assessments and interpolate values based on surrounding assessments.
    """

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
# ## Assessments over time


# %%
def generate_assessments_chart(
    df_ipc: pd.DataFrame,
    title: Optional[str] = None,
    save: bool = True,
    filename: Optional[str] = 'chart.png',
) -> alt.Chart:
    """
    Visualise evolution in IPC assessments
    """

    # convert to long format
    df_melted = df_ipc.melt(
        id_vars=['start_date', 'end_date'],
        var_name='Phase',
        value_name='Percentage',
    ).melt(
        id_vars=['Phase', 'Percentage'],
        var_name='date_type',
        value_name='date',
    )

    # generate chart
    chart_assessments = (
        alt.Chart(df_melted)
        .mark_area()
        .encode(
            x=alt.X('date:T').title('Period'),
            y=alt.Y('Percentage:Q').sort(None).stack('normalize'),
            color=alt.Color('Phase:N').sort(None),
        )
        .properties(
            title=title or '',
            width=600,
            height=400,
        )
    )

    # save chart
    if save is True:
        chart_file_path = CHARTS_DIR / filename
        chart_assessments.save(chart_file_path)

    return chart_assessments


# %%
# generate assessments chart
chart_assessments = generate_assessments_chart(
    df_ipc,
    title='Distribution of IPC phases over time',
    filename='ipc_assessments.png',
)

chart_assessments

# %% [markdown]
# ## Deaths based on IPC CDR


# %%
def calculate_expected_deaths(row: pd.Series) -> Dict[str, int]:
    """
    Calculate expected number of deaths based on IPC assessment and CDR, with lower and upper bounds.
    """

    expected_deaths = {
        'lower': 0,
        'upper': 0,
    }

    # acute food insecurity levels for which mortality is calculated
    levels = ['Emergency', 'Catastrophe']

    for level in levels:
        if pd.isna(row[level]):
            continue

        # affected pop size
        sub_pop = row[level] * gaza_pop_total

        # cdr
        cdr_lower = ipc_cdr[level]['lower_bound']
        cdr_upper = (
            ipc_cdr[level]['upper_bound']
            if ipc_cdr[level]['upper_bound'] is not None
            else ipc_cdr[level]['lower_bound']
        )

        # duration
        duration = (row['end_date'] - row['start_date']).days

        # expected deaths for given level, cdr, duration
        value_lower = int(sub_pop * cdr_lower * duration)
        value_upper = int(sub_pop * cdr_upper * duration)

        expected_deaths['lower'] += value_lower
        expected_deaths['upper'] += value_upper

    return expected_deaths


# %%
def calculate_expected_cumulative_deaths(df_ipc: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate expected deaths and cumulative totals.
    """

    # calculate expected deaths
    expected_deaths = df_ipc.apply(calculate_expected_deaths, axis=1)

    # add cols with expected deaths
    df_ipc = pd.concat(
        [
            df_ipc,
            pd.json_normalize(expected_deaths).rename(
                lambda x: f'expected_deaths_{x}', axis=1
            ),
        ],
        axis=1,
    )

    # calculate cumulative totals
    df_ipc['cumulative_lower'] = df_ipc['expected_deaths_lower'].cumsum()
    df_ipc['cumulative_upper'] = df_ipc['expected_deaths_upper'].cumsum()

    return df_ipc


# %%
df_ipc = calculate_expected_cumulative_deaths(df_ipc)

df_ipc


# %%
def generate_ipc_cdr_chart(
    df_ipc: pd.DataFrame,
    title: Optional[str] = None,
    save: bool = True,
    filename: Optional[str] = 'chart.png',
) -> alt.Chart:
    """
    Visualise deaths from IPC's phase assessments and CDR.
    """

    # generate chart
    chart_ipc_cdr = (
        alt.Chart(df_ipc)
        .mark_area(opacity=0.5)
        .encode(
            alt.X('end_date:T').title(None),
            alt.Y('cumulative_lower:Q').title('Cumulative total'),
            alt.Y2('cumulative_upper:Q'),
        )
        .properties(
            title=title or '',
            width=600,
            height=400,
        )
    )

    # save chart
    if save is True:
        chart_file_path = CHARTS_DIR / filename
        chart_ipc_cdr.save(chart_file_path)

    return chart_ipc_cdr


# %%
# generate IPC CDR chart
chart_ipc_cdr = generate_ipc_cdr_chart(
    df_ipc,
    title='Deaths expected based on IPC\'s crude death rate (source: IPC)',
    filename='ipc_cdr_deaths.png',
)

chart_ipc_cdr


# %%
def estimate_deaths_for_date(
    df_ipc: pd.DataFrame, date: Union[str, datetime.datetime] = datetime.date.today()
) -> Dict[str, int]:
    """
    Estimate number of deaths based on IPC CDR for a specific date.
    """

    estimates = {}

    if date is None:
        date = datetime.date.today()

    date = pd.to_datetime(date)
    estimates['date'] = date

    for i in range(len(df_ipc)):
        # find assessment that contains date
        if df_ipc.loc[i, 'start_date'] <= date <= df_ipc.loc[i, 'end_date']:
            # calculate lower and upper bounds of expected deaths
            for bound in ['lower', 'upper']:
                estimate_base = df_ipc.loc[i - 1, f'cumulative_{bound}']
                estimate_range = (
                    df_ipc.loc[i, f'cumulative_{bound}']
                    - df_ipc.loc[i - 1, f'cumulative_{bound}']
                )
                period = (df_ipc.loc[i, 'end_date'] - df_ipc.loc[i - 1, 'end_date']).days
                period_pro_rated = (date - df_ipc.loc[i - 1, 'end_date']).days

                estimate = estimate_base + estimate_range / period * period_pro_rated
                estimate = int(estimate)

                estimates[bound] = estimate

            return estimates

    return None


# %%
# determine lower and upper bounds
food_insecurity_casualties = estimate_deaths_for_date(
    df_ipc=df_ipc, date=datetime.date.today()
)

food_insecurity_casualties


# %%
def assess_food_insecurity(
    file_path: str = None,
    date: Union[str, datetime.datetime] = None,
    save_charts: bool = True,
) -> Dict[str, Union[Dict[str, int], alt.Chart]]:
    """
    Calculate expected deaths for a specific date given IPC assessments.
    """

    # load IPC assessments and clean the data.
    df_ipc = load_and_preprocess_data(file_path)

    # determine linear timeline across assessments.
    df_ipc = create_linear_timeline(df_ipc)

    # find gaps in assessments and interpolate values based on surrounding assessments.
    df_ipc = find_assessment_gaps(df_ipc=df_ipc, interpolate=True)

    # visualise evolution in IPC assessments
    chart_assessments = generate_assessments_chart(
        df_ipc,
        title='Distribution of IPC phases over time',
        save=save_charts,
        filename='ipc_assessments.png',
    )

    # calculate expected deaths and cumulative totals
    df_ipc = calculate_expected_cumulative_deaths(df_ipc)

    # save cleaned data
    df_ipc.to_csv(file_path.replace('.csv', '_clean.csv'), index=False)

    # visualise deaths from IPC's phase assessments and CDR
    charts_ipc_cdr = generate_ipc_cdr_chart(
        df_ipc,
        title='Deaths expected based on IPC\'s crude death rate (source: IPC)',
        filename='ipc_cdr_deaths.png',
    )

    # estimate number of deaths based on IPC CDR for a specific date
    food_insecurity_casualties = estimate_deaths_for_date(df_ipc, date=date)

    return {
        'food_insecurity_casualties': food_insecurity_casualties,
        'chart_assessments': chart_assessments,
        'charts_ipc_cdr': charts_ipc_cdr,
    }
