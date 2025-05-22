// Configuración de EventSource para actualizaciones en tiempo real
document.addEventListener('DOMContentLoaded', function() {
    // Verificar si estamos en la página de tareas
    if (document.getElementById('tasks-list')) {
        const eventSource = new EventSource('/updates');
        
        eventSource.onmessage = function(event) {
            const data = JSON.parse(event.data);
            console.log('Evento recibido:', data);
            
            if (data.type === 'new_task' || data.type === 'task_completed') {
                if (typeof updateTaskList === 'function') {
                    updateTaskList();
                }
            }
        };
        
        eventSource.onerror = function(error) {
            console.error('Error en EventSource:', error);
        };
    }
});

// Función para mostrar notificaciones
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.textContent = message;
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.classList.add('fade-out');
        setTimeout(() => {
            notification.remove();
        }, 500);
    }, 3000);
}

// Función global para actualizar la lista de tareas
window.updateTaskList = function() {
    if (typeof loadTasks === 'function') {
        loadTasks();
    }
};