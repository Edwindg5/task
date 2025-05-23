from flask import Flask, render_template, request, redirect, url_for, jsonify, Response
from flask_mail import Mail, Message
from apscheduler.schedulers.background import BackgroundScheduler
from queue import Queue
import json
import os
import socket
import smtplib
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Inicialización de la aplicación Flask
app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'bD8k#5gT9r@W2z!E7pVxL3mQ6sA1cY4n')

# Configuración para Vercel
app.config['SERVER_NAME'] = os.environ.get('VERCEL_URL', 'localhost:5000')
if 'VERCEL' in os.environ:
    app.config['PREFERRED_URL_SCHEME'] = 'https'

# Configuración de Flask-Mail con variables de entorno
app.config.update(
    MAIL_SERVER=os.environ.get('MAIL_SERVER', 'smtp.gmail.com'),
    MAIL_PORT=int(os.environ.get('MAIL_PORT', 587)),
    MAIL_USE_TLS=os.environ.get('MAIL_USE_TLS', 'True').lower() == 'true',
    MAIL_USERNAME=os.environ.get('MAIL_USERNAME'),
    MAIL_PASSWORD=os.environ.get('MAIL_PASSWORD'),
    MAIL_DEFAULT_SENDER=os.environ.get('MAIL_DEFAULT_SENDER'),
    MAIL_ASCII_ATTACHMENTS=False,
    MAIL_TIMEOUT=10,
    MAIL_DEBUG=True
)

mail = Mail(app)

# Almacenamiento en memoria
tasks_data = {
    'tasks': [],
    'categories': ['Fácil', 'Medio', 'Difícil'],
    'next_id': 1
}

# Context Processor para inyectar 'now' en todas las plantillas
@app.context_processor
def inject_now():
    return {'now': datetime.now(timezone.utc)}

