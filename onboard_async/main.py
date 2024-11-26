from flask import Flask, jsonify
# from parallel_tasks import ParallelAsyncTasks, TaskConfig
from chain_tasks import ChainedAsyncTasks, TaskConfig, ChainTracker
import logging
import sys
import uuid

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
tracker = ChainTracker()


# @app.route('/run-parallel')
# @ParallelAsyncTasks([
#     TaskConfig(
#         name='task1',
#         status_url='http://localhost:5001/status',
#         success_condition=lambda x: x.get('status') == 'DONE',
#         check_interval=5.0,  # Check every 5 seconds
#         max_retries=15       # 15 retries * 5 seconds = 75 seconds max wait
#     ),
#     TaskConfig(
#         name='task2',
#         status_url='http://localhost:5002/status',
#         success_condition=lambda x: x.get('status') == 'DONE',
#         check_interval=5.0,
#         max_retries=15
#     )
# ], timeout=120)  # 2 minute global timeout
# def run_parallel():
#     logger.info("Initiating parallel task processing")
#     return {'started': True}

chain_tracker = ChainTracker()

@app.route('/run-chain')
@ChainedAsyncTasks([
    TaskConfig(
        name='shared_vpc',
        status_url='http://localhost:5001/status',
        success_condition=lambda x: x.get('status') == 'DONE',
        check_interval=5.0,
        max_retries=15,
        task_type='shared_vpc'
    ),
    TaskConfig(
        name='vpc_sc',
        status_url='http://localhost:5002/status',
        success_condition=lambda x: x.get('status') == 'DONE',
        check_interval=5.0,
        max_retries=15,
        task_type='vpc_sc'
    )
], timeout=300, chain_tracker=chain_tracker)
def run_chain():
    chain_id = str(uuid.uuid4())
    logger.info("Initiating new chain processing", extra={'chain_id': chain_id})
    return {'started': True, 'chain_id': chain_id}

@app.route('/chain-status/<chain_id>')
def check_chain_status(chain_id):
    status = chain_tracker.get_chain_status(chain_id)
    if status:
        return jsonify(status)
    return jsonify({'error': 'Chain not found'}), 404

@app.route('/active-chains')
def list_active_chains():
    return jsonify(chain_tracker.get_active_chains())

@app.route('/health')
def health_check():
    return jsonify({'status': 'healthy'})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, threaded=True)
