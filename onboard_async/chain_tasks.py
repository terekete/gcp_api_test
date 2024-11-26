# app/chained_tasks.py
from functools import wraps
import asyncio
import aiohttp
from flask import jsonify
from typing import List, Dict, Any, Callable, Optional
from dataclasses import dataclass
import logging
from datetime import datetime
import threading
from collections import OrderedDict

logger = logging.getLogger(__name__)

@dataclass
class TaskConfig:
    name: str
    status_url: str
    success_condition: Callable[[dict], bool]
    max_retries: int = 5
    check_interval: float = 1.0
    task_type: str = "default"

class ChainTracker:
    def __init__(self):
        self._chains = {}
        self._lock = threading.Lock()

    def start_chain(self, chain_id: str, task_sequence: List[str]) -> None:
        with self._lock:
            self._chains[chain_id] = {
                'status': 'running',
                'start_time': datetime.now().isoformat(),
                'current_task': None,
                'task_sequence': task_sequence,
                'completed_tasks': OrderedDict(),
                'total_tasks': len(task_sequence),
                'last_updated': datetime.now().isoformat()
            }

    def update_task_progress(self, chain_id: str, task_name: str, progress: Dict) -> None:
        with self._lock:
            if chain_id in self._chains:
                self._chains[chain_id]['current_task'] = task_name
                self._chains[chain_id]['current_progress'] = progress
                self._chains[chain_id]['last_updated'] = datetime.now().isoformat()

    def complete_task(self, chain_id: str, task_name: str, result: Dict) -> None:
        with self._lock:
            if chain_id in self._chains:
                self._chains[chain_id]['completed_tasks'][task_name] = {
                    'completion_time': datetime.now().isoformat(),
                    'result': result
                }
                
                # Check if all tasks are completed
                if len(self._chains[chain_id]['completed_tasks']) == self._chains[chain_id]['total_tasks']:
                    self._chains[chain_id]['status'] = 'completed'
                    self._chains[chain_id]['end_time'] = datetime.now().isoformat()
                    logger.info(
                        f"Chain {chain_id} completed successfully. All {self._chains[chain_id]['total_tasks']} tasks finished.",
                        extra={'chain_id': chain_id}
                    )

    def fail_chain(self, chain_id: str, error: str, failed_task: str) -> None:
        with self._lock:
            if chain_id in self._chains:
                self._chains[chain_id].update({
                    'status': 'failed',
                    'error': error,
                    'failed_task': failed_task,
                    'end_time': datetime.now().isoformat()
                })

    def get_chain_status(self, chain_id: str) -> Optional[Dict]:
        with self._lock:
            if chain_id in self._chains:
                chain = self._chains[chain_id]
                completed_count = len(chain['completed_tasks'])
                total_count = chain['total_tasks']
                
                status = {
                    'chain_id': chain_id,
                    'status': chain['status'],
                    'progress': {
                        'completed_tasks': completed_count,
                        'total_tasks': total_count,
                        'percentage': (completed_count / total_count) * 100
                    },
                    'start_time': chain['start_time'],
                    'last_updated': chain['last_updated'],
                    'current_task': chain['current_task'],
                    'task_sequence': chain['task_sequence'],
                    'completed_tasks': list(chain['completed_tasks'].keys())
                }
                
                if 'end_time' in chain:
                    status['end_time'] = chain['end_time']
                if 'error' in chain:
                    status['error'] = chain['error']
                
                return status
            return None

    def get_active_chains(self) -> Dict[str, Dict]:
        """Return all active (running) chains and their current status."""
        with self._lock:
            active_chains = {}
            for chain_id, chain in self._chains.items():
                if chain['status'] == 'running':
                    active_chains[chain_id] = {
                        'current_task': chain['current_task'],
                        'progress': {
                            'completed_tasks': len(chain['completed_tasks']),
                            'total_tasks': chain['total_tasks'],
                            'percentage': (len(chain['completed_tasks']) / chain['total_tasks']) * 100
                        },
                        'start_time': chain['start_time'],
                        'last_updated': chain['last_updated']
                    }
            return active_chains

