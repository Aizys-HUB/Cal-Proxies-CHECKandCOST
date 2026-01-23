import tkinter as tk
from tkinter import messagebox, filedialog, ttk
import requests, time, os, threading, shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json

# --- Core Logic ---
def get_live_rate():
    try: return requests.get("https://open.er-api.com/v6/latest/USD", timeout=2).json()['rates']['THB']
    except: return 36.50

TARGET_PRESETS = {
    "Google (Standard)": {
        "url": "http://google.com/generate_204",
        "purpose": "stability/latency",
        "method": "GET",
    },
    "HttpBin (Anonymity)": {
        "url": "https://httpbin.org/get",
        "purpose": "connectivity + anonymity check",
        "method": "GET",
    },
    "IP-API (Geolocation)": {
        "url": "http://ip-api.com/json/?fields=status,country,countryCode,city,isp,query",
        "purpose": "connectivity + geo info",
        "method": "GET",
    },
    "Amazon (Target Test)": {
        "url": "https://www.amazon.com/robots.txt",
        "purpose": "anti-bot / blacklist smoke test",
        "method": "GET",
    },
    "Custom URL": {
        "url": "",
        "purpose": "custom",
        "method": "GET",
    },
}

def check_anonymous(proxy_url):
    """ตรวจสอบว่า proxy เป็น anonymous หรือไม่"""
    try:
        with requests.Session() as sess:
            sess.proxies = {"http": proxy_url, "https": proxy_url}
            # ใช้บริการที่ตรวจสอบ headers
            resp = sess.get("http://httpbin.org/headers", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                headers = data.get('headers', {})
                # ตรวจสอบว่ามี X-Forwarded-For, X-Real-Ip, หรือ Via headers หรือไม่
                # ถ้ามี headers เหล่านี้ แสดงว่า proxy ไม่ anonymous
                if 'X-Forwarded-For' in headers or 'X-Real-Ip' in headers or 'Via' in headers:
                    return False, "Transparent"
                return True, "Anonymous"
    except:
        pass
    return None, "Unknown"

def get_geo_info(proxy_url):
    """ตรวจสอบ Geo (ประเทศ) ของ proxy"""
    try:
        with requests.Session() as sess:
            sess.proxies = {"http": proxy_url, "https": proxy_url}
            # ใช้ ip-api.com (free, no API key needed)
            resp = sess.get("http://ip-api.com/json/?fields=status,country,countryCode,city,isp", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('status') == 'success':
                    country = data.get('country', 'Unknown')
                    country_code = data.get('countryCode', '')
                    city = data.get('city', '')
                    isp = data.get('isp', '')
                    return {
                        'country': country,
                        'country_code': country_code,
                        'city': city,
                        'isp': isp
                    }
    except:
        pass
    return {'country': 'Unknown', 'country_code': '', 'city': '', 'isp': ''}

def test_target(sess, target_key, custom_url=""):
    """
    ทดสอบ proxy กับ target ที่เลือก
    return: (ok: bool, status_code: int|None, extra: dict)
    """
    preset = TARGET_PRESETS.get(target_key) or TARGET_PRESETS["Google (Standard)"]
    url = (custom_url or "").strip() if target_key == "Custom URL" else preset.get("url", "")
    if not url:
        return False, None, {"error": "empty_target_url"}

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Accept": "*/*",
        "Connection": "close",
    }
    try:
        resp = sess.get(url, timeout=6, headers=headers, allow_redirects=True)
        extra = {"target_url": url}

        # Google: 204 is ideal, but <400 is fine
        if target_key == "Google (Standard)":
            extra["google_status"] = resp.status_code
            return (resp.status_code < 400), resp.status_code, extra

        # HttpBin: connectivity here; anonymity checked separately via /headers
        if target_key == "HttpBin (Anonymity)":
            extra["httpbin_status"] = resp.status_code
            return (resp.status_code == 200), resp.status_code, extra

        # IP-API: if success, we can extract geo directly from response
        if target_key == "IP-API (Geolocation)":
            extra["ipapi_status"] = resp.status_code
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    if data.get("status") == "success":
                        extra.update({
                            "country": data.get("country", "Unknown"),
                            "country_code": data.get("countryCode", ""),
                            "city": data.get("city", ""),
                            "isp": data.get("isp", ""),
                            "exit_ip": data.get("query", ""),
                        })
                        return True, resp.status_code, extra
                except:
                    pass
            return False, resp.status_code, extra

        # Amazon: very rough anti-bot smoke test (robots.txt is lightweight)
        if target_key == "Amazon (Target Test)":
            extra["amazon_status"] = resp.status_code
            body = (resp.text or "")[:5000].lower()
            is_captcha = ("captcha" in body) or ("robot check" in body) or ("enter the characters you see" in body)
            is_block = resp.status_code in (403, 429, 503) or is_captcha
            extra["amazon_blocked"] = bool(is_block)
            extra["amazon_signal"] = "captcha" if is_captcha else ("status_block" if resp.status_code in (403, 429, 503) else "ok")
            return (not is_block and resp.status_code < 400), resp.status_code, extra

        # Custom URL: consider <400 ok
        extra["custom_status"] = resp.status_code
        return (resp.status_code < 400), resp.status_code, extra
    except Exception as e:
        return False, None, {"target_url": url, "error": str(e)}

def parse_proxy(r):
    r = r.strip()
    if not r: return None
    if r.count(':') >= 4 and "://" in r:
        proto, rest = r.split("://", 1)
        p = rest.split(':')
        return f"{proto}://{p[2]}:{p[3]}@{p[0]}:{p[1]}"
    return r if "://" in r else f"http://{r}"

class HydraFinal:
    def __init__(self, root):
        self.root = root
        self.root.title("HYDRA PROXIES")
        self.root.configure(bg="#0A0A0A")
        
        self.is_running = False
        self.is_paused = False
        self.stop_requested = False
        self.pause_event = threading.Event()
        self.pause_event.set() 
        
        self.alive_list = []
        self.dead_count = 0
        self.total_count = 0
        
        self.setup_ui()
        self.toggle_input()

    def setup_ui(self):
        tk.Label(self.root, text="HYDRA Proxy Checks", font=("Courier", 16, "bold"), bg="#0A0A0A", fg="#00FF00").pack(pady=10)

        example_frame = tk.Frame(self.root, bg="#111", padx=10, pady=5)
        example_frame.pack(fill="x", padx=40, pady=5)
        tk.Label(example_frame, text="Example Format", font=("Tahoma", 10, "bold"), bg="#111", fg="#AAA", anchor="w").pack(fill="x")
        example_text = "socks5://1.1.1.1:20001\nsocks4://1.1.1.1:46527\nhttp://1.1.1.1:443:user:pass\nhttp://1.1.1.1:80"
        tk.Label(example_frame, text=example_text, font=("Consolas", 8), bg="#111", fg="#777", justify="left").pack(anchor="w")

        # --- Target Selection ---
        target_frame = tk.Frame(self.root, bg="#0A0A0A")
        target_frame.pack(fill="x", padx=40, pady=8)
        tk.Label(target_frame, text="TARGET URL", bg="#0A0A0A", fg="#00FF00", font=("Courier", 9, "bold")).pack(anchor="w")

        row = tk.Frame(target_frame, bg="#0A0A0A")
        row.pack(fill="x")
        self.target_var = tk.StringVar(value="Google (Standard)")
        self.target_combo = ttk.Combobox(row, textvariable=self.target_var, state="readonly",
                                         values=list(TARGET_PRESETS.keys()))
        self.target_combo.pack(side="left", fill="x", expand=True)

        self.custom_target_var = tk.StringVar(value="")
        self.entry_custom_target = tk.Entry(row, textvariable=self.custom_target_var, font=("Courier", 10),
                                            bg="#1A1A1A", fg="white", borderwidth=0)
        self.entry_custom_target.pack(side="left", padx=8, fill="x", expand=True)

        def _on_target_change(_evt=None):
            # Show custom entry only when needed
            is_custom = (self.target_var.get() == "Custom URL")
            self.entry_custom_target.configure(state=("normal" if is_custom else "disabled"))
            if not is_custom:
                self.custom_target_var.set("")

        self.target_combo.bind("<<ComboboxSelected>>", _on_target_change)
        _on_target_change()

        self.mode = tk.IntVar(value=1)
        self.f_mode = tk.Frame(self.root, bg="#0A0A0A"); self.f_mode.pack(pady=5)
        self.rb_manual = tk.Radiobutton(self.f_mode, text="Manual IP", variable=self.mode, value=1, command=self.toggle_input, bg="#0A0A0A", fg="white", selectcolor="#333")
        self.rb_manual.pack(side="left", padx=10)
        self.rb_file = tk.Radiobutton(self.f_mode, text="From File", variable=self.mode, value=2, command=self.toggle_input, bg="#0A0A0A", fg="white", selectcolor="#333")
        self.rb_file.pack(side="left", padx=10)

        self.manual_container = tk.Frame(self.root, bg="#0A0A0A")
        tk.Label(self.manual_container, text="▼ INSERT PROXY URL HERE ▼", font=("Tahoma", 8, "bold"), bg="#0A0A0A", fg="#00FF00").pack()
        self.entry_manual = tk.Entry(self.manual_container, justify='center', font=("Courier", 11), bg="#1A1A1A", fg="#00FF00", borderwidth=0)
        self.entry_manual.pack(fill="x", pady=2)
        self.btn_upload = tk.Button(self.root, text="[ UPLOAD TXT FILE ]", command=self.upload_file, bg="#444", fg="white")
        
        log_frame = tk.Frame(self.root, bg="#0A0A0A")
        log_frame.pack(pady=5, fill="both", expand=True, padx=20)

        f_alive = tk.Frame(log_frame, bg="#0A0A0A")
        f_alive.pack(side="left", fill="both", expand=True, padx=5)
        self.lbl_alive_count = tk.Label(f_alive, text="ALIVE: 0", bg="#0A0A0A", fg="#00FF00", font=("Courier", 12, "bold"))
        self.lbl_alive_count.pack()
        self.alive_box = tk.Text(f_alive, height=10, width=60, bg="#050505", fg="#00FF00", font=("Consolas", 8), borderwidth=1, relief="flat")
        self.alive_box.pack(fill="both", expand=True)
        tk.Button(f_alive, text="💾 SAVE & LOG RESULT", command=self.save_alive_to_file, bg="#004400", fg="white", font=("Tahoma", 8, "bold")).pack(fill="x", pady=2)

        f_dead = tk.Frame(log_frame, bg="#0A0A0A")
        f_dead.pack(side="right", fill="both", expand=True, padx=5)
        self.lbl_dead_count = tk.Label(f_dead, text="DEAD: 0", bg="#0A0A0A", fg="#FF3333", font=("Courier", 12, "bold"))
        self.lbl_dead_count.pack()
        self.dead_box = tk.Text(f_dead, height=10, width=30, bg="#050505", fg="#666", font=("Consolas", 8), borderwidth=1, relief="flat")
        self.dead_box.pack(fill="both", expand=True)

        self.ctrl_frame = tk.Frame(self.root, bg="#0A0A0A"); self.ctrl_frame.pack(pady=5)
        self.btn_check = tk.Button(self.ctrl_frame, text="[ START ]", command=self.start_check, bg="#005555", fg="white", width=12)
        self.btn_check.pack(side="left", padx=5)
        self.btn_pause = tk.Button(self.ctrl_frame, text="PAUSE", command=self.toggle_pause, bg="#444", fg="white", width=8, state="disabled")
        self.btn_pause.pack(side="left", padx=5)
        self.btn_stop = tk.Button(self.ctrl_frame, text="STOP", command=self.stop_check, bg="#880000", fg="white", width=8, state="disabled")
        self.btn_stop.pack(side="left", padx=5)

        self.prog_container = tk.Frame(self.root, bg="#0A0A0A")
        self.progress = ttk.Progressbar(self.prog_container, orient="horizontal", mode="determinate")
        self.progress.pack(fill="x", padx=50)
        self.lbl_status = tk.Label(self.root, text="Ready", bg="#0A0A0A", fg="#888", font=("Tahoma", 9))
        self.lbl_status.pack()

        self.ins = {}
        fields = [("T", "20", "THREADS"), ("R", "2", "RPC"), ("L", "0.000", "LATENCY"), ("D", "1.0", "DATA GB"), ("P", "5.0", "PRICE $")]
        for k, v, en in fields:
            f = tk.Frame(self.root, bg="#0A0A0A", pady=1); f.pack(fill="x", padx=50)
            tk.Label(f, text=en, bg="#0A0A0A", fg="#00FF00", font=("Courier", 9)).pack(side="left")
            st, bg_c = ('readonly', "#202020") if k == "L" else ('normal', "#1A1A1A")
            e = tk.Entry(f, justify='right', font=("Courier", 11), bg=bg_c, fg="white", borderwidth=0, width=15, state=st)
            if k != "L": e.insert(0, v)
            e.pack(side="right"); self.ins[k] = e

        tk.Button(self.root, text="[ EXECUTE CALCULATION ]", command=self.calculate, bg="#00FF00", fg="black", font=("Courier", 12, "bold")).pack(pady=10, fill="x", padx=40)
        self.res_label = tk.Label(self.root, text="RPS: -\nBW: -\nDURATION: -\nCOST: -", bg="#0A0A0A", fg="#00FF00", font=("Courier", 11, "bold"), justify="left")
        self.res_label.pack()
        
        self.root.geometry("1000x950")

    def lock_ui(self, locked=True):
        state = "disabled" if locked else "normal"
        self.rb_manual.config(state=state); self.rb_file.config(state=state)
        self.entry_manual.config(state=state); self.btn_upload.config(state=state)
        self.btn_check.config(state=state)
        self.target_combo.config(state=("disabled" if locked else "readonly"))
        if self.target_var.get() == "Custom URL":
            self.entry_custom_target.config(state=("disabled" if locked else "normal"))
        else:
            self.entry_custom_target.config(state="disabled")
        for k in self.ins:
            if k != "L": self.ins[k].config(state=state)

    def toggle_pause(self):
        if not self.is_paused:
            self.is_paused = True; self.pause_event.clear()
            self.btn_pause.config(text="RESUME", bg="#005500")
            self.lbl_status.config(text="PAUSED", fg="orange")
            self.lock_ui(False); self.btn_check.config(state="disabled")
        else:
            self.is_paused = False; self.pause_event.set()
            self.btn_pause.config(text="PAUSE", bg="#444"); self.lock_ui(True)

    def stop_check(self):
        if messagebox.askyesno("STOP", "ยกเลิกงานที่เหลือทั้งหมดใช่หรือไม่?"):
            self.stop_requested = True; self.pause_event.set()
            self.lbl_status.config(text="STOPPING...", fg="red")
            self.btn_stop.config(state="disabled"); self.btn_pause.config(state="disabled")

    def toggle_input(self):
        if self.mode.get() == 1:
            self.btn_upload.pack_forget()
            self.manual_container.pack(pady=5, fill="x", padx=40, before=self.ctrl_frame)
        else:
            self.manual_container.pack_forget()
            self.btn_upload.pack(pady=5, before=self.ctrl_frame)

    def upload_file(self):
        p = filedialog.askopenfilename(filetypes=[("Text", "*.txt")])
        if p: shutil.copy(p, "proxies.txt"); self.lbl_status.config(text=f"Loaded: {os.path.basename(p)}", fg="#00FF00")

    def save_alive_to_file(self):
        if not self.alive_list and self.dead_count == 0:
            messagebox.showwarning("Warning", "ไม่มีข้อมูลสำหรับบันทึก!")
            return
        f = filedialog.asksaveasfile(mode='w', defaultextension=".txt", filetypes=[("Text files", "*.txt")])
        if f:
            f.write("--- ALIVE PROXIES LIST ---\n")
            f.write(f"{'Proxy':<50} {'Latency':<10} {'Target':<18} {'T-OK':<5} {'T-Status':<8} {'Anonymous':<12} {'Country':<20} {'City':<20} {'ISP':<30} {'ExitIP':<16} {'AMZ':<8}\n")
            f.write("-" * 150 + "\n")
            for item in self.alive_list:
                if len(item) >= 3:
                    p, avg, data = item[0], item[1], item[2]
                    anon_str = "Yes" if data.get('anonymous') else ("No" if data.get('anonymous') is False else "Unknown")
                    country = data.get('country', 'Unknown')
                    city = data.get('city', '')
                    isp = data.get('isp', '')
                    tgt = data.get("target", "")
                    tok = "Y" if data.get("target_ok") is True else ("N" if data.get("target_ok") is False else "")
                    tsc = str(data.get("target_status") or "")
                    exit_ip = data.get("exit_ip", "") or ""
                    amz = ""
                    if data.get("target") == "Amazon (Target Test)":
                        if data.get("amazon_blocked") is True:
                            amz = "BLOCKED"
                        elif data.get("amazon_blocked") is False:
                            amz = "OK"
                    f.write(f"{p:<50} {avg:.3f}s{'':<5} {tgt:<18} {tok:<5} {tsc:<8} {anon_str:<12} {country:<20} {city:<20} {isp:<30} {exit_ip:<16} {amz:<8}\n")
                else:
                    # สำหรับข้อมูลเก่าที่ไม่มี geo info
                    p, avg = item[0], item[1]
                    f.write(f"{p:<50} {avg:.3f}s{'':<5} {'':<18} {'':<5} {'':<8} {'Unknown':<12} {'Unknown':<20} {'':<20} {'':<30} {'':<16} {'':<8}\n")
            f.write("\n" + "="*40 + "\n")
            f.write(f"HYDRA  - SESSION LOG SUMMARY\n")
            f.write(f"DATE: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"STATUS: {'PAUSED' if self.is_paused else ('COMPLETED' if not self.is_running else 'RUNNING')}\n")
            f.write(f"TOTAL CHECKED: {self.total_count}\n")
            f.write(f"ALIVE: {len(self.alive_list)}\n")
            f.write(f"DEAD: {self.dead_count}\n")
            f.write(f"TARGET: {self.target_var.get()}\n")
            if self.target_var.get() == "Custom URL":
                f.write(f"CUSTOM URL: {self.custom_target_var.get().strip()}\n")
            
            # สรุปข้อมูล Geo
            if self.alive_list and len(self.alive_list[0]) >= 3:
                countries = {}
                anonymous_count = 0
                for item in self.alive_list:
                    if len(item) >= 3:
                        data = item[2]
                        country = data.get('country', 'Unknown')
                        countries[country] = countries.get(country, 0) + 1
                        if data.get('anonymous'):
                            anonymous_count += 1
                
                f.write("\n" + "="*40 + "\n")
                f.write("GEO SUMMARY:\n")
                for country, count in sorted(countries.items(), key=lambda x: x[1], reverse=True):
                    f.write(f"  {country}: {count} proxies\n")
                f.write(f"\nAnonymous Proxies: {anonymous_count}/{len(self.alive_list)}\n")
            
            f.write("="*40 + "\n")
            f.close()
            messagebox.showinfo("Success", "บันทึกเรียบร้อยแล้ว!")

    def start_check(self):
        self.is_running = True; self.is_paused = False; self.stop_requested = False
        self.pause_event.set()
        self.btn_pause.config(state="normal", text="PAUSE", bg="#444")
        self.btn_stop.config(state="normal")
        self.alive_list = []; self.dead_count = 0; self.total_count = 0
        self.lbl_alive_count.config(text="ALIVE: 0")
        self.lbl_dead_count.config(text="DEAD: 0")
        self.ins['L'].config(state='normal')
        self.ins['L'].configure(bg="#202020", fg="white") # Reset color
        self.ins['L'].config(state='readonly')
        self.lock_ui(True)
        threading.Thread(target=self.worker, daemon=True).start()

    def worker(self):
        self.prog_container.pack(fill="x", before=self.lbl_status)
        self.alive_box.delete('1.0', tk.END); self.dead_box.delete('1.0', tk.END)
        m = self.mode.get()
        raw = [self.entry_manual.get()] if m==1 else (open("proxies.txt").read().splitlines() if os.path.exists("proxies.txt") else [])
        raw = [r for r in raw if r.strip()]
        if not raw: 
            self.lock_ui(False); self.btn_pause.config(state="disabled")
            self.btn_stop.config(state="disabled"); self.prog_container.pack_forget()
            return
        self.progress["value"] = 0; self.progress["maximum"] = len(raw)
        checked = 0
        target_key = self.target_var.get()
        custom_url = self.custom_target_var.get().strip()
        target_short = {
            "Google (Standard)": "GGL",
            "HttpBin (Anonymity)": "HBN",
            "IP-API (Geolocation)": "GEO",
            "Amazon (Target Test)": "AMZ",
            "Custom URL": "CUS",
        }.get(target_key, "TGT")

        with ThreadPoolExecutor(max_workers=int(self.ins['T'].get())) as exe:
            def check(p):
                nonlocal checked
                if self.stop_requested: return
                self.pause_event.wait()
                if self.stop_requested: return
                u = parse_proxy(p); s = []
                now = datetime.now().strftime("%H:%M:%S")
                try:
                    with requests.Session() as sess:
                        sess.proxies = {"http": u, "https": u}
                        # warm up: nothing, but keep consistent session
                        for _ in range(3):
                            if self.stop_requested: break
                            try:
                                st = time.time()
                                ok, _, _ = test_target(sess, target_key, custom_url=custom_url)
                                if ok:
                                    s.append(time.time()-st)
                            except: break
                except: pass
                checked += 1; self.total_count = checked
                if not self.stop_requested:
                    if len(s)==3:
                        avg = sum(s)/3
                        # ตรวจสอบ anonymous / geo ตาม target ที่เลือก
                        is_anon, anon_type = (None, "Unknown")
                        geo_info = {'country': 'Unknown', 'country_code': '', 'city': '', 'isp': ''}
                        target_info = {}
                        try:
                            with requests.Session() as sess2:
                                sess2.proxies = {"http": u, "https": u}
                                # target-specific enrichment
                                ok2, sc2, extra2 = test_target(sess2, target_key, custom_url=custom_url)
                                target_info = {"target": target_key, "target_ok": ok2, "target_status": sc2}
                                target_info.update(extra2 if isinstance(extra2, dict) else {})

                                if target_key == "HttpBin (Anonymity)":
                                    is_anon, anon_type = check_anonymous(u)
                                elif target_key == "IP-API (Geolocation)":
                                    # prefer parsed data from IP-API call if present; fallback to old function
                                    if extra2 and extra2.get("country") and extra2.get("country") != "Unknown":
                                        geo_info = {
                                            "country": extra2.get("country", "Unknown"),
                                            "country_code": extra2.get("country_code", ""),
                                            "city": extra2.get("city", ""),
                                            "isp": extra2.get("isp", ""),
                                        }
                                    else:
                                        geo_info = get_geo_info(u)
                                elif target_key == "Amazon (Target Test)":
                                    # also keep basic geo for display
                                    geo_info = get_geo_info(u)
                                else:
                                    # default: keep both checks like before (useful overall)
                                    is_anon, anon_type = check_anonymous(u)
                                    geo_info = get_geo_info(u)
                        except:
                            pass

                        country = geo_info.get('country', 'Unknown')
                        country_code = geo_info.get('country_code', '')
                        city = geo_info.get('city', '')
                        
                        # สร้างข้อมูลสำหรับแสดงผล
                        anon_status = "ANON" if is_anon else ("TRANS" if anon_type == "Transparent" else "UNK")
                        country_display = f"{country} ({country_code})" if country_code else country
                        if city:
                            country_display += f" - {city}"
                        
                        # เก็บข้อมูลทั้งหมด
                        proxy_data = {
                            'proxy': p,
                            'latency': avg,
                            'anonymous': is_anon,
                            'anon_type': anon_type,
                            'country': country,
                            'country_code': country_code,
                            'city': city,
                            'isp': geo_info.get('isp', '')
                        }
                        proxy_data.update(target_info)
                        self.alive_list.append((p, avg, proxy_data))
                        
                        # แสดงผลในกล่องข้อความ
                        tgt_badge = target_short
                        if target_key == "Amazon (Target Test)" and isinstance(target_info, dict):
                            if target_info.get("amazon_blocked") is True:
                                tgt_badge = f"{target_short}:BLK"
                            elif target_info.get("target_ok") is True:
                                tgt_badge = f"{target_short}:OK"
                        elif isinstance(target_info, dict) and target_info.get("target_ok") is True:
                            tgt_badge = f"{target_short}:OK"
                        elif isinstance(target_info, dict) and target_info.get("target_ok") is False:
                            tgt_badge = f"{target_short}:NO"

                        display_text = f"[{now}] [{tgt_badge}] [{anon_status}] {country_display} | {avg:.3f}s\n  {p}\n"
                        self.alive_box.insert(tk.END, display_text)
                        self.lbl_alive_count.config(text=f"ALIVE: {len(self.alive_list)}")
                    else:
                        self.dead_count += 1
                        self.dead_box.insert(tk.END, f"[{now}] [DEAD] {p}\n")
                        self.lbl_dead_count.config(text=f"DEAD: {self.dead_count}")
                    self.alive_box.see(tk.END); self.dead_box.see(tk.END)
                    self.progress["value"] = checked
                    self.lbl_status.config(text=f"Checking ({target_short}): {checked}/{len(raw)}")
            list(exe.map(check, raw))

        self.prog_container.pack_forget(); self.is_running = False
        self.lock_ui(False); self.btn_pause.config(state="disabled"); self.btn_stop.config(state="disabled")
        if self.alive_list and not self.stop_requested:
            self.alive_list.sort(key=lambda x: x[1])
            self.ins['L'].config(state='normal')
            self.ins['L'].delete(0, tk.END); self.ins['L'].insert(0, f"{self.alive_list[0][1]:.3f}")
            # เปลี่ยนเป็นสีเขียวและตัวหนาให้อ่านง่าย
            self.ins['L'].configure(bg="#004400", fg="#00FF00") 
            self.ins['L'].config(state='readonly')
            self.calculate()
            
            # แสดงสรุปข้อมูล Geo
            if len(self.alive_list) > 0 and len(self.alive_list[0]) >= 3:
                countries = {}
                anonymous_count = 0
                for item in self.alive_list:
                    if len(item) >= 3:
                        data = item[2]
                        country = data.get('country', 'Unknown')
                        countries[country] = countries.get(country, 0) + 1
                        if data.get('anonymous'):
                            anonymous_count += 1
                top_countries = ", ".join([f"{k}({v})" for k, v in sorted(countries.items(), key=lambda x: x[1], reverse=True)[:3]])
                self.lbl_status.config(text=f"DONE: {len(self.alive_list)} ALIVE | ANON: {anonymous_count} | Top: {top_countries}", fg="#00FF00")
            else:
                self.lbl_status.config(text=f"DONE: {len(self.alive_list)} ALIVE", fg="#00FF00")
        else:
            self.lbl_status.config(text="STOPPED" if self.stop_requested else "FAILED", fg="orange")

    def calculate(self):
        try:
            t, r, l, d, p = [float(self.ins[k].get()) for k in 'TRLDP']
            rate = get_live_rate()
            
            # --- Logic คำนวณความเร็ว ---
            rps = ((t * r) / l) * 0.8 if l > 0 else 0
            mb_s = (rps * 5) / 1024 # ยิงเฉลี่ยครั้งละ 5KB
            
            # --- Logic คำนวณระยะเวลา (Duration) ---
            total_seconds = (d * 1024) / mb_s if mb_s > 0 else 0
            if total_seconds > 3600: dur = f"{total_seconds/3600:.2f} Hours"
            elif total_seconds > 60: dur = f"{total_seconds/60:.2f} Mins"
            else: dur = f"{total_seconds:.2f} Secs"
            
            # --- ข้อแนะนำเพิ่มเติม: จำนวน Proxy ที่แนะนำ (ไม่ให้ IP ร้อนเกินไป) ---
            # คำนวณจาก RPS / 2 (สมมติ 1 proxy รับได้ 2 request/sec เพื่อความปลอดภัย)
            suggest_proxies = max(1, int(rps / 2))

            self.res_label.config(text=(
                f"ESTIMATED RPS: {rps:,.0f}\n"
                f"BW: {mb_s*8:.2f} Mbps\n"
                f"DURATION: {dur}\n"
                f"SUGGEST PROXIES: {suggest_proxies} IPs\n"
                f"COST: ฿{d*p*rate:,.2f}"
            ))
        except: pass

if __name__ == "__main__":
    root = tk.Tk(); HydraFinal(root); root.mainloop()