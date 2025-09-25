# NSF-CoSEA workflow

This repository contains the scripts, notebooks, and SQL code used to process and analyze Georgia high school data for the NSF CoSEA project.

### Repository Structure

- **`output_394/` Contains all maps and figures**
- `data_logic_394.ipynb`: Main notebook with the analysis and data processing workflow
- `maps_394.py`: Script to generate all maps found in `output_394/` from the database
- `plots_394.ipynb` Generates violin- and scatterplots found in `output_394/`
- `sql/`: Contains 4 SQL scripts that generate final outputs: `tbl_approvedschools` and `tbl_cbg_finalassignment` in the database
- `etc/`: Includes `data.zip` with needed CSVs, `docs/` with documentation, and `old/` with unused code
