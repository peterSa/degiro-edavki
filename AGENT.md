# AGENT.md

This file provides additional guidance for AI agents working on this repository.

## Project Context

`degiro-edavki` is a tax compliance tool that converts DeGiro broker CSV exports into XML formats required by FURS (Slovenian Tax Authority). This is a **financial reporting system** where accuracy is critical - errors can result in incorrect tax filings.

## Key Architectural Patterns

### Input Processing
- CSV parsing: DeGiro CSV format with specific column structure
- Date handling: Transaction dates are critical for exchange rate lookup
- Currency conversion: All amounts must be converted to EUR using official BSI rates

### Core Algorithms
- **FIFO cost basis**: First-In-First-Out for calculating capital gains/losses
- **Stock split adjustment**: Apply split ratios to historical holdings
- **Corporate actions**: Track and adjust for mergers, spinoffs, etc.

### Output Generation
- XML templates conforming to FURS XML Schema Definition (XSD)
- Separate forms for different tax categories (KDVP, IFI, Div, Obr)

## Code Conventions

### File Structure
- Main logic in `degiro_edavki.py` (monolithic but functional)
- Modular generators in `generators/` directory
- Setup configuration in `setup.py`

### Variable Naming
- Descriptive but verbose names are acceptable for clarity in tax calculations
- Hungarian notation is not used
- Snake_case for Python variables/functions

### Error Handling
- Input validation is critical - verify CSV structure before processing
- Graceful failure with clear error messages for users
- Exchange rate fetch failures should halt execution

## Testing Strategy

### When to Add Tests
- New asset types or tax categories
- Corporate action handling logic
- Currency conversion edge cases
- Stock split calculations
- FIFO cost basis logic

### Test Data
- Use sample DeGiro CSV files (provided by users)
- Mock exchange rate API responses
- Test edge cases: splits, partial positions, multiple years

### Running Tests
```bash
python degiro_edavki.py -t sample-2022.csv  # Test mode
# Compare generated XML files with expected outputs
```

## Critical Considerations

### Tax Accuracy
- **Never** round intermediate calculations - only final amounts
- Use official BSI exchange rates for transaction dates
- Preserve precision throughout calculations
- Double-check all formulas against Slovenian tax law

### Data Integrity
- Validate CSV format before processing
- Check for missing or corrupted data
- Warn users about unsupported transaction types
- Log all calculations for audit purposes

### Currency Handling
- All conversions must use BSI rates (not other sources)
- Date-specific rates are required (not average rates)
- Handle EUR to EUR conversion (rate = 1.0)
- Fetch missing rates automatically or halt with error

## Common Tasks

### Adding Support for New Asset Types
1. Add asset type to appropriate classification list in `degiro_edavki.py`
2. Update XML generation logic if new tax form is required
3. Test with sample data containing new asset type
4. Document in README if needed

### Fixing Exchange Rate Issues
1. Check BSI API format (they may change it)
2. Verify date format in exchange rate lookup
3. Ensure timezone handling is correct (UTC vs local)
4. Add caching to avoid repeated API calls

### Updating XML Templates
1. Get latest XSD from FURS website
2. Verify required fields and data types
3. Update XML generation code accordingly
4. Test XML validation against official schema

### Adding New Corporate Actions
1. Identify action type in DeGiro CSV
2. Add parsing logic to detect action
3. Implement appropriate adjustment (split ratio, etc.)
4. Update position tracking
5. Test with historical data

## Performance Considerations

- Exchange rate API calls should be minimized (cache results)
- Large CSV files (>10,000 rows) may need optimization
- Memory usage scales with number of open positions
- Consider chunking for multi-year imports

## User Experience

- Clear error messages explaining what went wrong
- Progress indicators for long-running operations
- Verbose mode for debugging (-v flag if added)
- Help text should be comprehensive

## Dependencies

- Python standard library (prefer over external deps)
- `requests` for HTTP (exchange rates, config files)
- `xml.etree.ElementTree` for XML generation
- `csv` module for CSV parsing

## Security & Privacy

- Never log or output sensitive financial data
- Validate all downloaded XML files from GitHub
- Taxpayer data should be read from local file only
- No API keys or secrets in code

## When in Doubt

- Preserve existing behavior unless explicitly changing it
- Add comments explaining complex tax calculations
- Test with real user data if possible
- Consult FURS documentation for ambiguous requirements
- Ask user if unsure about tax law interpretation
