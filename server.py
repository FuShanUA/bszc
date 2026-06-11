import http.server
import socketserver
import webbrowser
import os
import json
import re
import urllib.parse
import zipfile
import xml.etree.ElementTree as ET
import io
import hashlib
import datetime
from difflib import SequenceMatcher
import pypdf

PORT = 8000

PRESETS = [
    {
        "id": "sys_meta",
        "name": "文档元数据一致性审查",
        "description": "比对两份标书的PDF元数据（如作者、创建工具、修改时间等），检测是否使用相同排版环境编译。",
        "category": "系统预置",
        "enabled": True
    },
    {
        "id": "sys_image",
        "name": "图片资源二进制哈希审查",
        "description": "提取PDF中的图片指纹，判定两份标书中是否有完全一致的拓扑插图或架构图文件。",
        "category": "系统预置",
        "enabled": True
    },
    {
        "id": "sys_text",
        "name": "大段落文本相似度审查",
        "description": "基于 15-gram 中文分词滑动比对算法，检测两份标书在定制编写的非标书模板条款中的相似度。",
        "category": "系统预置",
        "enabled": True
    },
    {
        "id": "sys_template",
        "name": "标书模板遗留条款降权审查",
        "description": "智能匹配并过滤通用招标文件模板（如电网 boilerplate 官方用语），对合理雷同项进行自动降权降噪。",
        "category": "系统预置",
        "enabled": True
    },
    {
        "id": "sys_company",
        "name": "交叉公司简称泄露审查",
        "description": "交叉反查我方与对手方标书中的公司简称，判定是否存在“套模板时未删干净”的公司名铁证。",
        "category": "系统预置",
        "enabled": True
    }
]

DB_FILE = "rules_db.json"

def load_rules_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    db = {
        "current_rules": list(PRESETS),
        "versions": [
            {
                "version_id": "v_initial",
                "timestamp": "2026-06-11 12:00:00",
                "description": "系统初始规则版本",
                "rules": list(PRESETS)
            }
        ]
    }
    save_rules_db(db)
    return db

def save_rules_db(db):
    try:
        with open(DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False

def check_with_gemini(new_rule, current_rules, api_key):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    
    prompt = f"""
    分析以下“新规则”与“现有规则列表”，判断新规则是否与现有规则存在“重复”(duplicate, 意思高度一致或极其相似) 或 “冲突”(conflict, 正反含义矛盾或对立)。
    
    现有规则列表：
    {json.dumps(current_rules, ensure_ascii=False, indent=2)}
    
    新规则：
    {json.dumps(new_rule, ensure_ascii=False, indent=2)}
    
    请只返回 JSON 数据，格式如下。如果无冲突和重复，请返回空数组。不要包含 markdown 代码块：
    [
      {{
        "incoming_id": "新规则ID",
        "existing_id": "现有规则ID",
        "existing_name": "现有规则名称",
        "type": "duplicate" 或者是 "conflict",
        "reason": "中文解释发生重复或冲突的具体原因，简短明了"
      }}
    ]
    """
    
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }
    
    req = urllib.request.Request(url, data=json.dumps(body).encode('utf-8'), headers=headers, method='POST')
    with urllib.request.urlopen(req, timeout=8) as response:
        res_data = json.loads(response.read().decode('utf-8'))
        text_response = res_data['candidates'][0]['content']['parts'][0]['text'].strip()
        if text_response.startswith("```json"):
            text_response = text_response[7:]
        if text_response.endswith("```"):
            text_response = text_response[:-3]
        return json.loads(text_response.strip())