# Funciones auxiliares
def save_tasks():
    """Guarda las tareas en memoria (persistencia solo para desarrollo local)."""
    if 'VERCEL' not in os.environ:
        try:
            with open('tasks_memory.json', 'w', encoding='utf-8') as f:
                json.dump(tasks_data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ No se pudo guardar en archivo: {str(e)}")

def load_tasks():
    """Carga las tareas desde memoria (y desde archivo solo en desarrollo local)."""
    global tasks_data
    if 'VERCEL' not in os.environ and os.path.exists('tasks_memory.json'):
        try:
            with open('tasks_memory.json', 'r', encoding='utf-8') as f:
                saved_data = json.load(f)
                if 'tasks' in saved_data and 'categories' in saved_data:
                    tasks_data = saved_data
                    if tasks_data['tasks']:
                        tasks_data['next_id'] = max(task['id'] for task in tasks_data['tasks']) + 1
                    else:
                        tasks_data['next_id'] = 1
        except Exception as e:
            print(f"⚠️ No se pudo cargar desde archivo: {str(e)}")
    return tasks_data

def send_email_notification(task):
    """Envía un correo electrónico de recordatorio."""
    try:
        msg = Message(
            subject=f"Recordatorio de tarea: {task['title']}",
            recipients=[os.environ.get('MAIL_RECIPIENT', 'edwindjll25@gmail.com')],
            body=f"""
            Tarea: {task['title']}
            Categoría: {task['category']}
            Descripción: {task['description']}
            Fecha límite: {task['due_date']}
            Prioridad: {task['priority']}
            
            ¡No olvides completar esta tarea!
            """,
            charset='utf-8'
        )
        
        with app.app_context():
            with mail.connect() as connection:
                if connection:
                    connection.send(msg)
        return True
    except Exception as e:
        print(f"⛔ Error al enviar email: {str(e)}")
        return False

def check_due_tasks():
    """Verifica tareas próximas a vencer y envía notificaciones."""
    if 'VERCEL' in os.environ:
        return
        
    with app.app_context():
        global tasks_data
        now = datetime.now(timezone.utc)
        
        for task in tasks_data['tasks']:
            if not task.get('due_date'):
                continue
                
            due_date = datetime.strptime(task['due_date'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
            if now >= due_date - timedelta(hours=1) and not task.get('notification_sent', False):
                if send_email_notification(task):
                    task['notification_sent'] = True
                    save_tasks()

# Configuración del scheduler (solo en local)
if 'VERCEL' not in os.environ:
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=check_due_tasks, trigger="interval", minutes=60)
    scheduler.start()

# Cargar tareas al iniciar (solo en local)
if 'VERCEL' not in os.environ:
    load_tasks()

# Rutas de la aplicación
@app.route('/')
def home():
    """Página principal con el listado de categorías."""
    return render_template('index.html', categories=tasks_data['categories'])

@app.route('/add_task', methods=['GET', 'POST'])
def add_task():
    """Añade una nueva tarea."""
    global tasks_data
    
    if request.method == 'POST':
        try:
            due_date_str = request.form['due_date'].replace(' ', 'T') if ' ' in request.form['due_date'] else request.form['due_date']
            due_date = datetime.strptime(due_date_str, '%Y-%m-%dT%H:%M').replace(tzinfo=timezone.utc)
            
            new_task = {
                'id': tasks_data['next_id'],
                'title': request.form['title'],
                'description': request.form['description'],
                'category': request.form['category'],
                'priority': request.form['priority'],
                'due_date': due_date.strftime('%Y-%m-%d %H:%M:%S'),
                'created_at': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
                'completed': False,
                'notification_sent': False
            }
            
            tasks_data['tasks'].append(new_task)
            tasks_data['next_id'] += 1
            save_tasks()
            notify_clients('new_task', new_task)
            
            if due_date - datetime.now(timezone.utc) <= timedelta(hours=24):
                if send_email_notification(new_task):
                    new_task['notification_sent'] = True
                    save_tasks()
            
            return jsonify({'status': 'success', 'task': new_task})
        except ValueError as e:
            return jsonify({'status': 'error', 'message': f'Formato de fecha inválido: {str(e)}'}), 400
    
    return render_template('add_task.html', categories=tasks_data['categories'])

@app.route('/get_tasks')
def get_tasks():
    """Devuelve las tareas en formato JSON."""
    return jsonify(tasks_data['tasks'])

@app.route('/tasks')
def show_tasks():
    """Página de visualización de tareas."""
    return render_template('tasks.html')

@app.route('/complete_task/<int:task_id>', methods=['POST'])
def complete_task(task_id):
    """Marca una tarea como completada."""
    global tasks_data
    for task in tasks_data['tasks']:
        if task['id'] == task_id:
            task['completed'] = True
            save_tasks()
            notify_clients('task_completed', {'task_id': task_id})
            break
    return jsonify({'status': 'success'})

# Server-Sent Events (SSE) para actualizaciones en tiempo real
clients = []

def notify_clients(event_type, data):
    """Notifica a los clientes sobre cambios en las tareas."""
    for client in clients:
        try:
            client.queue.put({'type': event_type, 'data': data})
        except:
            clients.remove(client)

class Client:
    def __init__(self):
        self.queue = Queue()

    def generator(self):
        try:
            while True:
                message = self.queue.get()
                yield f"data: {json.dumps(message)}\n\n"
        except GeneratorExit:
            clients.remove(self)

@app.route('/updates')
def updates():
    """Endpoint para actualizaciones en tiempo real."""
    client = Client()
    clients.append(client)
    return Response(client.generator(), mimetype='text/event-stream')

@app.teardown_appcontext
def shutdown_scheduler(exception=None):
    """Apaga el scheduler al cerrar la aplicación."""
    if 'scheduler' in globals() and scheduler.running:
        scheduler.shutdown()

# Configuración para Vercel
def create_app():
    return app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
else:
    application = create_app()