import concurrent.futures
import requests
from urllib.parse import urlparse
from typing import List, Dict, Any
from PyQt6.QtCore import QThread, pyqtSignal
import logging

logger = logging.getLogger(__name__)


class URLCheckerWorker(QThread):
    progress = pyqtSignal(int, int, str)
    url_checked = pyqtSignal(int, bool, str)
    finished = pyqtSignal()
    error = pyqtSignal(str)
    
    def __init__(self, urls: List[str], timeout: int = 5):
        super().__init__()
        self.urls = urls
        self.timeout = timeout
        self._stop_requested = False
        self._results = {}
        self._futures = {}
        self._executor = None
    
    def stop(self):
        self._stop_requested = True
        if self._executor:
            self._executor.shutdown(wait=False, cancel_futures=True)
    
    def run(self):
        try:
            total = len(self.urls)
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                self._executor = executor
                futures = {}
                
                for i, url in enumerate(self.urls):
                    if self._stop_requested:
                        break
                    
                    future = executor.submit(self.check_single_url, url, i)
                    futures[future] = i
                    self._futures[i] = future
                
                completed = 0
                for future in concurrent.futures.as_completed(futures.keys()):
                    if self._stop_requested:
                        break
                    
                    try:
                        idx = futures[future]
                        result = future.result(timeout=1)
                        self._results[idx] = result
                        success_bool = result['success'] if result['success'] is not None else False
                        self.url_checked.emit(result['index'], success_bool, result['message'])
                        
                        del self._futures[idx]
                    except concurrent.futures.TimeoutError:
                        continue
                    except Exception as e:
                        idx = futures.get(future, -1)
                        if idx != -1:
                            self._results[idx] = {'index': idx, 'success': False, 'message': f"Ошибка: {str(e)}"}
                            self.url_checked.emit(idx, False, f"Ошибка: {str(e)}")
                    
                    completed += 1
                    progress = int((completed / total) * 100) if total > 0 else 0
                    self.progress.emit(completed, total, f"Проверено: {completed}/{total}")
            
            self.finished.emit()
            
        except Exception as e:
            self.error.emit(f"Ошибка при проверке URL: {str(e)}")
        finally:
            self._executor = None
    
    def check_single_url(self, url: str, index: int) -> Dict[str, Any]:
        if self._stop_requested:
            return {'index': index, 'success': None, 'message': 'Проверка отменена'}
        
        if not url or not url.strip():
            return {'index': index, 'success': False, 'message': 'Пустой URL'}
        
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return {'index': index, 'success': False, 'message': 'Некорректный URL'}
            
            if parsed.scheme in ['http', 'https']:
                try:
                    response = requests.head(
                        url, 
                        timeout=self.timeout,
                        allow_redirects=True,
                        headers={
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                        }
                    )
                    
                    if response.status_code < 400:
                        return {'index': index, 'success': True, 'message': f'HTTP {response.status_code}'}
                    else:
                        return {'index': index, 'success': False, 'message': f'HTTP {response.status_code}'}
                
                except requests.exceptions.Timeout:
                    return {'index': index, 'success': False, 'message': 'Таймаут'}
                except requests.exceptions.ConnectionError:
                    return {'index': index, 'success': False, 'message': 'Ошибка соединения'}
                except requests.exceptions.RequestException as e:
                    return {'index': index, 'success': False, 'message': str(e)}
            
            elif parsed.scheme in ['rtmp', 'rtsp', 'udp', 'tcp', 'rtp']:
                return {'index': index, 'success': None, 'message': 'Потоковый протокол (проверка не поддерживается)'}
            
            else:
                return {'index': index, 'success': False, 'message': f'Неподдерживаемый протокол: {parsed.scheme}'}
                
        except Exception as e:
            return {'index': index, 'success': False, 'message': f'Ошибка: {str(e)}'}
    
    def get_results(self) -> Dict[int, Dict[str, Any]]:
        return self._results