def check_duplicate_and_conflict(new_rule, current_rules, api_key=None):
    if api_key:
        try:
            res = check_with_gemini(new_rule, current_rules, api_key)
            if res:
                return res
        except Exception as e:
            print(f"Gemini check failed: {e}")
            
    matches = []
    new_desc = new_rule.get('description', '').strip()
    
    for r in current_rules:
        r_desc = r.get('description', '').strip()
        
        sim = SequenceMatcher(None, new_desc, r_desc).ratio()
        if sim > 0.75:
            matches.append({
                "incoming_id": new_rule.get('id'),
                "existing_id": r.get('id'),
                "existing_name": r.get('name'),
                "type": "duplicate",
                "reason": f"规则内容与现有规则相似度高达 {sim*100:.1f}%"
            })
            continue
            
        topics = ["元数据", "图片", "文本", "相似度", "公司简称", "作者", "修改时间", "哈希", "模板", "格式"]
        matched_topic = None
        for t in topics:
            if t in new_desc and t in r_desc:
                matched_topic = t
                break
                
        if matched_topic:
            neg_words = ["禁止", "不能", "不许", "不可", "不得", "不要", "不一致", "不相同", "免除", "忽略"]
            new_neg = any(w in new_desc for w in neg_words)
            r_neg = any(w in r_desc for w in neg_words)
            if new_neg != r_neg:
                matches.append({
                    "incoming_id": new_rule.get('id'),
                    "existing_id": r.get('id'),
                    "existing_name": r.get('name'),
                    "type": "conflict",
                    "reason": f"针对【{matched_topic}】，此规则与现有规则 '{r.get('name')}' 的正负要求相左"
                })
    return matches

def extract_rules_from_file(filename, file_bytes):
    ext = os.path.splitext(filename)[1].lower()
    text = ""
    if ext in ['.md', '.txt']:
        text = file_bytes.decode('utf-8', errors='ignore')
    elif ext == '.docx':
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as docx:
                xml_content = docx.read('word/document.xml')
                root = ET.fromstring(xml_content)
                texts = []
                for elem in root.iter():
                    if elem.tag.endswith('t'):
                        texts.append(elem.text)
                text = "".join(texts)
        except Exception as e:
            text = f"解析 docx 失败: {str(e)}"
    elif ext == '.pdf':
        try:
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            texts = []
            for page in reader.pages:
                texts.append(page.extract_text() or "")
            text = "".join(texts)
        except Exception as e:
            text = f"解析 pdf 失败: {str(e)}"
            
    parts = re.split(r'\n+|- |\* |\b\d+[\.\、\s]', text)
    rules = []
    for p in parts:
        cleaned = p.strip()
        if len(cleaned) > 8 and not cleaned.startswith('#'):
            rule_id = "rule_" + hashlib.md5(cleaned.encode('utf-8')).hexdigest()[:8]
            name = cleaned[:16] + ("..." if len(cleaned) > 16 else "")
            rules.append({
                "id": rule_id,
                "name": name,
                "description": cleaned,
                "category": "导入规则",
                "enabled": True
            })
    return rules

class CustomHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/api/get_key'):
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            env_key = params.get('env_key', [''])[0]
            
            val = self.load_key(env_key)
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'key': val}).encode('utf-8'))
            return
        elif self.path == '/api/get_rules':
            db = load_rules_db()
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(db).encode('utf-8'))
            return
        return super().do_GET()

    def do_POST(self):
        if self.path == '/api/save_key':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            env_key = data.get('env_key', '')
            new_val = data.get('key', '')
            
            success, err = self.save_key(env_key, new_val)
            
            self.send_response(200 if success else 500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'success': success, 'error': err}).encode('utf-8'))
            return
        elif self.path == '/api/save_rules':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            db = load_rules_db()
            db["current_rules"] = data.get("current_rules", [])
            save_rules_db(db)
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"success": True}).encode('utf-8'))
            return
        elif self.path == '/api/save_rule_version':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            desc = data.get("description", "新规则版本")
            
            db = load_rules_db()
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            version_id = "v_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            
            new_version = {
                "version_id": version_id,
                "timestamp": timestamp,
                "description": desc,
                "rules": list(db["current_rules"])
            }
            db["versions"].append(new_version)
            save_rules_db(db)
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "version": new_version}).encode('utf-8'))
            return
        elif self.path == '/api/load_rule_version':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            version_id = data.get("version_id")
            
            db = load_rules_db()
            found = False
            for v in db["versions"]:
                if v["version_id"] == version_id:
                    db["current_rules"] = list(v["rules"])
                    found = True
                    break
                    
            if found:
                save_rules_db(db)
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"success": True}).encode('utf-8'))
            else:
                self.send_response(404)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "error": "Version not found"}).encode('utf-8'))
            return
        elif self.path == '/api/import_rules':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            filename = data.get("filename", "")
            content_base64 = data.get("content", "")
            text_input = data.get("text", "")
            
            rules_to_check = []
            if content_base64:
                import base64
                file_bytes = base64.b64decode(content_base64)
                rules_to_check = extract_rules_from_file(filename, file_bytes)
            elif text_input:
                rule_id = "rule_" + hashlib.md5(text_input.encode('utf-8')).hexdigest()[:8]
                name = text_input[:16] + ("..." if len(text_input) > 16 else "")
                rules_to_check = [{
                    "id": rule_id,
                    "name": name,
                    "description": text_input,
                    "category": "导入规则",
                    "enabled": True
                }]
                
            db = load_rules_db()
            current_rules = db["current_rules"]
            
            api_key = self.load_key("GEMINI_API_KEY")
            
            results = []
            for nr in rules_to_check:
                conflicts = check_duplicate_and_conflict(nr, current_rules, api_key)
                if conflicts:
                    nr["conflict_or_duplicate"] = conflicts[0]
                results.append(nr)
                
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "rules": results}).encode('utf-8'))
            return
        elif self.path == '/api/resolve_imported_rules':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            resolutions = data.get("resolutions", [])
            
            db = load_rules_db()
            current_rules = db["current_rules"]
            
            for item in resolutions:
                rule = item.get("rule")
                action = item.get("action")
                
                if not rule:
                    continue
                    
                if action == "ignore":
                    continue
                elif action == "overwrite":
                    conflict_info = rule.get("conflict_or_duplicate")
                    if conflict_info:
                        exist_id = conflict_info.get("existing_id")
                        current_rules = [r for r in current_rules if r.get("id") != exist_id]
                    if "conflict_or_duplicate" in rule:
                        del rule["conflict_or_duplicate"]
                    current_rules.append(rule)
                else:
                    if "conflict_or_duplicate" in rule:
                        del rule["conflict_or_duplicate"]
                    current_rules.append(rule)
                    
            db["current_rules"] = current_rules
            save_rules_db(db)
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"success": True}).encode('utf-8'))
            return

    def load_key(self, env_key):
        if not env_key:
            return ""
        
        # 1. Try reading from project .env
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        if os.path.exists(env_path):
            try:
                with open(env_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                match = re.search(rf'^{env_key}=(.*)', content, re.M)
                if match:
                    val = match.group(1).strip().strip("'").strip('"')
                    if val: return val
            except:
                pass

        # 2. Fallback to ~/.baoyu-skills/.env
        backup_env = os.path.expanduser("~/.baoyu-skills/.env")
        if os.path.exists(backup_env):
            try:
                with open(backup_env, 'r', encoding='utf-8') as f:
                    content = f.read()
                match = re.search(rf'^{env_key}=(.*)', content, re.M)
                if match:
                    val = match.group(1).strip().strip("'").strip('"')
                    if val: return val
            except:
                pass

        return os.environ.get(env_key, "")

    def save_key(self, env_key, new_val):
        if not env_key:
            return False, "Invalid env key"
        
        # Save to ~/.baoyu-skills/.env to sync with unified config
        env_path = os.path.expanduser("~/.baoyu-skills/.env")
        try:
            content = ""
            if os.path.exists(env_path):
                with open(env_path, 'r', encoding='utf-8') as f:
                    content = f.read()

            def set_env_val(key, val, current):
                regex = re.compile(rf'^{key}=.*', re.M)
                if regex.search(current):
                    return regex.sub(f'{key}={val}', current)
                prefix = "\n" if current and not current.endswith("\n") else ""
                return current + f'{prefix}{key}={val}'

            new_content = set_env_val(env_key, new_val, content)
            
            os.makedirs(os.path.dirname(env_path), exist_ok=True)
            with open(env_path, 'w', encoding='utf-8') as f:
                f.write(new_content.strip() + '\n')
            
            os.environ[env_key] = new_val
            return True, ""
        except Exception as e:
            return False, str(e)

class ReuseAddrTCPServer(socketserver.TCPServer):
    allow_reuse_address = True

print("BidShield UI server starting at http://localhost:8000...")
webbrowser.open("http://localhost:8000")

# Change working directory to the script's directory so it serves the files correctly
os.chdir(os.path.dirname(os.path.abspath(__file__)))

with ReuseAddrTCPServer(("", PORT), CustomHandler) as httpd:
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
