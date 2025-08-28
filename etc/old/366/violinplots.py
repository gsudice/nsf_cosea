import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.patches import Patch
import sqlalchemy
import numpy as np

# Connect to the database
engine = sqlalchemy.create_engine(
    "postgresql://cosea_user:CoSeaIndex@pgsql.dataconn.net:5432/cosea_db"
)

# Load school data
school_df = pd.read_sql('SELECT * FROM "2024".tbl_approvedschools', engine)
school_df.columns = school_df.columns.str.lower()

# Load RI columns
ri_df = pd.read_sql(
    'SELECT "UNIQUESCHOOLID", "RI_White", "RI_Black", "RI_Asian", "RI_Hispanic" '
    'FROM census.gadoe2024',
    engine
)
ri_df.columns = ri_df.columns.str.lower()
school_metrics = school_df.merge(ri_df, on="uniqueschoolid", how="left")

# Load catchment block‐group 
assignment_df = pd.read_sql(
    'SELECT "UNIQUESCHOOLID", "GEOID", "distance" FROM "2024".tbl_cbg_finalassignment',
    engine
)
assignment_df.columns = assignment_df.columns.str.lower()

# Load ACS block‐group data
census_df = pd.read_sql('SELECT * FROM census.acs2023_combined', engine)
census_df.columns = census_df.columns.str.lower()

# Join catchment areas to ACS on GEOID
df_cbg = assignment_df.merge(census_df, on="geoid", how="inner")

# Compute weighted‐average education/access metrics
waea_cols = [
    "edu_less_than_hs",
    "edu_hs_or_more",
    "without_internet_subscription",
    "households_no_computer"
]
waea = (
    df_cbg
    .groupby("uniqueschoolid")
    .apply(lambda g: {
        col: g[col].sum() / g["total_population"].sum()
        for col in waea_cols
    })
    .apply(pd.Series)
    .reset_index()
)
# convert to percentages
waea[waea_cols] *= 100
waea.rename(
    columns={col: f"weighted_avg_{col}" for col in waea_cols},
    inplace=True
)

# Compute population‐weighted average per-capita income
df_income = df_cbg.dropna(subset=["total_population", "percapita_income_total"])
income = (
    df_income
    .groupby("uniqueschoolid")
    .apply(lambda g: (
        (g["total_population"] * g["percapita_income_total"]).sum()
        / g["total_population"].sum()
    ))
    .reset_index(name="total_pop_weighted_avg_income")
)

# Compute harmonic mean distances
def harmonic_weighted_distance(df, distance_col, pop_cols):
    rows = []
    for uid, grp in df.groupby("uniqueschoolid"):
        row = {"uniqueschoolid": uid}
        for col in pop_cols:
            num = grp[col].sum()
            denom = (grp[col] / grp[distance_col]).sum()
            row[f"{col}_population_avg_distance"] = num / denom if denom != 0 else None
        rows.append(row)
    return pd.DataFrame(rows)

pop_cols = [
    "white_alone_non_hispanic",
    "black_alone_non_hispanic",
    "asian_alone_non_hispanic",
    "hispanic_or_latino"
]
distance = harmonic_weighted_distance(df_cbg, "distance", pop_cols)

# Merge all census‐derived metrics
metrics = waea.merge(income, on="uniqueschoolid", how="outer")
metrics = metrics.merge(distance, on="uniqueschoolid", how="outer")

# Final join: school data + RI + metrics
df = school_metrics.merge(metrics, on="uniqueschoolid", how="left")

# Prepare for plotting
soft_palette = {"Underrepresented": "#FDBF6F", "Overrepresented": "#A6CEE3"}

