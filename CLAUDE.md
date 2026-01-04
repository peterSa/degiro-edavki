# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is `degiro-edavki` - a Python script that converts DeGiro CSV reports into XML formats suitable for importing into Slovenian tax forms (eDavki). The script converts trading data, dividends, and interest income into formats required by FURS (Slovenian tax authority).

## Commands

### Installation and Setup
```bash
pip install --upgrade git+https://github.com/jamsix/degiro-edavki.git
```

### Running the Script
```bash
# Basic usage
degiro-edavki degiro-csv-file-2021 [degiro-csv-file-2020] [degiro-csv-file-2019]

# With specific year
degiro-edavki -y 2022 degiro-csv-file-2022

# Test mode (for informational calculation only)
degiro-edavki -t degiro-csv-file-2022
```

### Development Commands
```bash
# Install in development mode
pip install -e .

# Run the script directly
python degiro_edavki.py [arguments]
```

## Architecture

### Core Files
- `degiro_edavki.py` - Main script containing the conversion logic
- `setup.py` - Package configuration for pip installation
- `generators/doh_obr.py` - Interest income report generator module

### Key Components

#### Main Script (`degiro_edavki.py`)
- Parses DeGiro CSV reports
- Fetches exchange rates from Bank of Slovenia (BSI)
- Handles stock splits and corporate actions
- Converts foreign currencies to EUR
- Generates XML files for Slovenian tax forms

#### Asset Classification
- `normalAssets = ["STK"]` - Regular stocks for Doh-KDVP form
- `derivateAssets = ["CFD", "OPT", "FUT", "FOP", "WAR"]` - Derivatives for D-IFI form
- `ignoreAssets = ["CASH", "CMDTY"]` - Assets to ignore

#### Output Files Generated
- `Doh-KDVP.xml` - Capital gains from securities
- `D-IFI.xml` - Gains from derivative financial instruments  
- `Doh-Div.xml` - Dividend income
- `Doh-Obr.xml` - Interest income

### Configuration Files
- `taxpayer.xml` - User's tax information (name, address, tax number)
- `companies.xml` - Company information for dividend reports (downloaded automatically)
- `relief-statements.xml` - Double taxation agreements (downloaded automatically)
- `degiro-affiliates.xml` - DeGiro subsidiary information (downloaded automatically)

### Data Sources
- DeGiro CSV reports (user provided)
- Bank of Slovenia exchange rates (fetched automatically from BSI API)
- Various XML configuration files (downloaded from GitHub repository)

## Key Features

### Currency Conversion
The script automatically converts foreign currency amounts to EUR using official Bank of Slovenia exchange rates for the transaction date.

### Stock Split Handling
Tracks and applies stock split adjustments from corporate actions to ensure accurate cost basis calculations.

### FIFO Cost Basis
Implements First-In-First-Out methodology for calculating capital gains/losses as required by Slovenian tax law.

### Test Mode
The `-t` flag allows running calculations for the current year by shifting dates to the previous year, enabling informational tax calculations before year-end.

## Important Notes

- This is a tax-related tool - accuracy is critical
- The script processes real financial data and generates official tax documents
- Generated XML files are imported directly into Slovenian eDavki system
- Exchange rate conversion uses official BSI rates to comply with tax regulations
- The project has been fully adapted for DeGiro CSV processing from the original IB-focused version