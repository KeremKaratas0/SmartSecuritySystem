from msilib.schema import Error
import tkinter as tk
from tkinter import filedialog as fd
from tkinter import messagebox as mb
from tkinter import ttk
import subprocess
import psutil
import socket
import paramiko
import re
import detect
import threading


def is_ethernet_connected():
    net_if_addrs = psutil.net_if_addrs()
    net_if_stats = psutil.net_if_stats()
    for iface, stats in net_if_stats.items():
        if stats.isup and "Ethernet" in iface:
            return True
    return False
def is_pi_reachable(hostname="raspberrypi.local"):
    try:
        output = subprocess.check_output(["ping", "-n", "1", hostname], timeout=3)
        return True
    except subprocess.CalledProcessError:
        return False
    except subprocess.TimeoutExpired:
        return False
def resolve_pi_ip(hostname="raspberrypi.local"):
    try:
        ip = socket.gethostbyname(hostname)
        return ip
    except socket.gaierror:
        return None
def try_connecting_to_pi(username,password):
    if is_ethernet_connected():
        if is_pi_reachable():
            try:
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                client.connect(hostname="raspberrypi.local", username=username, password=password, timeout=5)
                return "Connected"
            except paramiko.AuthenticationException:
                return "Authentication failed."
            except paramiko.SSHException as sshException:
                return (f"Unable to establish SSH connection: {sshException}")
            except Exception as e:
                return (f" Connection failed: {e}")
            finally:
                client.close()
        else:
            return 'Pi is unreacahable.'       
    else:
       return "Ethernet is not connected."    
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.folder_path=""
        self.password=""
        self.selected_mac=''
        self.obex_channel=''
        self.running=False
        self.mac_page=None
        self.title("Smart Office Security System")
        container = tk.Frame(self)
        container.pack(fill="both", expand=True)
        self.pages = {}
        for PageClass in (StartPage,):  # Only StartPage at first
            page = PageClass(container, self)
            self.pages[PageClass] = page
            page.grid(row=0, column=0, sticky="nsew")
        self.show_page(StartPage)
    def browse_folder(self,folder_entry):
        folder_path = fd.askdirectory()  
        if folder_path:  
            folder_entry.delete(0, tk.END)  
            folder_entry.insert(0, folder_path)
    def show_page(self, page_class):
        page = self.pages[page_class]
        page.tkraise()
    def on_send_button_click(self, folder_entry, password_entry):
        folder = folder_entry.get()
        password = password_entry.get()
        if not folder or not password:
            mb.showwarning("Missing Info", "Please enter the output folder and Raspberry Pi password.")
            return
        self.folder_path = folder
        self.password = password
        container = self.pages[StartPage].master
        second_page = SecondPage(container, self)
        self.pages[SecondPage] = second_page
        second_page.grid(row=0, column=0, sticky="nsew")
        self.show_page(SecondPage)
    def get_mac_addresses(self):
        client=paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        if(len(self.password)>0):
            try:
                client.connect('raspberrypi.local', username='admin', password=self.password)
                channel=client.invoke_shell()
                channel.send("bluetoothctl\n")
                channel.send("power on\n")
                channel.send("agent on\n")
                channel.send("scan on\n")
                buffer = ""
                while self.running: 
                    if channel.recv_ready():
                        data = channel.recv(1024).decode("utf-8")
                        buffer += data
                        lines = buffer.split("\n")
                        buffer = lines[-1]
                        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
                        for line in lines[:-1]:
                            line = ansi_escape.sub('', line)
                            line = ''.join(ch for ch in line if ch.isprintable())
                            line= line.strip()
                            if '[NEW] Device' in line:
                                mac=line.split()[3]
                                self.mac_page.add_list_element(mac)
                            elif '[DEL] Device' in line:
                                mac=line.split()[3]
                                self.mac_page.del_list_element(mac)
                channel.send("scan off\n")
                channel.send("exit\n")
                channel.close()
            finally:
                client.close()
    def set_obex_channel(self):
        scan=f'sdptool browse {self.selected_mac} > obex.txt'
        get_scan_output='cat obex.txt'
        client=paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        output=''
        if(len(self.password)>0):
            try:
                client.connect('raspberrypi.local', username='admin', password=self.password)
                client.exec_command(scan)
                stdin,stdout,stderr=client.exec_command(get_scan_output)
                lines=stdout.readlines()
                obex_found=False
                for line in lines:
                    if(obex_found):
                        if(line.find('Channel')!=-1):
                            output=line.split(':')[1].strip()
                    else:
                        if(line.find('OBEX')!=-1):
                            obex_found=True            
            finally:
                client.close()
            self.obex_channel=output
    def set_bluetooth_connection(self):
        get_cnct_bt='cat expect.sh'
        client=paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        output=''
        if(len(self.password)>0):
            try:
                client.connect('raspberrypi.local', username='admin', password=self.password)
                stdin,stdout,stderr=client.exec_command(get_cnct_bt)
                lines=stdout.readlines()
                modified_lines = [line.replace('[lindex $argv 0]', self.selected_mac) for line in lines]
                for line in modified_lines:
                    client.exec_command(line)   
            finally:
                client.close()
            return output    
        
class StartPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)

        self.controller = controller

        folder_label = tk.Label(self, text="Select Output Folder:")
        folder_label.pack(pady=5)

        self.folder_entry = tk.Entry(self, width=40)
        self.folder_entry.pack(pady=5)

        browse_button = tk.Button(self, text="Browse", command=lambda: controller.browse_folder(self.folder_entry))
        browse_button.pack(pady=5)

        password_label = tk.Label(self, text="Enter Raspberry Pi Password:")
        password_label.pack(pady=5)

        self.password_entry = tk.Entry(self, show="*", width=40)
        self.password_entry.pack(pady=5)

        continue_button = tk.Button(
            self,
            text="Continue",
            command=self.on_continue_click
        )
        continue_button.pack(pady=20)

    def on_continue_click(self):
        folder = self.folder_entry.get()
        password = self.password_entry.get()

        if not folder or not password:
            mb.showwarning("Missing Info", "Please enter the folder and password.")
            return

        self.controller.folder_path = folder
        self.controller.password = password
        container = self.controller.pages[StartPage].master  
        second_page = SecondPage(container, self.controller)
        self.controller.pages[SecondPage] = second_page
        second_page.grid(row=0, column=0, sticky="nsew")
        self.controller.show_page(SecondPage)
class SecondPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.text_label = tk.Label(self, text="Ready to connect to Raspberry Pi...")
        self.text_label.pack(pady=10)

        self.progress = ttk.Progressbar(self, mode="indeterminate")
        self.progress.pack(pady=5)

        self.connect_button = tk.Button(self, text="Connect Now", command=self.start_connection_thread)
        self.connect_button.pack(pady=10)
    def start_connection_thread(self):
        self.progress.start()
        threading.Thread(target=self.try_connect_async, daemon=True).start()

    def try_connect_async(self):
        result = try_connecting_to_pi(username="admin", password=self.controller.password)
        print(result)
        self.after(0, lambda: self.handle_result(result))

    def handle_result(self, result):
        self.progress.stop()
        self.progress.pack_forget()
        if result == "Connected":
            self.text_label.config(text="Connected successfully!")
            container = self.controller.pages[StartPage].master
            third_page = ThirdPage(container, self.controller)
            self.controller.pages[ThirdPage] = third_page
            third_page.grid(row=0, column=0, sticky="nsew")
            self.after(2000, lambda: self.controller.show_page(ThirdPage))
        elif result == "Authentication failed.":
            self.text_label.config(text="Authentication failed. Please try again.")
            password_label = tk.Label(self, text="Enter Raspberry Pi Password:")
            password_label.pack(pady=5)
            self.password_entry = tk.Entry(self, show="*", width=40)
            self.password_entry.pack(pady=5)
            self.connect_button.configure(text='Retry',command=self.retry_with_new_password)
        else:
            self.text_label.config(text="Could not connect. Try again?")
            self.connect_button.configure(text='Retry',command=lambda:self.controller.show_page(SecondPage))

    def retry_with_new_password(self):
        self.controller.password = self.password_entry.get()
        self.controller.show_page(SecondPage)