variables = {
    "Income": {
        "columns": {
            "White":    ("ri_white",   "total_pop_weighted_avg_income"),
            "Black":    ("ri_black",   "total_pop_weighted_avg_income"),
            "Asian":    ("ri_asian",   "total_pop_weighted_avg_income"),
            "Hispanic": ("ri_hispanic","total_pop_weighted_avg_income")
        },
        "xlabel":      "Population-Weighted Avg. Per Capita Income in USD (with quartiles)",
        "title_race":  "Distribution of $RI_X$ and Income by Race",
        "title_locale":"Distribution of $RI_X$ and Income by Locale"
    },
    "Harmonic Mean Distance": {
        "columns": {
            "White":    ("ri_white",  "white_alone_non_hispanic_population_avg_distance"),
            "Black":    ("ri_black",  "black_alone_non_hispanic_population_avg_distance"),
            "Asian":    ("ri_asian",  "asian_alone_non_hispanic_population_avg_distance"),
            "Hispanic": ("ri_hispanic","hispanic_or_latino_population_avg_distance")
        },
        "xlabel":      "Harmonic Mean of Population-Distance in meters (with quartiles)",
        "title_race":  "Distribution of $RI_X$ and Distance by Race",
        "title_locale":"Distribution of $RI_X$ and Distance by Locale"
    },
    "No Computer": {
        "columns": {
            "White":    ("ri_white",  "weighted_avg_households_no_computer"),
            "Black":    ("ri_black",  "weighted_avg_households_no_computer"),
            "Asian":    ("ri_asian",  "weighted_avg_households_no_computer"),
            "Hispanic": ("ri_hispanic","weighted_avg_households_no_computer")
        },
        "xlabel":      "Weighted % of Households Without Computer (with quartiles)",
        "title_race":  "Distribution of $RI_X$ and No Computer Access by Race",
        "title_locale":"Distribution of $RI_X$ and No Computer Access by Locale"
    },
    "Comp But No Internet": {
        "columns": {
            "White":    ("ri_white",  "weighted_avg_without_internet_subscription"),
            "Black":    ("ri_black",  "weighted_avg_without_internet_subscription"),
            "Asian":    ("ri_asian",  "weighted_avg_without_internet_subscription"),
            "Hispanic": ("ri_hispanic","weighted_avg_without_internet_subscription")
        },
        "xlabel":      "Weighted % Without Internet Subscription (with quartiles)",
        "title_race":  "Distribution of $RI_X$ and No Internet Access by Race",
        "title_locale":"Distribution of $RI_X$ and No Internet Access by Locale"
    },
    "Less than High School": {
        "columns": {
            "White":    ("ri_white",  "weighted_avg_edu_less_than_hs"),
            "Black":    ("ri_black",  "weighted_avg_edu_less_than_hs"),
            "Asian":    ("ri_asian",  "weighted_avg_edu_less_than_hs"),
            "Hispanic": ("ri_hispanic","weighted_avg_edu_less_than_hs")
        },
        "xlabel":      "Weighted % with <HS Degree (with quartiles)",
        "title_race":  "Distribution of $RI_X$ and <HS Education by Race",
        "title_locale":"Distribution of $RI_X$ and <HS Education by Locale"
    },
    "Completed HS and Higher": {
        "columns": {
            "White":    ("ri_white",  "weighted_avg_edu_hs_or_more"),
            "Black":    ("ri_black",  "weighted_avg_edu_hs_or_more"),
            "Asian":    ("ri_asian",  "weighted_avg_edu_hs_or_more"),
            "Hispanic": ("ri_hispanic","weighted_avg_edu_hs_or_more")
        },
        "xlabel":      "Weighted % Completing HS or More (with quartiles)",
        "title_race":  "Distribution of $RI_X$ and HS Completion by Race",
        "title_locale":"Distribution of $RI_X$ and HS Completion by Locale"
    }
}

def draw_consistent_grid_lines(ax, y_values, x_max):
    for y in y_values:
        for line in ax.lines[:]:
            if len(line.get_ydata()) == 2 and abs(line.get_ydata()[0] - y) < 0.01:
                line.remove()
        ln = ax.axhline(y=y, xmin=0, xmax=1, linestyle='--', linewidth=1, alpha=1.0, zorder=0)
        ln.set_clip_on(False)
        ln.set_dashes([5, 2])

