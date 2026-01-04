from flask import Flask, render_template, request, flash, redirect, url_for, send_from_directory, jsonify, session, send_file
from werkzeug.utils import secure_filename
from datetime import datetime
import os
import json
import zipfile
import xml.etree.ElementTree as ET
import io
import time
import threading

CONFIG_FILE = 'config.json'

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev-secret-key-change-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///edavki.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['OUTPUT_FOLDER'] = 'outputs'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

from database import db
from models import ProcessingJob, Trade, Dividend, Interest
from degiro_edavki_core import process_csvs

db.init_app(app)

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)

def load_taxpayer_config():
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {
            'taxNumber': '',
            'taxpayerType': 'FO',
            'name': '',
            'address1': '',
            'city': '',
            'postNumber': '',
            'postName': '',
            'email': '',
            'telephoneNumber': '',
            'residentCountry': 'SI',
            'isResident': True
        }
    except Exception as e:
        app.logger.error(f"Error loading config: {e}")
        return {
            'taxNumber': '',
            'taxpayerType': 'FO',
            'name': '',
            'address1': '',
            'city': '',
            'postNumber': '',
            'postName': '',
            'email': '',
            'telephoneNumber': '',
            'residentCountry': 'SI',
            'isResident': True
        }

def save_taxpayer_config(config):
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
    except Exception as e:
        app.logger.error(f"Error saving config: {e}")
        raise

@app.route('/')
def index():
    recent_jobs = ProcessingJob.query.order_by(ProcessingJob.created_at.desc()).limit(5).all()
    current_year = datetime.now().year
    return render_template('index.html', jobs=[job.to_dict() for job in recent_jobs], current_year=current_year)

@app.route('/upload', methods=['POST'])
def upload():
    if 'files' not in request.files:
        return 'No files', 400
    
    files = request.files.getlist('files')
    
    if not files or files[0].filename == '':
        flash('Prosimo, izberite CSV datoteko.', 'danger')
        return redirect(url_for('index'))
    
    saved_files = []
    for file in files:
        if file.filename == '':
            continue
            
        if not file.filename.endswith('.csv'):
            flash('Samo CSV datoteke so dovoljene.', 'danger')
            return redirect(url_for('index'))
        
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
        filename = timestamp + filename
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        saved_files.append(filepath)
    
    session['uploaded_files'] = saved_files
    session['year'] = request.form.get('year', str(datetime.now().year - 1))
    session['test_mode'] = request.form.get('testMode', 'false') == 'true'
    
    flash(f'{len(saved_files)} datotek naloženih.', 'success')
    return redirect(url_for('index'))

@app.route('/process', methods=['POST'])
def process():
    if 'uploaded_files' not in session or not session['uploaded_files']:
        flash('Nobene naložene datoteke. Prosimo, naložite CSV datoteke.', 'warning')
        return redirect(url_for('index'))
    
    try:
        csv_files = session['uploaded_files']
        year = int(session['year'])
        test_mode = session['test_mode']
        
        job = ProcessingJob(
            year=year,
            test_mode=test_mode,
            status='processing',
            csv_files=json.dumps([os.path.basename(f) for f in csv_files])
        )
        db.session.add(job)
        db.session.commit()
        session['job_id'] = job.id
        
        def run_processing():
            with app.app_context():
                try:
                    result = process_csvs(
                        csv_files=csv_files,
                        year=year,
                        test_mode=test_mode,
                        output_dir=app.config['OUTPUT_FOLDER'],
                        db_session=db.session,
                        job_id=job.id
                    )
                    
                    if result.get('success'):
                        job.status = 'completed'
                        job.num_trades = len(result.get('trades', []))
                        job.num_dividends = len(result.get('dividends', []))
                        job.num_interest = len(result.get('interests', []))
                        job.total_dividends_eur = sum(d.get('amount_eur', 0) for d in result.get('dividends', []))
                        job.total_interest_eur = sum(i.get('amount_eur', 0) for i in result.get('interests', []))
                        
                        # Verify XML files were generated
                        import os
                        expected_files = [
                            f'Doh-KDVP_{job.id}.xml',
                            f'D-IFI_{job.id}.xml',
                            f'Doh-Div_{job.id}.xml',
                            f'Doh-Obr_{job.id}.xml'
                        ]
                        missing_files = []
                        for f in expected_files:
                            if not os.path.exists(os.path.join(app.config['OUTPUT_FOLDER'], f)):
                                missing_files.append(f)
                        
                        if missing_files:
                            app.logger.error(f'XML files not generated: {missing_files}')
                            job.error_message = f'XML generation incomplete. Missing: {", ".join(missing_files)}'
                            job.status = 'warning'
                        
                        db.session.commit()
                    else:
                        job.status = 'error'
                        job.error_message = result.get('error', 'Unknown error')
                        db.session.commit()
                    
                except Exception as e:
                    job.status = 'error'
                    job.error_message = f'Processing error: {str(e)}'
                    db.session.commit()
                    app.logger.error(f'Job {job.id} processing failed: {str(e)}', exc_info=True)
        
        thread = threading.Thread(target=run_processing)
        thread.daemon = True
        thread.start()
        
        return redirect(url_for('processing_status'))
        
    except Exception as e:
        flash(f'Napaka pri obdelavi: {str(e)}', 'danger')
        return redirect(url_for('index'))

