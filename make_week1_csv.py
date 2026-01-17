import pandas as pd

IN_CSV = "Bike share ridership 2024-09.csv"
OUT_CSV = "Bike share ridership 2024-09_week1.csv"

COLUMNS = [
    "Trip Id",
    "Trip  Duration",
    "Start Station Id",
    "Start Time",
    "Start Station Name",
    "End Station Id",
    "End Time",
    "End Station Name",
    "Bike Id",
    "User Type",
    "Model",
]

def main():
    # load only needed columns (faster + less RAM)
    df = pd.read_csv(IN_CSV, usecols=COLUMNS)

    # parse Start Time like: 09/01/2024 00:00
    df["Start Time"] = pd.to_datetime(df["Start Time"], format="%m/%d/%Y %H:%M", errors="coerce")

    # keep first week of September (Sep 1 to Sep 7 inclusive)
    start = pd.Timestamp("2024-09-01 00:00:00")
    end_exclusive = pd.Timestamp("2024-09-08 00:00:00")

    week1 = df[(df["Start Time"] >= start) & (df["Start Time"] < end_exclusive)].copy()

    # write output
    week1.to_csv(OUT_CSV, index=False)

    print(f"Wrote: {OUT_CSV}")
    print(f"Rows kept: {len(week1):,}")

if __name__ == "__main__":
    main()