for var_name, meta in variables.items():
    cleaned = []
    for race, (ri_col, val_col) in meta["columns"].items():
        temp_all = df[[ri_col, val_col, "locale"]].dropna().copy()
        temp_all["race"] = race
        temp_all["representation"] = "Parity"
        temp_all.loc[temp_all[ri_col] > 0.05, "representation"] = "Overrepresented"
        temp_all.loc[temp_all[ri_col] < -0.05, "representation"] = "Underrepresented"
        tmp = temp_all[temp_all["representation"] != "Parity"].copy()
        tmp.rename(columns={val_col: var_name.lower()}, inplace=True)
        cleaned.append(tmp)

    df_violin = pd.concat(cleaned, ignore_index=True)

    # Race‐wise violin
    fig, ax_race = plt.subplots(figsize=(12, 7), dpi=300)
    sns.violinplot(
        data=df_violin,
        x=var_name.lower(),
        y="race",
        hue="representation",
        split=True,
        hue_order=["Overrepresented", "Underrepresented"],
        palette=soft_palette,
        cut=0, bw=0.2, scale="width", gap=0.2, inner="quart",
        ax=ax_race
    )
    ax_race.set_xlim(left=0)
    ax_race.set_title(meta["title_race"], fontsize=14)
    ax_race.set_xlabel(meta["xlabel"], fontsize=12)
    ax_race.set_ylabel("Race", fontsize=12, labelpad=40)
    ax_race.grid(axis='y', linestyle='--', alpha=0.3)

    races = df_violin["race"].unique()
    yticks = range(len(races))
    ax_race.set_yticks(yticks)
    ax_race.set_yticklabels(races, fontsize=9)
    ax_race.text(-0.07, 0.97, "Count", transform=ax_race.transAxes,
                 fontsize=8, ha='right', va='bottom', fontweight='bold')
    draw_consistent_grid_lines(ax_race, yticks, ax_race.get_xlim()[1]*0.95)

    for i, race in enumerate(races):
        race_all = df[[meta["columns"][race][0], "locale"]].dropna().copy()
        race_all["representation"] = "Parity"
        race_all.loc[race_all[meta["columns"][race][0]] > 0.05, "representation"] = "Overrepresented"
        race_all.loc[race_all[meta["columns"][race][0]] < -0.05, "representation"] = "Underrepresented"

        over = (race_all["representation"] == "Overrepresented").sum()
        par  = (race_all["representation"] == "Parity").sum()
        under= (race_all["representation"] == "Underrepresented").sum()

        plt.text(-0.07, i+0.15, f"↓{under}", transform=ax_race.get_yaxis_transform(),
                 fontsize=9, ha='right', va='center')
        plt.text(-0.07, i,        f"={par}",   transform=ax_race.get_yaxis_transform(),
                 fontsize=9, ha='right', va='center')
        plt.text(-0.07, i-0.15,   f"↑{over}",  transform=ax_race.get_yaxis_transform(),
                 fontsize=9, ha='right', va='center')

    ax_race.legend_.remove()
    plt.legend(
        handles=[
            Patch(facecolor=soft_palette["Overrepresented"], label="Overrepresented (>+0.05)"),
            Patch(facecolor=soft_palette["Underrepresented"], label="Underrepresented (<-0.05)")
        ],
        title="$RI_X$",
        loc="upper right",
        fontsize=8,
        title_fontsize=9,
        borderpad=0.3,
        labelspacing=0.3
    )
    ax_race.text(0.85, 0.78,
                 "Count symbols:\n↑ : Overrepresented\n= : Parity\n↓ : Underrepresented",
                 transform=ax_race.transAxes,
                 fontsize=8, ha='left', va='top',
                 bbox=dict(boxstyle="round,pad=0.5", facecolor='white', alpha=0.8,
                           edgecolor='gray', linewidth=0.5))
    plt.tight_layout()
    plt.subplots_adjust(left=0.15)
    plt.savefig(f'output/violin_race_{var_name.lower().replace(" ", "_")}.png')
    plt.close()

    # Locale‐wise violin
    fig, ax_locale = plt.subplots(figsize=(12, 7), dpi=300)
    sns.violinplot(
        data=df_violin,
        x=var_name.lower(),
        y="locale",
        hue="representation",
        split=True,
        hue_order=["Overrepresented", "Underrepresented"],
        palette=soft_palette,
        cut=0, bw=0.2, scale="width", gap=0.2, inner="quart",
        ax=ax_locale
    )
    ax_locale.set_xlim(left=0)
    ax_locale.set_title(meta["title_locale"], fontsize=14)
    ax_locale.set_xlabel(meta["xlabel"], fontsize=12)
    ax_locale.set_ylabel("Locale", fontsize=12, labelpad=40)
    ax_locale.grid(axis='y', linestyle='--', alpha=0.3)

    locales = df_violin["locale"].unique()
    yticks = range(len(locales))
    ax_locale.set_yticks(yticks)
    ax_locale.set_yticklabels(locales, fontsize=9)
    ax_locale.text(-0.07, 0.97, "Count", transform=ax_locale.transAxes,
                   fontsize=8, ha='right', va='bottom')
    draw_consistent_grid_lines(ax_locale, yticks, ax_locale.get_xlim()[1]*0.95)

    for i, loc in enumerate(locales):
        counts = {"Overrepresented": 0, "Parity": 0, "Underrepresented": 0}
        for race in variables[var_name]["columns"]:
            sub = df[(df["locale"] == loc) & (~df[f"ri_{race.lower()}"].isna())].copy()
            sub["representation"] = "Parity"
            sub.loc[sub[f"ri_{race.lower()}"] > 0.05, "representation"] = "Overrepresented"
            sub.loc[sub[f"ri_{race.lower()}"] < -0.05, "representation"] = "Underrepresented"
            for rep in counts:
                counts[rep] += (sub["representation"] == rep).sum()

        plt.text(-0.07, i+0.15, f"↓{counts['Underrepresented']}",
                 transform=ax_locale.get_yaxis_transform(), fontsize=9, ha='right', va='center')
        plt.text(-0.07, i,        f"={counts['Parity']}",
                 transform=ax_locale.get_yaxis_transform(), fontsize=9, ha='right', va='center')
        plt.text(-0.07, i-0.15,   f"↑{counts['Overrepresented']}",
                 transform=ax_locale.get_yaxis_transform(), fontsize=9, ha='right', va='center')

    ax_locale.legend_.remove()
    plt.legend(
        handles=[
            Patch(facecolor=soft_palette["Overrepresented"], label="Overrepresented (>+0.05)"),
            Patch(facecolor=soft_palette["Underrepresented"], label="Underrepresented (<-0.05)")
        ],
        title="$RI_X$",
        loc="upper right",
        fontsize=8,
        title_fontsize=9,
        borderpad=0.3,
        labelspacing=0.3
    )
    ax_locale.text(0.85, 0.78,
                   "Count symbols:\n↑ : Overrepresented\n= : Parity\n↓ : Underrepresented",
                   transform=ax_locale.transAxes,
                   fontsize=8, ha='left', va='top',
                   bbox=dict(boxstyle="round,pad=0.5", facecolor='white', alpha=0.8,
                             edgecolor='gray', linewidth=0.5))
    plt.tight_layout()
    plt.subplots_adjust(left=0.15)
    plt.savefig(f'output/violin_locale_{var_name.lower().replace(" ", "_")}.png')
    plt.close()

print("All plots have been generated successfully.")