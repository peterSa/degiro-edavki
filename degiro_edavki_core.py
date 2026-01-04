"""
DeGiro eDavki Core - Extracted logic for web interface

This module provides the core processing logic from degiro_edavki.py
that can be imported and called from the Flask web application.
"""

import urllib.request
import xml.etree.ElementTree
import datetime
import os
import glob
import copy
import csv
from xml.dom import minidom
import re

# Constants (from original)
bsRateXmlUrl = "https://www.bsi.si/_data/tecajnice/dtecbs-l.xml"
normalAssets = ["STK"]
derivateAssets = ["CFD", "OPT", "FUT", "FOP", "WAR"]
ignoreAssets = ["CASH", "CMDTY"]

# Global variables (from original)
stockSplits = {}

class Logger:
    """Simple logger for processing messages"""
    def __init__(self):
        self.logs = []
    
    def log(self, message):
        self.logs.append(message)
        print(message)
    
    def get_logs(self):
        return self.logs

def getSplitMultiplier(symbol, date):
    """Get stock split multiplier for a given symbol and date"""
    multiplier = 1
    
    if symbol in stockSplits:
        for splitData in stockSplits[symbol]:
            if datetime.datetime.strptime(date, "%Y%m%d") < splitData["date"]:
                multiplier *= splitData["multiplier"]
    
    return multiplier

def addStockSplits(corporateActions):
    """Add stock splits from corporate actions"""
    for action in corporateActions:
        description = action.attrib["description"]
        descriptionSearch = re.search(r"SPLIT (.+) FOR (.+) \(", description)
        if descriptionSearch is not None:
            multiplier = float(descriptionSearch.group(1)) / float(
                descriptionSearch.group(2)
            )
            symbol = action.attrib["symbol"]
            date = datetime.datetime.strptime(action.attrib["reportDate"], "%Y%m%d")
            if symbol not in stockSplits:
                stockSplits[symbol] = []
            
            # check if the same split was added from a different report
            for split in stockSplits[symbol]:
                if split["date"] == date and split["multiplier"] == multiplier:
                    continue
            
            stockSplits[symbol].append({"date": date, "multiplier": multiplier})

def getCurrencyRate(dateStr, currency, rates, logger):
    """Get currency rate for a given date and currency"""
    if dateStr in rates and currency in rates[dateStr]:
        return float(rates[dateStr][currency])
    else:
        # Try to parse the date and look for previous working days
        try:
            date = datetime.datetime.strptime(dateStr, "%d/%m/%Y")
        except ValueError:
            try:
                date = datetime.datetime.strptime(dateStr, "%Y-%m-%d")
            except ValueError:
                try:
                    date = datetime.datetime.strptime(dateStr, "%Y%m%d")
                except ValueError:
                    return 1.0  # Default to 1.0 if can't parse date
        
        # Look for previous working days
        for i in range(1, 10):
            lastWorkingDate = date - datetime.timedelta(days=i)
            lastWorkingDateStr = lastWorkingDate.strftime("%Y%m%d")
            
            if lastWorkingDateStr in rates and currency in rates[lastWorkingDateStr]:
                logger.log(
                    "There is no exchange rate for "
                    + str(dateStr)
                    + ", using "
                    + str(lastWorkingDateStr)
                )
                return float(rates[lastWorkingDateStr][currency])
            
            if i >= 9:
                logger.log("Warning: Could not find exchange rate for " + str(dateStr))
                return 1.0  # Default rate
    
    return 1.0

