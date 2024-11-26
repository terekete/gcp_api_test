# # app/task_service.py
# import time
# import argparse
# from flask import Flask, jsonify
# import logging
# import sys
# import random

# # Configure logging
# logging.basicConfig(
#     level=logging.INFO,
#     format='%(asctime)s [%(levelname)s] %(message)s',
#     handlers=[
#         logging.StreamHandler(sys.stdout)
#     ]
# )
# logger = logging.getLogger(__name__)

# app = Flask(__name__)

# class TaskState:
#     def __init__(self, task_id):
#         self.task_id = task_id
#         self.start_time = time.time()
#         self.duration = 60  # 1 minute duration
#         # Add some random variation to make tasks complete at different times
#         self.duration += random.uniform(-5, 5)
#         logger.info(f"Task {task_id} initialized with duration: {self.duration:.2f} seconds")

#     def get_progress(self):
#         elapsed = time.time() - self.start_time
#         progress = min(100, (elapsed / self.duration) * 100)
#         return progress

#     def is_complete(self):
#         return self.get_progress() >= 100

# @app.route('/status')
# def status():
#     progress = task_state.get_progress()
#     status_data = {
#         'status': 'DONE' if task_state.is_complete() else 'RUNNING',
#         'task_id': task_state.task_id,
#         'progress': round(progress, 2),
#         'elapsed_time': round(time.time() - task_state.start_time, 2)
#     }
    
#     logger.info(f"Task {task_state.task_id} - Progress: {status_data['progress']}% - "
#                 f"Status: {status_data['status']} - "
#                 f"Elapsed: {status_data['elapsed_time']}s")
    
#     return jsonify(status_data)

# if __name__ == '__main__':
#     parser = argparse.ArgumentParser()
#     parser.add_argument('--port', type=int, required=True)
#     parser.add_argument('--task-id', type=int, required=True)
#     args = parser.parse_args()

#     logger.info(f"Starting task service {args.task_id} on port {args.port}")
#     task_state = TaskState(args.task_id)
#     app.run(host='0.0.0.0', port=args.port)


import time
import argparse
from flask import Flask, jsonify
import logging
import sys
import random

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

class TaskState:
    def __init__(self, task_id, task_type):
        self.task_id = task_id
        self.task_type = task_type
        self.start_time = None
        self.duration = self._get_duration_for_type()
        self.is_started = False
        logger.info(f"Task {task_id} ({task_type}) initialized with duration: {self.duration:.2f} seconds")

    def _get_duration_for_type(self):
        # Different durations for different task types
        base_durations = {
            'preprocessing': 30,
            'model_training': 60,
            'evaluation': 45
        }
        base = base_durations.get(self.task_type, 60)
        # Add some random variation
        return base + random.uniform(-5, 5)

    def start(self):
        if not self.is_started:
            self.start_time = time.time()
            self.is_started = True
            logger.info(f"Task {self.task_id} ({self.task_type}) started")

    def get_progress(self):
        if not self.is_started:
            self.start()
            
        elapsed = time.time() - self.start_time
        progress = min(100, (elapsed / self.duration) * 100)
        return progress

    def is_complete(self):
        return self.get_progress() >= 100

@app.route('/status')
def status():
    progress = task_state.get_progress()
    status_data = {
        'status': 'DONE' if task_state.is_complete() else 'RUNNING',
        'task_id': task_state.task_id,
        'task_type': task_state.task_type,
        'progress': round(progress, 2),
        'elapsed_time': round(time.time() - task_state.start_time, 2) if task_state.start_time else 0
    }
    
    logger.info(f"Task {task_state.task_id} ({task_state.task_type}) - "
                f"Progress: {status_data['progress']}% - "
                f"Status: {status_data['status']} - "
                f"Elapsed: {status_data['elapsed_time']}s")
    
    return jsonify(status_data)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--task-id', type=int, required=True)
    parser.add_argument('--task-type', type=str, required=True)
    args = parser.parse_args()

    logger.info(f"Starting task service {args.task_id} ({args.task_type}) on port {args.port}")
    task_state = TaskState(args.task_id, args.task_type)
    app.run(host='0.0.0.0', port=args.port)
