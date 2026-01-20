import tkinter as tk
from tkinter import messagebox, filedialog
import random
import requests
import time
import os
import threading
import shutil

# --- 1. ฟังก์ชันสร้าง Input (ย้ายมาไว้ด้านบนเพื่อแก้ Error) ---
def create_input(parent, label_text, default_val):
    tk.Label(parent, text=label_text, bg="#0A0A0A", fg="#888888", font=("Courier", 10)).pack()
    entry = tk.Entry(parent, justify='center', font=("Courier", 12), bg="#1A1A1A", fg="#00FF00", borderwidth=0)
    entry.insert(0, default_val)
    entry.pack(pady=5, ipady=3)
    return entry

# --- 2. ฟังก์ชันดึงอัตราแลกเปลี่ยน ---
def get_live_exchange_rate():
    try:
        url = "https://open.er-api.com/v6/latest/USD"
        response = requests.get(url, timeout=5)
        data = response.json()
        return data['rates']['THB']
    except:
        return 36.50 

# --- 3. Smart Proxy Parser ---
def parse_proxy(raw_proxy):
    raw_proxy = raw_proxy.strip()
    if not raw_proxy: return None
    protocol = "http"
    if "://" in raw_proxy:
        protocol, raw_proxy = raw_proxy.split("://", 1)
    parts = raw_proxy.split(":")
    if len(parts) == 2:
        return f"{protocol}://{parts[0]}:{parts[1]}"
    elif len(parts) == 4:
        if "." in parts[0]: ip, port, user, pw = parts
        else: user, pw, ip, port = parts
        return f"{protocol}://{user}:{pw}@{ip}:{port}"
    return f"{protocol}://{raw_proxy}"

# --- 4. ฟังก์ชันจัดการไฟล์ ---
def upload_and_save_proxy():
    file_path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt")])
    if file_path:
        try:
            shutil.copyfile(file_path, "proxies.txt")
            with open("proxies.txt", "r") as f:
                count = len([line for line in f if line.strip()])
            label_latency_status.config(text=f"Uploaded: {count} proxies", fg="#00FF00")
            messagebox.showinfo("Success", f"บันทึกไฟล์ลง proxies.txt เรียบร้อย (พบ {count} รายการ)")
        except Exception as e:
            messagebox.showerror("Error", f"Upload ล้มเหลว: {str(e)}")

def load_proxies_from_file():
    if not os.path.exists("proxies.txt"): return []
    with open("proxies.txt", "r") as f:
        return [line.strip() for line in f.readlines() if line.strip()]

def toggle_proxy_input():
    if proxy_mode.get() == 1:
        entry_proxy_addr.config(state=tk.NORMAL, bg="#1A1A1A", fg="#FFFFFF")
        btn_upload.config(state=tk.DISABLED)
    else:
        entry_proxy_addr.config(state=tk.DISABLED, bg="#333333", fg="#888888")
        btn_upload.config(state=tk.NORMAL)

# --- 5. Proxy Checker (Target: Google) ---
def proxy_check_worker():
    btn_test_proxy.config(state=tk.DISABLED)
    mode = proxy_mode.get()
    raw_pool = [entry_proxy_addr.get().strip()] if mode == 1 else load_proxies_from_file()

    if not raw_pool or (mode == 1 and not raw_pool[0]):
        messagebox.showwarning("Warning", "กรุณาระบุ Proxy หรืออัพโหลดไฟล์!")
        btn_test_proxy.config(state=tk.NORMAL)
        return

    random.shuffle(raw_pool)
    found_live = False
    
    for attempts, raw_proxy in enumerate(raw_pool, 1):
        proxy_url = parse_proxy(raw_proxy)
        if not proxy_url: continue
        
        proxies = {"http": proxy_url, "https": proxy_url}
        label_latency_status.config(text=f"Google Check: {attempts}/{len(raw_pool)}", fg="#FFCC00")
        
        try:
            start_time = time.time()
            # เช็คกับ Google ตามคำขอใหม่
            response = requests.get("http://www.google.com", proxies=proxies, timeout=6)
            if response.status_code == 200:
                latency = time.time() - start_time
                entry_latency.delete(0, tk.END)
                entry_latency.insert(0, f"{latency:.3f}")
                label_latency_status.config(text=f"GOOGLE LIVE! ({latency:.3f}s)", fg="#00FF00")
                found_live = True
                break
        except: continue
            
    if not found_live:
        label_latency_status.config(text="ALL PROXIES FAILED", fg="#FF3333")
    btn_test_proxy.config(state=tk.NORMAL)

