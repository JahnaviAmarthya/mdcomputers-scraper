#!/usr/bin/env bash

# Prints Company Name, Headquarters Location, and Founding Year
# from the S&P 500 constituents CSV, sorted by founding year.

set -euo pipefail

CSV_URL="https://raw.githubusercontent.com/datasets/s-and-p-500-companies/refs/heads/main/data/constituents.csv"

printf "%-6s %-45s %s\n" "Year" "Company" "Location"

curl -sL "$CSV_URL" | gawk '
BEGIN {
    # FPAT splits on unquoted fields OR quoted "..." fields, so commas
    # embedded inside quoted values (e.g. "Saint Paul, Minnesota") are
    # kept together as a single field instead of being split apart.
    FPAT = "([^,]*)|(\"[^\"]*\")"
    OFS  = "\t"
}
NR == 1 { next }  # skip header row
{
    name     = $2
    location = $5
    founded  = $8

    gsub(/^"|"$/, "", name)
    gsub(/^"|"$/, "", location)
    gsub(/^"|"$/, "", founded)

    # The "Founded" field sometimes has extra notes, e.g.
    # "2013 (1888)" or "2020 (1915, United Technologies spinoff)".
    # Pull out the first 4-digit year to sort/display on.
    if (match(founded, /[0-9]{4}/)) {
        year = substr(founded, RSTART, RLENGTH)
    } else {
        year = "0000"
    }

    print year, name, location
}
' | sort -n -k1,1 | awk -F'\t' '{printf "%-6s %-45s %s\n", $1, $2, $3}'
