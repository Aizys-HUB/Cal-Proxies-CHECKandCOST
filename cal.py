import tkinter as tk
from tkinter import messagebox, filedialog
import random, requests, time, os, threading, shutil
from concurrent.futures import ThreadPoolExecutor

# --- 1-3. Core Functions (สรุปย่อ) ---
def create_input(parent, label_text, default_val):
    tk.Label(parent, text=label_text, bg="#0A0A0A", fg="#888888", font=("Courier", 10)).pack()
    entry = tk.Entry(parent, justify='center', font=("Courier", 12), bg="#1A1A1A", fg="#00FF00", borderwidth=0)
    entry.insert(0, default_val)
    entry.pack(pady=5, ipady=3); return entry

def get_live_exchange_rate():
    try: return requests.get("https://open.er-api.com/v6/latest/USD", timeout=3).json()['rates']['THB']
    except: return 36.50 

def parse_proxy(p):
    p = p.strip()
    if not p: return None
    pref = "http://" if "://" not in p else ""
    return pref + p

# --- 4. File & Mode Management ---
def upload_and_save_proxy():
    path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt")])
    if path:
        shutil.copyfile(path, "proxies.txt")
        count = len([l for l in open("proxies.txt") if l.strip()])
        label_latency_status.config(text=f"Uploaded: {count} proxies", fg="#00FF00")

def toggle_proxy_input():
    st = tk.NORMAL if proxy_mode.get() == 1 else tk.DISABLED
    entry_proxy_addr.config(state=st, bg="#1A1A1A" if st==tk.NORMAL else "#333333")
    btn_upload.config(state=tk.DISABLED if st==tk.NORMAL else tk.NORMAL)

# --- 5. Optimized Proxy Checker (Big O: O(n) but Parallel) ---
def proxy_check_worker():
    btn_test_proxy.config(state=tk.DISABLED)
    raw_pool = [entry_proxy_addr.get()] if proxy_mode.get() == 1 else [l.strip() for l in open("proxies.txt") if l.strip()] if os.path.exists("proxies.txt") else []
    
    if not raw_pool or not raw_pool[0]:
        messagebox.showwarning("!", "No Proxy Found!"); btn_test_proxy.config(state=tk.NORMAL); return

    random.shuffle(raw_pool)
    found_proxies = []
    
    def check(proxy):
        url = parse_proxy(proxy)
        try:
            start = time.time()
            if requests.get("http://www.google.com", proxies={"http":url, "https":url}, timeout=3).status_code == 200:
                found_proxies.append((time.time() - start, url))
        except: pass

    # ใช้ ThreadPoolExecutor เพื่อความเร็วสูงสุด
    with ThreadPoolExecutor(max_workers=20) as exe:
        exe.map(check, raw_pool[:50]) # ตรวจสอบ 50 ตัวแรกเพื่อความรวดเร็ว

    if found_proxies:
        found_proxies.sort() # เอาตัวที่ Latency ต่ำสุด
        lat, best_url = found_proxies[0]
        entry_latency.delete(0, tk.END); entry_latency.insert(0, f"{lat:.3f}")
        label_latency_status.config(text=f"GOOGLE LIVE! ({lat:.3f}s)", fg="#00FF00")
    else:
        label_latency_status.config(text="ALL FAILED", fg="#FF3333")
    btn_test_proxy.config(state=tk.NORMAL)

# --- 6-7. Calculation & GUI ---
def calculate():
    try:
        t, r, l, d = [float(e.get()) for e in [entry_threads, entry_rpc, entry_latency, entry_data]]
        rate = get_live_exchange_rate()
        rps = ((t * r) / l) * 0.8
        mb_s = (rps * 5) / 1024
        label_rps.config(text=f"ESTIMATED RPS: {rps:,.0f}")
        label_data.config(text=f"BANDWIDTH: {mb_s:.2f} MB/s")
        label_time.config(text=f"TIME: {(d*1024)/mb_s/60:.2f} MIN" if mb_s > 0 else "TIME: -")
        label_total_thb.config(text=f"TOTAL COST: ฿{d*5*rate:,.2f}")
    except: messagebox.showerror("!", "Invalid Input")

root = tk.Tk(); root.title("HYDRA V2"); root.geometry("400x800"); root.configure(bg="#0A0A0A")
tk.Label(root, text="L7 PLANNER", font=("Courier", 16, "bold"), bg="#0A0A0A", fg="#00FF00").pack(pady=10)

proxy_mode = tk.IntVar(value=1)
f_mode = tk.Frame(root, bg="#0A0A0A"); f_mode.pack()
for txt, val in [("Manual", 1), ("File", 2)]:
    tk.Radiobutton(f_mode, text=txt, variable=proxy_mode, value=val, command=toggle_proxy_input, bg="#0A0A0A", fg="white").pack(side=tk.LEFT)

entry_proxy_addr = tk.Entry(root, justify='center', bg="#1A1A1A", fg="white"); entry_proxy_addr.pack(fill="x", padx=50, pady=5)
btn_upload = tk.Button(root, text="UPLOAD", command=upload_and_save_proxy, state=tk.DISABLED); btn_upload.pack()
btn_test_proxy = tk.Button(root, text="CHECK GOOGLE", command=lambda: threading.Thread(target=proxy_check_worker, daemon=True).start()); btn_test_proxy.pack(pady=5)
label_latency_status = tk.Label(root, text="Ready...", bg="#0A0A0A", fg="#666666"); label_latency_status.pack()

entry_threads = create_input(root, "THREADS", "500")
entry_rpc = create_input(root, "RPC", "2")
entry_latency = create_input(root, "LATENCY", "0.5")
entry_data = create_input(root, "DATA (GB)", "1.0")

tk.Button(root, text="EXECUTE", command=calculate, bg="#00FF00", font=("Courier", 11, "bold")).pack(pady=10)
res_frame = tk.Frame(root, bg="#111111", padx=10, pady=10); res_frame.pack(fill="x", padx=20)
label_rps = tk.Label(res_frame, text="RPS: -", bg="#111111", fg="#00FF00"); label_rps.pack(anchor="w")
label_data = tk.Label(res_frame, text="BW: -", bg="#111111", fg="white"); label_data.pack(anchor="w")
label_time = tk.Label(res_frame, text="TIME: -", bg="#111111", fg="white"); label_time.pack(anchor="w")
label_total_thb = tk.Label(res_frame, text="COST: -", bg="#111111", fg="#00FF00"); label_total_thb.pack(anchor="w")

root.mainloop()