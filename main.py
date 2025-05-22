from flask import Flask, render_template, request, redirect, url_for, jsonify, Response
from flask_mail import Mail, Message
from apscheduler.schedulers.background import BackgroundScheduler
from queue import Queue
import json
import os
import socket
import smtplib
from datetime import datetime, timedelta, timezone

# Inicialización de la aplicación Flask
app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'bD8k#5gT9r@W2z!E7pVxL3mQ6sA1cY4n')

# Configuración mejorada de Flask-Mail
app.config.update(
    MAIL_SERVER='smtp.gmail.com',
    MAIL_PORT=587,
    MAIL_USE_TLS=True,
    MAIL_USERNAME='edwindjll25@gmail.com',
    MAIL_PASSWORD='hxlvlkfmvyintszw',  # Contraseña de aplicación SIN espacios
    MAIL_DEFAULT_SENDER='edwindjll25@gmail.com',
    MAIL_ASCII_ATTACHMENTS=False,  # Permite caracteres no ASCII
    MAIL_TIMEOUT=10,  # Timeout de 10 segundos
    MAIL_DEBUG=True   # Habilita logs detallados
)

mail = Mail(app)

# Archivo de base de datos JSON
DB_FILE = 'tasks_db.json'

# Context Processor para inyectar 'now' en todas las plantillas
@app.context_processor
def inject_now():
    return {'now': datetime.now(timezone.utc)}

# Funciones auxiliares
def load_tasks():
    """Carga las tareas desde el archivo JSON."""
    if not os.path.exists(DB_FILE):
        return {'tasks': [], 'categories': ['Fácil', 'Medio', 'Difícil']}
    
    with open(DB_FILE, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {'tasks': [], 'categories': ['Fácil', 'Medio', 'Difícil']}

def save_tasks(data):
    """Guarda las tareas en el archivo JSON."""
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def send_email_notification(task):
    """Envía un correo electrónico de recordatorio con manejo de errores mejorado."""
    try:
        subject = f"Recordatorio de tarea: {task['title']}"
        body = f"""
        Tarea: {task['title']}
        Categoría: {task['category']}
        Descripción: {task['description']}
        Fecha límite: {task['due_date']}
        Prioridad: {task['priority']}
        
        ¡No olvides completar esta tarea!
        """
        
        msg = Message(
            subject=subject,
            recipients=['edwindjll25@gmail.com'],
            charset='utf-8'
        )
        msg.body = body
        
        # Configuración manual del timeout
        with app.app_context():
            with mail.connect() as connection:
                if connection:
                    connection.timeout = 10  # Timeout de 10 segundos
                    connection.send(msg)
        return True
        
    except smtplib.SMTPException as e:
        print(f"⛔ Error SMTP al enviar email: {str(e)}")
        return False
    except Exception as e:
        print(f"⛔ Error general al enviar email: {str(e)}")
        return False

def check_due_tasks():
    """Verifica tareas próximas a vencer y envía notificaciones."""
    with app.app_context():
        tasks_data = load_tasks()
        now = datetime.now(timezone.utc)
        
        for task in tasks_data['tasks']:
            if not task.get('due_date'):
                continue
                
            due_date = datetime.strptime(task['due_date'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
            if now >= due_date - timedelta(hours=1) and not task.get('notification_sent', False):
                if send_email_notification(task):
                    task['notification_sent'] = True
                    save_tasks(tasks_data)

# Configuración del scheduler para verificar tareas cada hora
scheduler = BackgroundScheduler()
scheduler.add_job(func=check_due_tasks, trigger="interval", minutes=60)
scheduler.start()

# Rutas de la aplicación
@app.route('/')
def index():
    """Página principal con el listado de categorías."""
    tasks_data = load_tasks()
    return render_template('index.html', categories=tasks_data['categories'])

@app.route('/add_task', methods=['GET', 'POST'])
def add_task():
    """Añade una nueva tarea."""
    if request.method == 'POST':
        tasks_data = load_tasks()
        due_date_str = request.form['due_date']
        
        try:
            formatted_date_str = due_date_str.replace(' ', 'T') if ' ' in due_date_str else due_date_str
            due_date = datetime.strptime(formatted_date_str, '%Y-%m-%dT%H:%M').replace(tzinfo=timezone.utc)
            
            new_task = {
                'id': len(tasks_data['tasks']) + 1,
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
            save_tasks(tasks_data)
            notify_clients('new_task', new_task)
            
            if due_date - datetime.now(timezone.utc) <= timedelta(hours=24):
                if send_email_notification(new_task):
                    new_task['notification_sent'] = True
                    save_tasks(tasks_data)
            
            return jsonify({'status': 'success', 'task': new_task})
        
        except ValueError as e:
            return jsonify({'status': 'error', 'message': f'Formato de fecha inválido: {str(e)}'}), 400
    
    tasks_data = load_tasks()
    return render_template('add_task.html', categories=tasks_data['categories'])

@app.route('/get_tasks')
def get_tasks():
    """Devuelve las tareas en formato JSON."""
    tasks_data = load_tasks()
    return jsonify(tasks_data['tasks'])

@app.route('/tasks')
def tasks():
    """Página de visualización de tareas."""
    return render_template('tasks.html')

@app.route('/complete_task/<int:task_id>', methods=['POST'])
def complete_task(task_id):
    """Marca una tarea como completada."""
    tasks_data = load_tasks()
    for task in tasks_data['tasks']:
        if task['id'] == task_id:
            task['completed'] = True
            save_tasks(tasks_data)
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
    """Clase para manejar conexiones SSE."""
    def __init__(self):
        self.queue = Queue()

    def generator(self):
        """Genera eventos para el cliente."""
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
    if scheduler.running:
        scheduler.shutdown()

if __name__ == '__main__':
    app.run(debug=True)