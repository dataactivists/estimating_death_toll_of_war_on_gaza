# utils.py

import pandas as pd


def add_full_date_range(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add full date range to df.
    """

    start_date = df['date'].min()
    end_date = df['date'].max()

    date_range = pd.date_range(start=start_date, end=end_date, freq='D')
    df_date_range = pd.DataFrame({'date': date_range})
    df = pd.merge(
        df_date_range,
        df,
        on='date',
        how='left',
    )

    return df
