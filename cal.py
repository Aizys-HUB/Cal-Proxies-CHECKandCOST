import tkinter as tk
from tkinter import messagebox, filedialog
import random, requests, time, os, threading, shutil
from concurrent.futures import ThreadPoolExecutor

# --- 1-3. Core Logic (Clean & Efficient) ---
def create_input(parent, label_text, default_val):
    tk.Label(parent, text=label_text, bg="#0A0A0A", fg="#888888", font=("Courier", 10)).pack()
    entry = tk.Entry(parent, justify='center', font=("Courier", 12), bg="#1A1A1A", fg="#00FF00", borderwidth=0)
    entry.insert(0, default_val)
    entry.pack(pady=5, ipady=3); return entry

def get_live_exchange_rate():
    try: return requests.get("https://open.er-api.com/v6/latest/USD", timeout=5).json()['rates']['THB']
    except: return 36.50 

def parse_proxy(raw):
    raw = raw.strip()
    if not raw: return None
    p = "http"
    if "://" in raw: p, raw = raw.split("://", 1)
    parts = raw.split(":")
    if len(parts) == 2: return f"{p}://{parts[0]}:{parts[1]}"
    if len(parts) == 4:
        ip, port, u, pw = parts if "." in parts[0] else (parts[2], parts[3], parts[0], parts[1])
        return f"{p}://{u}:{pw}@{ip}:{port}"
    return f"{p}://{raw}"

# --- 4-5. Proxy Management & Parallel Checker ---
def upload_and_save_proxy():
    path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt")])
    if path:
        shutil.copyfile(path, "proxies.txt")
        count = len([l for l in open("proxies.txt") if l.strip()])
        label_latency_status.config(text=f"Uploaded: {count} proxies", fg="#00FF00")

def proxy_check_worker():
    btn_test_proxy.config(state=tk.DISABLED)
    mode = proxy_mode.get()
    raw_pool = [entry_proxy_addr.get().strip()] if mode == 1 else \
               ([l.strip() for l in open("proxies.txt") if l.strip()] if os.path.exists("proxies.txt") else [])
    
    if not any(raw_pool): 
        messagebox.showwarning("!", "No Proxy Found!"); btn_test_proxy.config(state=tk.NORMAL); return

    try: workers = int(entry_threads.get())
    except: workers = 20
    
    random.shuffle(raw_pool); results = []; checked = 0
    def check(proxy):
        nonlocal checked; url = parse_proxy(proxy)
        try:
            start = time.time()
            if requests.get("http://www.google.com", proxies={"http":url,"https":url}, timeout=6).status_code == 200:
                results.append(time.time() - start)
        except: pass
        checked += 1
        label_latency_status.config(text=f"Check: {checked}/{len(raw_pool)}", fg="#FFCC00")

    with ThreadPoolExecutor(max_workers=workers) as exe: exe.map(check, raw_pool)

    if results:
        best = min(results)
        entry_latency.delete(0, tk.END); entry_latency.insert(0, f"{best:.3f}")
        label_latency_status.config(text=f"BEST LIVE: {best:.3f}s", fg="#00FF00")
    else: label_latency_status.config(text="ALL FAILED", fg="#FF3333")
    btn_test_proxy.config(state=tk.NORMAL)

# --- 6-7. Calculation (Updated with Mbps * 8) ---
def calculate():
    try:
        t, r, l, d = [float(e.get()) for e in [entry_threads, entry_rpc, entry_latency, entry_data]]
        rate = get_live_exchange_rate()
        rps = ((t * r) / l) * 0.8
        
        # คำนวณ Bandwidth
        mb_s = (rps * 5) / 1024  # Megabytes per second
        mbps = mb_s * 8          # Megabits per second (คูณ 8 สำหรับเทียบท่อเน็ต)

        label_rps.config(text=f"ESTIMATED RPS: {rps:,.0f}", fg="#00FF00")
        # แสดงผลทั้ง MB/s และ Mbps ในบรรทัดเดียวกัน
        label_data.config(text=f"BANDWIDTH: {mb_s:.2f} MB/s ({mbps:.2f} Mbps)")
        label_time.config(text=f"TIME: {(d*1024)/mb_s/60:.2f} MIN" if mb_s > 0 else "TIME: -", fg="#FFCC00")
        label_total_thb.config(text=f"TOTAL COST: ฿{d*5*rate:,.2f}", fg="#00FF00")
    except: messagebox.showerror("Error", "Check Input!")

# --- GUI Setup ---
root = tk.Tk(); root.title("HYDRA V2 BANDWIDTH+"); root.geometry("480x880"); root.configure(bg="#0A0A0A")
tk.Label(root, text="L7 STRESS TEST PLANNER", font=("Courier", 16, "bold"), bg="#0A0A0A", fg="#00FF00").pack(pady=15)

proxy_mode = tk.IntVar(value=1)
f_mode = tk.Frame(root, bg="#0A0A0A"); f_mode.pack()
for t, v in [("Manual IP", 1), ("From File", 2)]:
    tk.Radiobutton(f_mode, text=t, variable=proxy_mode, value=v, bg="#0A0A0A", fg="white", selectcolor="#333333", 
                   command=lambda: [entry_proxy_addr.config(state=tk.NORMAL if proxy_mode.get()==1 else tk.DISABLED), 
                                   btn_upload.config(state=tk.DISABLED if proxy_mode.get()==1 else tk.NORMAL)]).pack(side=tk.LEFT, padx=10)

entry_proxy_addr = tk.Entry(root, justify='center', font=("Courier", 10), bg="#1A1A1A", fg="white", borderwidth=0); entry_proxy_addr.pack(pady=5, fill="x", padx=50)
btn_upload = tk.Button(root, text="[ UPLOAD PROXY ]", command=upload_and_save_proxy, bg="#444444", fg="white", state=tk.DISABLED); btn_upload.pack(pady=5)
btn_test_proxy = tk.Button(root, text="[ CHECK GOOGLE ]", command=lambda: threading.Thread(target=proxy_check_worker, daemon=True).start(), bg="#333333", fg="white"); btn_test_proxy.pack(pady=5)
label_latency_status = tk.Label(root, text="Ready...", bg="#0A0A0A", fg="#666666"); label_latency_status.pack()

tk.Label(root, text="-"*30, bg="#0A0A0A", fg="#333333").pack()
entry_threads, entry_rpc, entry_latency, entry_data = [create_input(root, n, v) for n, v in [("THREADS", "20"), ("RPC", "2"), ("LATENCY", "0.5"), ("DATA (GB)", "1.0")]]

tk.Button(root, text="[ EXECUTE CALCULATION ]", command=calculate, bg="#00FF00", font=("Courier", 11, "bold")).pack(pady=20)
res_frame = tk.Frame(root, bg="#111111", padx=20, pady=20, highlightthickness=1, highlightbackground="#00FF00"); res_frame.pack(fill="x", padx=30)
label_rps = tk.Label(res_frame, text="ESTIMATED RPS: -", bg="#111111", fg="#00FF00", font=("Courier", 11, "bold")); label_rps.pack(anchor="w")
label_data = tk.Label(res_frame, text="BANDWIDTH: -", bg="#111111", fg="white", font=("Courier", 10)); label_data.pack(anchor="w")
label_time = tk.Label(res_frame, text="TIME REMAINING: -", bg="#111111", fg="white", font=("Courier", 10)); label_time.pack(anchor="w")
label_total_thb = tk.Label(res_frame, text="TOTAL COST (THB): -", bg="#111111", fg="white", font=("Courier", 12, "bold")); label_total_thb.pack(anchor="w", pady=5)

root.mainloop()