class ThirdPage(tk.Frame):   
    def __init__(self, parent, controller):
        super().__init__(parent)            #liste en başta oluşturulacak
        self.controller = controller
        self.controller.mac_page=self
        self.build_ui()
    def build_ui(self):
            self.text_label = tk.Label(self, text='Retrieving available MAC addresses...')
            self.text_label.pack(pady=5)
            self.listbox=tk.Listbox(self,selectmode='single')
            self.listbox.pack(pady=10)
            self.confirm_button = tk.Button(self, text='Confirm selection', command=self.confirm_selection,state='disabled')
            self.confirm_button.pack(pady=5)
            threading.Thread(target=self.load_mac_addresses, daemon=True).start()

    def add_list_element(self,mac):
        existing_items = self.listbox.get(0, tk.END)
        if mac not in existing_items:
                self.after(0, self.listbox.insert, tk.END, mac)
    def del_list_element(self,mac):
        items = self.listbox.get(0, tk.END)
        if mac in items:
            index = items.index(mac)
            self.after(0,self.listbox.delete,index)
    def load_mac_addresses(self):
            self.controller.running = True
            self.controller.get_mac_addresses()
            self.after(0, self.show_mac_selection)
    def show_mac_selection(self):
        self.after(10,None)
        items = self.listbox.get(0, tk.END)
        if items:
            if 'Currently there is not any available device' in items:
                index=items.index('Currently there is not any available device')
                self.listbox.delete(index)
                self.text_label.config(text="Select a device:")
                self.confirm_button.configure(state='active')
        else:
            self.listbox.insert(tk.End,'Currently there is not any available device')
        
    def confirm_selection(self):
        if self.listbox.curselection():
            selected = self.listbox.get(self.listbox.curselection())
            self.controller.selected_mac = selected
            self.controller.running=False
            threading.Thread(target=self.setup_bluetooth_connection, daemon=True).start()
        else:
            mb.showwarning(message='You have not selected any MAC address.')
    def setup_bluetooth_connection(self):
        self.controller.set_obex_channel()
        self.controller.set_bluetooth_connection()
        container = self.controller.pages[StartPage].master
        last_page = LastPage(container, self.controller)
        self.controller.pages[LastPage] = last_page
        last_page.grid(row=0, column=0, sticky="nsew")
        self.after(0, lambda: self.controller.show_page(LastPage))

class LastPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.build_ui()
    def build_ui(self):
            self.ready_txt = tk.Label(self, text='Everything is ready!')
            self.ready_txt.pack(pady=10)
            self.progress = ttk.Progressbar(self, mode='indeterminate')
            self.progress.pack(pady=10)
            self.progress.stop()       
            self.status_label = tk.Label(self, text='')
            self.status_label.pack(pady=5)
            self.start_button = tk.Button(self, text='Start', command=self.on_start_button_click)
            self.start_button.pack(pady=5)
    def on_start_button_click(self):
        self.progress.start()
        self.status_label.config(text="Connecting to Raspberry Pi and running script...")
        self.start_button.config(state='disabled')
        threading.Thread(target=self.start_remote_script_and_detection, daemon=True).start()
    def start_remote_script_and_detection(self):
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect('raspberrypi.local', username='admin', password=self.controller.password)
            stdin, stdout, stderr = client.exec_command('cat script.sh')
            output = stdout.read().decode()
            output = output.replace('put_mac_here', self.controller.selected_mac)
            output = output.replace('put_obex_here', self.controller.obex_channel)
            safe_script = output.replace("'", r"'\''")
            client.exec_command(f"echo '{safe_script}' > script.sh")
            client.exec_command('chmod +x script.sh && ./script.sh')
            client.close()
            self.after(0, self.launch_detection_process)
        except Exception as e:
            self.after(0, lambda: self.status_label.config(text=f"Error: {e}"))
            self.progress.stop()
    def launch_detection_process(self):
        self.status_label.config(text="Running object detection...")
        self.progress.stop() 
        try:
            threading.Thread(
            target=detect.object_detection,
            args=(self.controller.folder_path, 'raspberrypi.local', self.controller.password),
            daemon=True
            ).start()
        except Error:
            print(Error)

if __name__ == "__main__":
    app = App()
    app.mainloop()

