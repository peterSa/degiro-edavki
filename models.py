from datetime import datetime
from database import db

class ProcessingJob(db.Model):
    __tablename__ = 'processing_jobs'
    
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    year = db.Column(db.Integer, nullable=False)
    test_mode = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(50), default='pending')
    csv_files = db.Column(db.Text)  # JSON array of filenames
    error_message = db.Column(db.Text, nullable=True)
    
    # Summary data
    num_trades = db.Column(db.Integer, default=0)
    num_dividends = db.Column(db.Integer, default=0)
    num_interest = db.Column(db.Integer, default=0)
    total_dividends_eur = db.Column(db.Float, default=0.0)
    total_interest_eur = db.Column(db.Float, default=0.0)
    
    # Relationships
    trades = db.relationship('Trade', backref='job', lazy=True, cascade='all, delete-orphan')
    dividends = db.relationship('Dividend', backref='job', lazy=True, cascade='all, delete-orphan')
    interests = db.relationship('Interest', backref='job', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'created_at': self.created_at.strftime('%d/%m/%Y %H:%M'),
            'year': self.year,
            'test_mode': self.test_mode,
            'status': self.status,
            'csv_files': self.csv_files,
            'error_message': self.error_message,
            'num_trades': self.num_trades,
            'num_dividends': self.num_dividends,
            'num_interest': self.num_interest,
            'total_dividends_eur': self.total_dividends_eur,
            'total_interest_eur': self.total_interest_eur
        }

class Trade(db.Model):
    __tablename__ = 'trades'
    
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('processing_jobs.id'), nullable=False)
    date = db.Column(db.String(20), nullable=False)
    symbol = db.Column(db.String(50))
    isin = db.Column(db.String(20))
    description = db.Column(db.Text)
    asset_type = db.Column(db.String(20))  # normal, derivate
    position_type = db.Column(db.String(10))  # long, short
    quantity = db.Column(db.Float)
    price = db.Column(db.Float)
    price_eur = db.Column(db.Float)
    currency = db.Column(db.String(10))
    action = db.Column(db.String(10))  # Buy, Sell
    
    def to_dict(self):
        return {
            'id': self.id,
            'date': self.date,
            'symbol': self.symbol,
            'isin': self.isin,
            'description': self.description,
            'asset_type': self.asset_type,
            'position_type': self.position_type,
            'quantity': self.quantity,
            'price': self.price,
            'price_eur': self.price_eur,
            'currency': self.currency,
            'action': self.action
        }

class Dividend(db.Model):
    __tablename__ = 'dividends'
    
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('processing_jobs.id'), nullable=False)
    date = db.Column(db.String(20), nullable=False)
    company_name = db.Column(db.String(200))
    symbol = db.Column(db.String(50))
    amount = db.Column(db.Float)
    amount_eur = db.Column(db.Float)
    tax = db.Column(db.Float)
    tax_eur = db.Column(db.Float)
    currency = db.Column(db.String(10))
    isin = db.Column(db.String(20))
    
    def to_dict(self):
        return {
            'id': self.id,
            'date': self.date,
            'company_name': self.company_name,
            'symbol': self.symbol,
            'amount': self.amount,
            'amount_eur': self.amount_eur,
            'tax': self.tax,
            'tax_eur': self.tax_eur,
            'currency': self.currency,
            'isin': self.isin
        }

class Interest(db.Model):
    __tablename__ = 'interest'
    
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('processing_jobs.id'), nullable=False)
    date = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Float)
    amount_eur = db.Column(db.Float)
    currency = db.Column(db.String(10))
    description = db.Column(db.Text)
    
    def to_dict(self):
        return {
            'id': self.id,
            'date': self.date,
            'amount': self.amount,
            'amount_eur': self.amount_eur,
            'currency': self.currency,
            'description': self.description
        }