def start_proxy_check():
    threading.Thread(target=proxy_check_worker, daemon=True).start()

# --- 6. ฟังก์ชันคำนวณ ---
def calculate():
    try:
        t, r, l, d = float(entry_threads.get()), float(entry_rpc.get()), float(entry_latency.get()), float(entry_data.get())
        rate = get_live_exchange_rate()
        rps = ((t * r) / l) * 0.8
        mb_s = (rps * 5) / 1024
        mins = (d * 1024) / mb_s / 60 if mb_s > 0 else 0
        cost_thb = d * 5 * rate
        
        label_rps.config(text=f"ESTIMATED RPS: {rps:,.0f}", fg="#00FF00")
        label_data.config(text=f"BANDWIDTH: {mb_s:.2f} MB/s")
        label_time.config(text=f"TIME REMAINING: {mins:.2f} MIN", fg="#FFCC00")
        label_total_thb.config(text=f"TOTAL COST (THB): ฿{cost_thb:,.2f}", fg="#00FF00")
    except: messagebox.showerror("Error", "กรุณาตรวจสอบตัวเลขที่กรอก!")

# --- 7. GUI ---
root = tk.Tk()
root.title("HYDRA GOOGLE CHECKER v2")
root.geometry("480x900")
root.configure(bg="#0A0A0A")

tk.Label(root, text="L7 STRESS TEST PLANNER", font=("Courier", 16, "bold"), bg="#0A0A0A", fg="#00FF00").pack(pady=15)

proxy_mode = tk.IntVar(value=1)
frame_mode = tk.Frame(root, bg="#0A0A0A")
frame_mode.pack(pady=5)
tk.Radiobutton(frame_mode, text="Manual IP", variable=proxy_mode, value=1, command=toggle_proxy_input, bg="#0A0A0A", fg="#FFFFFF", selectcolor="#333333").pack(side=tk.LEFT, padx=10)
tk.Radiobutton(frame_mode, text="From File", variable=proxy_mode, value=2, command=toggle_proxy_input, bg="#0A0A0A", fg="#FFFFFF", selectcolor="#333333").pack(side=tk.LEFT, padx=10)

entry_proxy_addr = tk.Entry(root, justify='center', font=("Courier", 10), bg="#1A1A1A", fg="#FFFFFF", borderwidth=0)
entry_proxy_addr.pack(pady=5, ipady=3, fill="x", padx=50)

btn_upload = tk.Button(root, text="[ UPLOAD PROXY LIST ]", command=upload_and_save_proxy, bg="#444444", fg="#FFFFFF", font=("Courier", 8), state=tk.DISABLED)
btn_upload.pack(pady=5)

btn_test_proxy = tk.Button(root, text="[ CHECK LATENCY VIA GOOGLE ]", command=start_proxy_check, bg="#333333", fg="#FFFFFF", font=("Courier", 9))
btn_test_proxy.pack(pady=5)
label_latency_status = tk.Label(root, text="Ready...", bg="#0A0A0A", fg="#666666", font=("Courier", 8))
label_latency_status.pack()

tk.Label(root, text="------------------------------", bg="#0A0A0A", fg="#333333").pack()

# เรียกใช้ฟังก์ชันสร้าง Input ( Error หายแน่นอน )
entry_threads = create_input(root, "THREADS", "500")
entry_rpc = create_input(root, "RPC", "2")
entry_latency = create_input(root, "LATENCY", "0.5")
entry_data = create_input(root, "DATA (GB)", "1.0")

tk.Button(root, text="[ EXECUTE CALCULATION ]", command=calculate, bg="#00FF00", fg="#000000", font=("Courier", 11, "bold")).pack(pady=20)

res_frame = tk.Frame(root, bg="#111111", padx=20, pady=20, highlightbackground="#00FF00", highlightthickness=1)
res_frame.pack(fill="x", padx=30)
label_rps = tk.Label(res_frame, text="ESTIMATED RPS: -", bg="#111111", fg="#00FF00", font=("Courier", 11, "bold")); label_rps.pack(anchor="w")
label_data = tk.Label(res_frame, text="BANDWIDTH: -", bg="#111111", fg="#FFFFFF", font=("Courier", 10)); label_data.pack(anchor="w")
label_time = tk.Label(res_frame, text="TIME REMAINING: -", bg="#111111", fg="#FFFFFF", font=("Courier", 10)); label_time.pack(anchor="w")
label_total_thb = tk.Label(res_frame, text="TOTAL COST (THB): -", bg="#111111", fg="#FFFFFF", font=("Courier", 12, "bold")); label_total_thb.pack(anchor="w", pady=5)

root.mainloop()