@app.route('/processing-status')
def processing_status():
    job_id = session.get('job_id')
    if not job_id:
        return redirect(url_for('index'))
    
    job = ProcessingJob.query.get(job_id)
    if not job:
        flash('Opravilo ni najdeno.', 'danger')
        return redirect(url_for('index'))
    
    return render_template('processing.html', job=job)

@app.route('/api/status')
def api_status():
    job_id = session.get('job_id')
    if not job_id:
        return jsonify({'status': 'error', 'error': 'No job found'}), 404
    
    job = ProcessingJob.query.get(job_id)
    if not job:
        return jsonify({'status': 'error', 'error': 'Job not found'}), 404
    
    return jsonify({
        'status': job.status,
        'error': job.error_message,
        'redirect_url': url_for('results', job_id=job.id) if job.status == 'completed' else None
    })

@app.route('/api/job-status/<int:job_id>')
def api_job_status(job_id):
    job = ProcessingJob.query.get(job_id)
    if not job:
        return jsonify({'status': 'error', 'error': 'Job not found'}), 404
    
    return jsonify({
        'status': job.status,
        'error': job.error_message,
        'message': get_status_message(job),
        'progress': 100 if job.status == 'completed' else 50,
        'logs': ['Obdelava v teku...', 'Generiranje XML datotek...']
    })

def get_status_message(job):
    if job.status == 'processing':
        return 'Obdelava datotek...'
    elif job.status == 'completed':
        return 'Obdelava končana!'
    elif job.status == 'error':
        return f'Napaka: {job.error_message or "Neznana napaka"}'
    else:
        return 'V teku...'

@app.route('/results/<int:job_id>')
def results(job_id):
    job = ProcessingJob.query.get(job_id)
    if not job:
        flash('Opravilo ni najdeno.', 'danger')
        return redirect(url_for('index'))
    
    trades = [t.to_dict() for t in job.trades]
    dividends = [d.to_dict() for d in job.dividends]
    interests = [i.to_dict() for i in job.interests]
    
    return render_template('results.html', 
                     job=job.to_dict(),
                     trades=trades,
                     dividends=dividends,
                     interests=interests)

@app.route('/configure')
def configure():
    taxpayer = load_taxpayer_config()
    return render_template('configure.html', taxpayer=taxpayer)

@app.route('/configure', methods=['POST'])
def save_configure():
    try:
        config = {
            'taxNumber': request.form.get('taxNumber'),
            'taxpayerType': request.form.get('taxpayerType', 'FO'),
            'name': request.form.get('name'),
            'address1': request.form.get('address1'),
            'city': request.form.get('city'),
            'postNumber': request.form.get('postNumber'),
            'postName': request.form.get('postName'),
            'email': request.form.get('email'),
            'telephoneNumber': request.form.get('telephoneNumber'),
            'residentCountry': request.form.get('residentCountry', 'SI'),
            'isResident': request.form.get('isResident') == 'on'
        }
        
        save_taxpayer_config(config)
        flash('Konfiguracija shranjena.', 'success')
        return redirect(url_for('index'))
        
    except Exception as e:
        flash(f'Napaka pri shranjevanju: {str(e)}', 'danger')
        return redirect(url_for('configure'))

@app.route('/history')
def history():
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    pagination = ProcessingJob.query.order_by(ProcessingJob.created_at.desc()).\
        paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template('history.html',
                     jobs=[job.to_dict() for job in pagination.items],
                     pagination=pagination)

@app.route('/download/<filename>')
def download_file(filename):
    return send_from_directory(app.config['OUTPUT_FOLDER'], filename)

@app.route('/download-all/<int:job_id>')
def download_all(job_id):
    job = ProcessingJob.query.get(job_id)
    if not job:
        flash('Opravilo ni najdeno.', 'danger')
        return redirect(url_for('index'))
    
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
        xml_files = [
            f'Doh-KDVP_{job.id}.xml',
            f'D-IFI_{job.id}.xml',
            f'Doh-Div_{job.id}.xml',
            f'Doh-Obr_{job.id}.xml'
        ]
        
        for filename in xml_files:
            filepath = os.path.join(app.config['OUTPUT_FOLDER'], filename)
            if os.path.exists(filepath):
                zipf.write(filepath, filename)
    
    memory_file.seek(0)
    return send_file(
        memory_file,
        as_attachment=True,
        download_name=f'edavki_{job.id}.zip',
        mimetype='application/zip'
    )

@app.route('/delete-job/<int:job_id>', methods=['POST'])
def delete_job(job_id):
    job = ProcessingJob.query.get(job_id)
    if not job:
        flash('Opravilo ni najdeno.', 'danger')
        return redirect(url_for('history'))
    
    try:
        db.session.delete(job)
        db.session.commit()
        flash('Opravilo izbrisano.', 'success')
    except Exception as e:
        flash(f'Napaka pri brisanju: {str(e)}', 'danger')
        return redirect(url_for('history'))

@app.template_filter('year')
def year_filter(year):
    return year

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)