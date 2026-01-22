import tkinter as tk
from tkinter import messagebox, filedialog, ttk
import requests, time, os, threading, shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

# --- Core Logic ---
def get_live_rate():
    try: return requests.get("https://open.er-api.com/v6/latest/USD", timeout=2).json()['rates']['THB']
    except: return 36.50

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
        self.alive_box = tk.Text(f_alive, height=10, width=45, bg="#050505", fg="#00FF00", font=("Consolas", 8), borderwidth=1, relief="flat")
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
        
        self.root.geometry("800x950")

    def lock_ui(self, locked=True):
        state = "disabled" if locked else "normal"
        self.rb_manual.config(state=state); self.rb_file.config(state=state)
        self.entry_manual.config(state=state); self.btn_upload.config(state=state)
        self.btn_check.config(state=state)
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
            for p, _ in self.alive_list:
                f.write(f"{p}\n")
            f.write("\n" + "="*40 + "\n")
            f.write(f"HYDRA  - SESSION LOG SUMMARY\n")
            f.write(f"DATE: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"STATUS: {'PAUSED' if self.is_paused else ('COMPLETED' if not self.is_running else 'RUNNING')}\n")
            f.write(f"TOTAL CHECKED: {self.total_count}\n")
            f.write(f"ALIVE: {len(self.alive_list)}\n")
            f.write(f"DEAD: {self.dead_count}\n")
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
                        for _ in range(3):
                            if self.stop_requested: break
                            try:
                                st = time.time()
                                if sess.get("http://google.com/generate_204", timeout=4).status_code < 400: s.append(time.time()-st)
                            except: break
                except: pass
                checked += 1; self.total_count = checked
                if not self.stop_requested:
                    if len(s)==3:
                        avg = sum(s)/3
                        self.alive_list.append((p, avg))
                        self.alive_box.insert(tk.END, f"[{now}] [SUCCESS] {p} | {avg:.3f}s\n")
                        self.lbl_alive_count.config(text=f"ALIVE: {len(self.alive_list)}")
                    else:
                        self.dead_count += 1
                        self.dead_box.insert(tk.END, f"[{now}] [DEAD] {p}\n")
                        self.lbl_dead_count.config(text=f"DEAD: {self.dead_count}")
                    self.alive_box.see(tk.END); self.dead_box.see(tk.END)
                    self.progress["value"] = checked
                    self.lbl_status.config(text=f"Checking: {checked}/{len(raw)}")
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