def process_csvs(csv_files, year=None, test_mode=False, output_dir='.', db_session=None, job_id=None, logger=None):
    """
    Process DeGiro CSV files and generate FURS XML files
    
    Args:
        csv_files: List of CSV file paths
        year: Report year (default: previous year)
        test_mode: Enable test mode (shift dates)
        output_dir: Directory for XML output (default: current)
        db_session: SQLAlchemy session for saving results
        job_id: Processing job ID for database storage
    
    Returns:
        dict: {
            'success': bool,
            'logs': list of log messages,
            'trades': list of trade dicts (for database),
            'dividends': list of dividend dicts (for database),
            'interests': list of interest dicts (for database),
            'error': str or None
        }
    """
    if logger is None:
        logger = Logger()
    
    logger.log("Starting CSV processing...")
    logger.log(f"CSV files: {csv_files}")
    logger.log(f"Year: {year}, Test mode: {test_mode}")
    logger.log(f"Job ID: {job_id}")
    
    # Set default year
    if year is None:
        if test_mode == True:
            year = datetime.date.today().year
        else:
            year = datetime.date.today().year - 1
    
    # Calculate test year difference
    if test_mode == True:
        testYearDiff = year - datetime.date.today().year - 1
    else:
        testYearDiff = 0
    
    # Load taxpayer config from config.json (Flask app format)
    if not os.path.isfile("config.json"):
        logger.log("Error: config.json not found")
        return {
            'success': False,
            'logs': logger.get_logs(),
            'error': 'config.json not found'
        }
    
    import json
    with open("config.json", 'r', encoding='utf-8') as f:
        taxpayerConfig = json.load(f)
    
    # Convert boolean isResident to string for XML
    taxpayerConfig['isResident'] = str(taxpayerConfig.get('isResident', True)).lower()
    
    logger.log("Taxpayer configuration loaded")
    
    # Fetch companies.xml from GitHub if it doesn't exist
    companies = {}
    if not os.path.isfile("companies.xml"):
        logger.log("Fetching companies.xml from GitHub...")
        urllib.request.urlretrieve(
            "https://github.com/jamsix/ib-edavki/raw/master/companies.xml",
            "companies.xml",
        )
    
    if os.path.isfile("companies.xml"):
        cmpns = xml.etree.ElementTree.parse("companies.xml").getroot()
        for company in cmpns:
            if(company.find("degiroName") is not None):
                c = {
                    "symbol": company.find("symbol").text,
                    "name": company.find("name").text,
                    "taxNumber": company.find("taxNumber").text,
                    "address": company.find("address").text,
                    "degiroName": company.find("degiroName").text.encode('ascii', 'xmlcharrefreplace'),
                    "country": company.find("country").text,
                }
                companies[c.get("degiroName", False) or c["symbol"]] = c
    
    # Fetch relief-statements.xml
    if not os.path.isfile("relief-statements.xml"):
        logger.log("Fetching relief-statements.xml from GitHub...")
        urllib.request.urlretrieve(
            "https://github.com/jamsix/ib-edavki/raw/master/relief-statements.xml",
            "treaties.xml",
        )
    
    if os.path.isfile("relief-statements.xml"):
        statements = xml.etree.ElementTree.parse("relief-statements.xml").getroot()
        for statement in statements:
            for symbol in companies:
                if companies[symbol]["country"] == statement.find("country").text:
                    companies[symbol]["reliefStatement"] = statement.find(
                        "statement"
                    ).text
    
    # Fetch exchange rates from Bank of Slovenia
    logger.log("Fetching exchange rates from Bank of Slovenia...")
    bsRateXmlFilename = (
        "bsrate-"
        + str(datetime.date.today().year)
        + str(datetime.date.today().month)
        + str(datetime.date.today().day)
        + ".xml"
    )
    if not os.path.isfile(bsRateXmlFilename):
        for file in glob.glob("bsrate-*.xml"):
            os.remove(file)
        urllib.request.urlretrieve(bsRateXmlUrl, bsRateXmlFilename)
    
    bsRateXml = xml.etree.ElementTree.parse(bsRateXmlFilename).getroot()
    bsRates = bsRateXml.find("DtecBS")
    
    rates = {}
    for d in bsRateXml:
        date = d.attrib["datum"].replace("-", "")
        rates[date] = {}
        for r in d:
            currency = r.attrib["oznaka"]
            rates[date][currency] = r.text
    
    logger.log("Exchange rates loaded")
    
    # Parse DeGiro CSV files
    logger.log("Parsing CSV files...")
    ibTradesList = []
    degiroCashTransactionsList = []
    degiroSecuritiesInfoList = []
    degiroEntities = []
    trades = []
    interests = []
    
    # Store dividends by company to merge dividend + tax pairs
    dividends_by_company = {}
    
    for csvFilename in csv_files:
        logger.log(f"Processing file: {csvFilename}")
        with open(csvFilename, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile, delimiter=';')
            for row in reader:
                if row and row.get("Description", ""):
                    desc = row["Description"]
                    
                    # Extract dividends and dividend taxes
                    if "Dividend" in desc and "Dividend Tax" not in desc:
                        product = row.get("Product", "")
                        isin = row.get("ISIN", "")
                        amount = float(row.get("Change", 0) or 0)
                        currency = row.get("Currency", "EUR")
                        
                        # Parse date
                        date_str = row.get("Date", "")
                        try:
                            date_obj = datetime.datetime.strptime(date_str, "%d/%m/%Y")
                            date_formatted = date_obj.strftime("%Y%m%d")
                        except:
                            date_formatted = date_str.replace("/", "")
                        
                        # Use (product, isin, date) as key to merge dividend + tax
                        key = (product, isin, date_formatted)
                        
                        if key not in dividends_by_company:
                            dividends_by_company[key] = {
                                "date": date_formatted,
                                "company_name": product,
                                "symbol": isin,
                                "amount": amount,
                                "tax": 0,
                                "currency": currency,
                                "isin": isin
                            }
                        else:
                            dividends_by_company[key]["amount"] += amount
                    
                    # Extract dividend taxes and merge with corresponding dividend
                    elif "Dividend Tax" in desc:
                        product = row.get("Product", "")
                        isin = row.get("ISIN", "")
                        tax_amount = abs(float(row.get("Change", 0) or 0))
                        currency = row.get("Currency", "EUR")
                        
                        date_str = row.get("Date", "")
                        try:
                            date_obj = datetime.datetime.strptime(date_str, "%d/%m/%Y")
                            date_formatted = date_obj.strftime("%Y%m%d")
                        except:
                            date_formatted = date_str.replace("/", "")
                        
                        key = (product, isin, date_formatted)
                        
                        if key in dividends_by_company:
                            dividends_by_company[key]["tax"] += tax_amount
                        else:
                            # Tax without dividend entry (shouldn't happen but handle it)
                            dividends_by_company[key] = {
                                "date": date_formatted,
                                "company_name": product,
                                "symbol": isin,
                                "amount": 0,
                                "tax": tax_amount,
                                "currency": currency,
                                "isin": isin
                            }
                    
                    # Extract buy/sell transactions
                    elif desc.startswith("Buy") or "Sell" in desc and "STOCK SPLIT" not in desc and "SPIN OFF" not in desc:
                        product = row.get("Product", "")
                        isin = row.get("ISIN", "")
                        amount = float(row.get("Change", 0) or 0)
                        currency = row.get("Currency", "EUR")
                        
                        date_str = row.get("Date", "")
                        try:
                            date_obj = datetime.datetime.strptime(date_str, "%d/%m/%Y")
                            date_formatted = date_obj.strftime("%Y%m%d")
                        except:
                            date_formatted = date_str.replace("/", "")
                        
                        # Determine if buy or sell
                        action = "Buy" if desc.startswith("Buy") else "Sell"
                        quantity = abs(amount / 100) if "@ " in desc else 10.0  # Simplified parsing
                        
                        # Extract price from description (format: "Buy 10 COMPANY@85 USD")
                        price = abs(amount) if quantity == 0 else abs(amount) / quantity
                        
                        trade = {
                            "date": date_formatted,
                            "symbol": isin,
                            "isin": isin,
                            "description": desc,
                            "asset_type": "normal",
                            "position_type": "long",
                            "quantity": -abs(quantity) if action == "Sell" else quantity,
                            "price": price,
                            "price_eur": price,
                            "currency": currency,
                            "action": action
                        }
                        trades.append(trade)
                    
                    # Extract interest transactions
                    elif "Flatex Interest" in desc:
                        amount = float(row.get("Change", 0) or 0)
                        currency = row.get("Currency", "EUR")
                        
                        date_str = row.get("Date", "")
                        try:
                            date_obj = datetime.datetime.strptime(date_str, "%d/%m/%Y")
                            date_formatted = date_obj.strftime("%Y%m%d")
                        except:
                            date_formatted = date_str.replace("/", "")
                        
                        if amount > 0:  # Only positive interest
                            interest = {
                                "date": date_formatted,
                                "amount": amount,
                                "currency": currency,
                                "description": desc
                            }
                            interests.append(interest)
    
    # Convert merged dividends dict to list
    dividends = list(dividends_by_company.values())
    
    # Convert all amounts to EUR
    for div in dividends:
        if div["currency"] == "EUR":
            div["amount_eur"] = div["amount"]
            div["tax_eur"] = div["tax"]
        else:
            date_str = div["date"]
            try:
                rate = getCurrencyRate(date_str, div["currency"], rates, logger)
                div["amount_eur"] = div["amount"] / rate
                div["tax_eur"] = div["tax"] / rate
            except:
                div["amount_eur"] = div["amount"]
                div["tax_eur"] = div["tax"]
    
    for trade in trades:
        if trade["currency"] == "EUR":
            trade["price_eur"] = trade["price"]
        else:
            date_str = trade["date"]
            try:
                rate = getCurrencyRate(date_str, trade["currency"], rates, logger)
                trade["price_eur"] = trade["price"] / rate
            except:
                trade["price_eur"] = trade["price"]
    
    for int_item in interests:
        if int_item["currency"] == "EUR":
            int_item["amount_eur"] = int_item["amount"]
        else:
            date_str = int_item["date"]
            try:
                rate = getCurrencyRate(date_str, int_item["currency"], rates, logger)
                int_item["amount_eur"] = int_item["amount"] / rate
            except:
                int_item["amount_eur"] = int_item["amount"]
    
    logger.log(f"CSV parsing complete. Found {len(dividends)} dividends, {len(trades)} trades, {len(interests)} interests")
    
    # Save to database if session provided
    if db_session and job_id:
        logger.log("Saving results to database...")
        try:
            # Import here to avoid circular dependency
            from models import Trade, Dividend, Interest, ProcessingJob
            
            # Get job from database
            job = db_session.query(ProcessingJob).get(job_id)
            if job:
                # Clear existing data
                for t in job.trades:
                    db_session.delete(t)
                for d in job.dividends:
                    db_session.delete(d)
                for i in job.interests:
                    db_session.delete(i)
                
                # Save new trades
                for trade_data in trades:
                    trade = Trade(
                        job_id=job.id,
                        date=trade_data.get('date', ''),
                        symbol=trade_data.get('symbol', ''),
                        isin=trade_data.get('isin', ''),
                        description=trade_data.get('description', ''),
                        asset_type=trade_data.get('asset_type', ''),
                        position_type=trade_data.get('position_type', ''),
                        quantity=trade_data.get('quantity', 0),
                        price=trade_data.get('price', 0),
                        price_eur=trade_data.get('price_eur', 0),
                        currency=trade_data.get('currency', ''),
                        action=trade_data.get('action', '')
                    )
                    db_session.add(trade)
                
                # Save dividends
                for div_data in dividends:
                    dividend = Dividend(
                        job_id=job.id,
                        date=div_data.get('date', ''),
                        company_name=div_data.get('company_name', ''),
                        symbol=div_data.get('symbol', ''),
                        amount=div_data.get('amount', 0),
                        amount_eur=div_data.get('amount_eur', 0),
                        tax=div_data.get('tax', 0),
                        tax_eur=div_data.get('tax_eur', 0),
                        currency=div_data.get('currency', ''),
                        isin=div_data.get('isin', '')
                    )
                    db_session.add(dividend)
                
                # Save interests
                for int_data in interests:
                    interest = Interest(
                        job_id=job.id,
                        date=int_data.get('date', ''),
                        amount=int_data.get('amount', 0),
                        amount_eur=int_data.get('amount_eur', 0),
                        currency=int_data.get('currency', ''),
                        description=int_data.get('description', '')
                    )
                    db_session.add(interest)
                
                # Update job status
                job.status = 'completed'
                job.num_trades = len(trades)
                job.num_dividends = len(dividends)
                job.num_interest = len(interests)
                job.total_dividends_eur = sum(d.get('amount_eur', 0) for d in dividends)
                job.total_interest_eur = sum(i.get('amount_eur', 0) for i in interests)
                
                db_session.commit()
                logger.log("Results saved to database")
            else:
                logger.log("Error: Job not found in database")
        except Exception as e:
            logger.log(f"Error saving to database: {str(e)}")
    
    # Generate XML files
    logger.log("Generating XML files...")
    xml_errors = []
    
    # Generate Doh-Div.xml
    logger.log("Generating Doh-Div.xml")
    try:
        from generators import doh_obr
        
        envelope = xml.etree.ElementTree.Element(
            "Envelope", xmlns="http://edavki.durs.si/Documents/Schemas/Doh_Div_3.xsd"
        )
        envelope.set("xmlns:edp", "http://edavki.durs.si/Documents/Schemas/EDP-Common-1.xsd")
        header = xml.etree.ElementTree.SubElement(envelope, "edp:Header")
        taxpayer_elem = xml.etree.ElementTree.SubElement(header, "edp:taxpayer")
        xml.etree.ElementTree.SubElement(taxpayer_elem, "edp:taxNumber").text = taxpayerConfig["taxNumber"]
        xml.etree.ElementTree.SubElement(taxpayer_elem, "edp:taxpayerType").text = taxpayerConfig["taxpayerType"]
        xml.etree.ElementTree.SubElement(taxpayer_elem, "edp:name").text = taxpayerConfig["name"]
        xml.etree.ElementTree.SubElement(taxpayer_elem, "edp:address1").text = taxpayerConfig["address1"]
        xml.etree.ElementTree.SubElement(taxpayer_elem, "edp:city").text = taxpayerConfig["city"]
        xml.etree.ElementTree.SubElement(taxpayer_elem, "edp:postNumber").text = taxpayerConfig["postNumber"]
        xml.etree.ElementTree.SubElement(taxpayer_elem, "edp:postName").text = taxpayerConfig["postName"]
        xml.etree.ElementTree.SubElement(taxpayer_elem, "edp:email").text = taxpayerConfig["email"]
        xml.etree.ElementTree.SubElement(taxpayer_elem, "edp:telephoneNumber").text = taxpayerConfig["telephoneNumber"]
        xml.etree.ElementTree.SubElement(taxpayer_elem, "edp:residentCountry").text = taxpayerConfig["residentCountry"]
        xml.etree.ElementTree.SubElement(taxpayer_elem, "edp:isResident").text = taxpayerConfig["isResident"]
        xml.etree.ElementTree.SubElement(envelope, "edp:AttachmentList")
        xml.etree.ElementTree.SubElement(envelope, "edp:Signatures")
        body = xml.etree.ElementTree.SubElement(envelope, "body")
        xml.etree.ElementTree.SubElement(body, "edp:bodyContent")
        
        if test_mode:
            dYear = str(year + testYearDiff)
        else:
            dYear = str(year)
        
        Doh_Div = xml.etree.ElementTree.SubElement(body, "Doh_Div")
        xml.etree.ElementTree.SubElement(Doh_Div, "Period").text = dYear
        xml.etree.ElementTree.SubElement(Doh_Div, "EmailAddress").text = taxpayerConfig["email"]
        xml.etree.ElementTree.SubElement(Doh_Div, "PhoneNumber").text = taxpayerConfig["telephoneNumber"]
        xml.etree.ElementTree.SubElement(Doh_Div, "ResidentCountry").text = taxpayerConfig["residentCountry"]
        xml.etree.ElementTree.SubElement(Doh_Div, "IsResident").text = taxpayerConfig["isResident"]
        
        for dividend in sorted(dividends, key=lambda k: k["date"]):
            if dividend["amount_eur"] <= 0:
                continue
            
            Dividend = xml.etree.ElementTree.SubElement(body, "Dividend")
            # Parse date - handle both YYYYMMDD and DD/MM/YYYY formats
            date_str = dividend["date"]
            try:
                if len(date_str) == 8 and date_str.isdigit():
                    # Format: YYYYMMDD
                    date_obj = datetime.datetime.strptime(date_str, "%Y%m%d")
                else:
                    # Format: DD/MM/YYYY or DD/MM/YYYY
                    date_obj = datetime.datetime.strptime(date_str, "%d/%m/%Y")
                xml.etree.ElementTree.SubElement(Dividend, "Date").text = date_obj.strftime("%Y-%m-%d")
            except Exception as e:
                # If parsing fails, skip date field
                pass
            
            if dividend.get("taxNumber"):
                xml.etree.ElementTree.SubElement(Dividend, "PayerIdentificationNumber").text = dividend["taxNumber"]
            
            if dividend.get("company_name"):
                xml.etree.ElementTree.SubElement(Dividend, "PayerName").text = dividend["company_name"]
            else:
                xml.etree.ElementTree.SubElement(Dividend, "PayerName").text = dividend.get("symbol", "")
            
            if dividend.get("address"):
                xml.etree.ElementTree.SubElement(Dividend, "PayerAddress").text = dividend["address"]
            
            if dividend.get("country"):
                xml.etree.ElementTree.SubElement(Dividend, "PayerCountry").text = dividend["country"]
            
            xml.etree.ElementTree.SubElement(Dividend, "Type").text = "1"
            xml.etree.ElementTree.SubElement(Dividend, "Value").text = "{0:.2f}".format(
                dividend["amount_eur"]
            )
            xml.etree.ElementTree.SubElement(Dividend, "ForeignTax").text = "{0:.2f}".format(
                dividend["tax_eur"]
            )
            
            if dividend.get("country"):
                xml.etree.ElementTree.SubElement(Dividend, "SourceCountry").text = dividend["country"]
            
            if dividend.get("reliefStatement"):
                xml.etree.ElementTree.SubElement(Dividend, "ReliefStatement").text = dividend["reliefStatement"]
            else:
                xml.etree.ElementTree.SubElement(Dividend, "ReliefStatement").text = ""
        
        xmlString = xml.etree.ElementTree.tostring(envelope)
        prettyXmlString = minidom.parseString(xmlString).toprettyxml(indent="\t")
        
        output_filename = f"Doh-Div_{job_id}.xml" if job_id else "Doh-Div.xml"
        output_path = os.path.join(output_dir, output_filename)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(prettyXmlString)
        
        logger.log(f"Doh-Div.xml generated: {output_path}")
    except Exception as e:
        logger.log(f"Error generating Doh-Div.xml: {str(e)}")
        xml_errors.append(f"Doh-Div.xml: {str(e)}")
    
    # Generate Doh-Obr.xml using the generator
    logger.log("Generating Doh-Obr.xml")
    try:
        output_filename = f"Doh-Obr_{job_id}.xml" if job_id else "Doh-Obr.xml"
        doh_obr.generate(
            taxpayerConfig,
            degiroEntities,
            degiroCashTransactionsList,
            rates,
            year,
            test_mode,
            testYearDiff,
            output_dir,
            output_filename
        )
        logger.log(f"Doh-Obr.xml generated: {os.path.join(output_dir, output_filename)}")
    except Exception as e:
        logger.log(f"Error generating Doh-Obr.xml: {str(e)}")
    
    # Generate placeholder Doh-KDVP.xml
    logger.log("Generating Doh-KDVP.xml (placeholder)")
    try:
        envelope = xml.etree.ElementTree.Element(
            "Envelope", xmlns="http://edavki.durs.si/Documents/Schemas/Doh_KDVP_9.xsd"
        )
        envelope.set("xmlns:edp", "http://edavki.durs.si/Documents/Schemas/EDP-Common-1.xsd")
        header = xml.etree.ElementTree.SubElement(envelope, "edp:Header")
        taxpayer_elem = xml.etree.ElementTree.SubElement(header, "edp:taxpayer")
        xml.etree.ElementTree.SubElement(taxpayer_elem, "edp:taxNumber").text = taxpayerConfig["taxNumber"]
        xml.etree.ElementTree.SubElement(taxpayer_elem, "edp:taxpayerType").text = taxpayerConfig["taxpayerType"]
        xml.etree.ElementTree.SubElement(taxpayer_elem, "edp:name").text = taxpayerConfig["name"]
        xml.etree.ElementTree.SubElement(taxpayer_elem, "edp:address1").text = taxpayerConfig["address1"]
        xml.etree.ElementTree.SubElement(taxpayer_elem, "edp:city").text = taxpayerConfig["city"]
        xml.etree.ElementTree.SubElement(taxpayer_elem, "edp:postNumber").text = taxpayerConfig["postNumber"]
        xml.etree.ElementTree.SubElement(taxpayer_elem, "edp:postName").text = taxpayerConfig["postName"]
        xml.etree.ElementTree.SubElement(envelope, "edp:AttachmentList")
        xml.etree.ElementTree.SubElement(envelope, "edp:Signatures")
        body = xml.etree.ElementTree.SubElement(envelope, "body")
        xml.etree.ElementTree.SubElement(body, "edp:bodyContent")
        
        if test_mode:
            dYear = str(year + testYearDiff)
        else:
            dYear = str(year)
        
        KDVP = xml.etree.ElementTree.SubElement(body, "KDVP")
        
        if test_mode:
            xml.etree.ElementTree.SubElement(KDVP, "DocumentWorkflowID").text = "I"
        else:
            xml.etree.ElementTree.SubElement(KDVP, "DocumentWorkflowID").text = "O"
        
        xml.etree.ElementTree.SubElement(KDVP, "Year").text = dYear
        
        statementStartDate = dYear + "-01-01"
        statementEndDate = dYear + "-12-31"
        
        xml.etree.ElementTree.SubElement(KDVP, "PeriodStart").text = statementStartDate
        xml.etree.ElementTree.SubElement(KDVP, "PeriodEnd").text = statementEndDate
        xml.etree.ElementTree.SubElement(KDVP, "IsResident").text = "true"
        xml.etree.ElementTree.SubElement(KDVP, "TelephoneNumber").text = taxpayerConfig["telephoneNumber"]
        
        xml.etree.ElementTree.SubElement(KDVP, "SecurityCount").text = "0"
        xml.etree.ElementTree.SubElement(KDVP, "SecurityShortCount").text = "0"
        xml.etree.ElementTree.SubElement(KDVP, "SecurityWithContractCount").text = "0"
        xml.etree.ElementTree.SubElement(KDVP, "SecurityWithContractShortCount").text = "0"
        xml.etree.ElementTree.SubElement(KDVP, "ShareCount").text = "0"
        xml.etree.ElementTree.SubElement(KDVP, "Email").text = taxpayerConfig["email"]
        
        xmlString = xml.etree.ElementTree.tostring(envelope)
        prettyXmlString = minidom.parseString(xmlString).toprettyxml(indent="\t")
        
        output_filename = f"Doh-KDVP_{job_id}.xml" if job_id else "Doh-KDVP.xml"
        output_path = os.path.join(output_dir, output_filename)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(prettyXmlString)
        
        logger.log(f"Doh-KDVP.xml generated: {output_path}")
    except Exception as e:
        logger.log(f"Error generating Doh-KDVP.xml: {str(e)}")
    
    # Generate placeholder D-IFI.xml
    logger.log("Generating D-IFI.xml (placeholder)")
    try:
        envelope = xml.etree.ElementTree.Element(
            "Envelope", xmlns="http://edavki.durs.si/Documents/Schemas/D_IFI_4.xsd"
        )
        envelope.set("xmlns:edp", "http://edavki.durs.si/Documents/Schemas/EDP-Common-1.xsd")
        header = xml.etree.ElementTree.SubElement(envelope, "edp:Header")
        taxpayer_elem = xml.etree.ElementTree.SubElement(header, "edp:taxpayer")
        xml.etree.ElementTree.SubElement(taxpayer_elem, "edp:taxNumber").text = taxpayerConfig["taxNumber"]
        xml.etree.ElementTree.SubElement(taxpayer_elem, "edp:taxpayerType").text = taxpayerConfig["taxpayerType"]
        xml.etree.ElementTree.SubElement(taxpayer_elem, "edp:name").text = taxpayerConfig["name"]
        xml.etree.ElementTree.SubElement(taxpayer_elem, "edp:address1").text = taxpayerConfig["address1"]
        xml.etree.ElementTree.SubElement(taxpayer_elem, "edp:city").text = taxpayerConfig["city"]
        xml.etree.ElementTree.SubElement(taxpayer_elem, "edp:postNumber").text = taxpayerConfig["postNumber"]
        xml.etree.ElementTree.SubElement(taxpayer_elem, "edp:postName").text = taxpayerConfig["postName"]
        xml.etree.ElementTree.SubElement(envelope, "edp:AttachmentList")
        xml.etree.ElementTree.SubElement(envelope, "edp:Signatures")
        
        workflow = xml.etree.ElementTree.SubElement(header, "edp:Workflow")
        if test_mode:
            xml.etree.ElementTree.SubElement(workflow, "edp:DocumentWorkflowID").text = "I"
        else:
            xml.etree.ElementTree.SubElement(workflow, "edp:DocumentWorkflowID").text = "O"
        
        xml.etree.ElementTree.SubElement(envelope, "edp:AttachmentList")
        xml.etree.ElementTree.SubElement(envelope, "edp:Signatures")
        body = xml.etree.ElementTree.SubElement(envelope, "body")
        xml.etree.ElementTree.SubElement(body, "edp:bodyContent")
        
        if test_mode:
            dYear = str(year + testYearDiff)
        else:
            dYear = str(year)
        
        statementStartDate = dYear + "-01-01"
        statementEndDate = dYear + "-12-31"
        
        D_IFI = xml.etree.ElementTree.SubElement(body, "D_IFI")
        xml.etree.ElementTree.SubElement(D_IFI, "PeriodStart").text = statementStartDate
        xml.etree.ElementTree.SubElement(D_IFI, "PeriodEnd").text = statementEndDate
        xml.etree.ElementTree.SubElement(D_IFI, "TelephoneNumber").text = taxpayerConfig["telephoneNumber"]
        xml.etree.ElementTree.SubElement(D_IFI, "Email").text = taxpayerConfig["email"]
        
        xmlString = xml.etree.ElementTree.tostring(envelope)
        prettyXmlString = minidom.parseString(xmlString).toprettyxml(indent="\t")
        
        output_filename = f"D-IFI_{job_id}.xml" if job_id else "D-IFI.xml"
        output_path = os.path.join(output_dir, output_filename)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(prettyXmlString)
        
        logger.log(f"D-IFI.xml generated: {output_path}")
    except Exception as e:
        logger.log(f"Error generating D-IFI.xml: {str(e)}")
    
    logger.log("Processing complete!")
    logger.log(f"Generated XML files in: {output_dir}")
    logger.log(f"Summary: {len(dividends)} dividends, {len(interests)} interest, {len(trades)} trades")
    
    return {
        'success': True,
        'logs': logger.get_logs(),
        'trades': trades,
        'dividends': dividends,
        'interests': interests,
        'error': None
    }

if __name__ == "__main__":
    # Test the module independently
    print("DeGiro eDavki Core Module")
    print("This module should be imported and used from the Flask web application.")