class ChainedAsyncTasks:
    def __init__(self, tasks: List[TaskConfig], timeout: int = 300, chain_tracker: Optional[ChainTracker] = None):
        self.tasks = tasks
        self.timeout = timeout
        self.chain_tracker = chain_tracker or ChainTracker()

    async def check_status(self, task: TaskConfig, chain_id: str) -> Dict:
        logger.info(
            f"Starting task: {task.name} ({task.task_type})",
            extra={'chain_id': chain_id}
        )
        
        async with aiohttp.ClientSession() as session:
            retry_count = 0
            start_time = asyncio.get_event_loop().time()
            
            while retry_count < task.max_retries:
                try:
                    async with session.get(task.status_url) as response:
                        if response.status == 200:
                            data = await response.json()
                            elapsed_time = asyncio.get_event_loop().time() - start_time
                            progress = data.get('progress', 0)
                            
                            self.chain_tracker.update_task_progress(
                                chain_id,
                                task.name,
                                {
                                    'progress': progress,
                                    'elapsed_time': elapsed_time,
                                    'status': data.get('status')
                                }
                            )
                            
                            if task.success_condition(data):
                                result = {
                                    'name': task.name,
                                    'type': task.type,
                                    'elapsed_time': elapsed_time,
                                    'data': data
                                }
                                self.chain_tracker.complete_task(chain_id, task.name, result)
                                return result
                        
                    retry_count += 1
                    if retry_count < task.max_retries:
                        await asyncio.sleep(task.check_interval)
                except aiohttp.ClientError as e:
                    retry_count += 1
                    if retry_count < task.max_retries:
                        await asyncio.sleep(task.check_interval)
            
            error_msg = f"Task {task.name}: Max retries exceeded"
            self.chain_tracker.fail_chain(chain_id, error_msg, task.name)
            raise Exception(error_msg)

    async def execute_chain(self, chain_id: str) -> List[Dict]:
        results = []
        
        # Execute tasks sequentially
        for task in self.tasks:
            try:
                logger.info(
                    f"Executing task {task.name} in sequence",
                    extra={'chain_id': chain_id}
                )
                result = await self.check_status(task, chain_id)
                results.append(result)
                logger.info(
                    f"Completed task {task.name} successfully",
                    extra={'chain_id': chain_id}
                )
            except Exception as e:
                logger.error(
                    f"Chain failed at task {task.name}: {str(e)}",
                    extra={'chain_id': chain_id}
                )
                raise
        
        return results

    def __call__(self, f: Callable) -> Callable:
        @wraps(f)
        async def decorated_function(*args: Any, **kwargs: Any) -> Dict:
            initial_response = f(*args, **kwargs)
            chain_id = initial_response.get('chain_id')
            
            if not chain_id:
                return jsonify({'error': 'No chain_id provided'})
            
            # Initialize chain with task sequence
            self.chain_tracker.start_chain(
                chain_id,
                [task.name for task in self.tasks]
            )
            
            # Execute chain in background
            async def run_chain():
                try:
                    await asyncio.wait_for(
                        self.execute_chain(chain_id),
                        timeout=self.timeout
                    )
                except asyncio.TimeoutError:
                    self.chain_tracker.fail_chain(
                        chain_id,
                        'Chain execution timeout',
                        self.chain_tracker.get_chain_status(chain_id)['current_task']
                    )
                except Exception as e:
                    self.chain_tracker.fail_chain(
                        chain_id,
                        str(e),
                        self.chain_tracker.get_chain_status(chain_id)['current_task']
                    )

            asyncio.create_task(run_chain())
            
            return jsonify({
                'chain_id': chain_id,
                'message': 'Chain execution started',
                'status_endpoint': f'/chain-status/{chain_id}',
                'task_sequence': [task.name for task in self.tasks]
            })

        return decorated_function