using CSV
using DataFrames

# Folder containing the CSVs; @__DIR__ keeps paths relative to this script.
csv_dir = @__DIR__

# Helper to load a CSV into a DataFrame.
load_csv(filename) = CSV.read(joinpath(csv_dir, filename), DataFrame)

acsomega_df = load_csv("ACSOmegaSGReady.csv")
liverpool_df = load_csv("LiverpoolSGReady.csv")
obelix_df = load_csv("ObelixSGReady.csv")

